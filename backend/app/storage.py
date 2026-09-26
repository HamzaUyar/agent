"""Supabase Storage: drone görüntülerinin dosyaları.

`images.file_path` "<bucket>/<nesne>" biçimindedir (ör. `drone-images/img_000860.jpg`).
Tespit ve VLM dosya yolu ister; görüntü yerel klasörde yoksa Storage'dan indirilip
oraya yazılır, sonraki okumalar yerelden yapılır.
"""

import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.data_package import find_image_file
from app.schemas.domain import ImageMeta

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30.0


class StorageError(RuntimeError):
    """Storage isteği başarısız oldu."""


def storage_path(bucket: str, file_name: str) -> str:
    """`images.file_path` değeri: "<bucket>/<nesne>"."""
    return f"{bucket}/{file_name}"


def _split(file_path: str) -> tuple[str, str]:
    bucket, _, name = file_path.partition("/")
    if not bucket or not name:
        raise StorageError(f"Storage yolu '<bucket>/<nesne>' biçiminde değil: {file_path!r}")
    return bucket, name


class SupabaseStorage:
    """Storage REST API'si, `service_role` anahtarıyla."""

    def __init__(
        self,
        url: str,
        service_role_key: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
    ) -> None:
        self._base = f"{url.rstrip('/')}/storage/v1/object"
        self._headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }
        self._client = client or httpx.Client(timeout=timeout_s)

    def _url(self, file_path: str) -> str:
        bucket, name = _split(file_path)
        return f"{self._base}/{quote(bucket)}/{quote(name)}"

    def download(self, file_path: str) -> bytes:
        response = self._client.get(self._url(file_path), headers=self._headers)
        if response.status_code != httpx.codes.OK:
            raise StorageError(f"{file_path} indirilemedi: {response.status_code} {response.text}")
        return response.content

    def upload(self, file_path: str, data: bytes, content_type: str) -> None:
        """Nesneyi yazar; varsa üzerine yazar."""
        response = self._client.post(
            self._url(file_path),
            content=data,
            headers={**self._headers, "Content-Type": content_type, "x-upsert": "true"},
        )
        if response.status_code != httpx.codes.OK:
            raise StorageError(f"{file_path} yüklenemedi: {response.status_code} {response.text}")


def build_storage(settings: Settings) -> SupabaseStorage | None:
    """`SUPABASE_URL` ve `SUPABASE_SERVICE_ROLE_KEY` tanımlıysa Storage istemcisi."""
    key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not key:
        return None
    return SupabaseStorage(settings.supabase_url, key)


def resolve_image_file(
    images_dir: Path, image: ImageMeta, storage: SupabaseStorage | None
) -> Path | None:
    """Görüntünün yerel dosyası; yerelde yoksa Storage'dan `images_dir` içine indirilir.

    Dosya hiçbir yerde bulunamazsa `None`.
    """
    local = find_image_file(images_dir, image.image_id)
    if local is not None or storage is None or not image.file_path:
        return local
    try:
        _, name = _split(image.file_path)
        data = storage.download(image.file_path)
    except (StorageError, httpx.HTTPError) as exc:
        logger.warning("%s Storage'dan alınamadı: %s", image.image_id, exc)
        return None
    target = images_dir / Path(name).name
    images_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.part")
    partial.write_bytes(data)
    partial.replace(target)
    logger.info("%s Storage'dan indirildi: %s", image.image_id, target)
    return target
