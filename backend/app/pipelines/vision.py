"""VLM ile görsel doğrulama: renk, yük ve "gerçekten araç mı".

Yalnızca gerektiğinde çağrılır: zayıf bir tespit bir track'le eşleştiğinde ya da bir
temasa bağlanan iddia renk veya yük belirttiğinde. VLM tespit kutusunun kırpılmış
halini görür. Görüntü dosyası yoksa, model cevap vermezse ya da süre aşılırsa sonuç
`None` olur ve özellik "doğrulanamadı" kalır.
"""

import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Protocol, get_args

from PIL import Image
from pydantic import BaseModel, Field

from app.data_package import find_image_file
from app.llm.client import LLMRouter, LLMUnavailableError
from app.schemas.api import VisualFinding
from app.schemas.domain import CargoState, ImageMeta, VehicleColor

logger = logging.getLogger(__name__)

TASK = "vision"
PROMPT_PATH = Path(__file__).parents[1] / "agent" / "prompts" / "vision.md"
DEFAULT_TIMEOUT_S = 30.0
# Küçük kutular VLM'e bağlamıyla ve büyütülerek verilir.
CROP_PADDING = 0.5
CROP_MIN_PADDING_PX = 24
CROP_MIN_SIDE_PX = 384

BBox = tuple[float, float, float, float]

COLOR_WORDS: dict[str, VehicleColor] = {c: c for c in get_args(VehicleColor)} | {
    "lacivert": "mavi",
    "gumus": "gri",
    "kursuni": "gri",
    "fume": "gri",
    "haki": "yesil",
    "bordo": "kirmizi",
    "krem": "bej",
}
_TR_ASCII = str.maketrans("çğıöşüâîûÇĞİÖŞÜ", "cgiosuaiucgiosu")


def normalize_color(text: str | None) -> VehicleColor | None:
    """Rapordaki renk ifadesini paletteki renge indirger ("koyu yeşil" → yesil)."""
    if not text:
        return None
    for word in re.findall(r"[a-z]+", text.translate(_TR_ASCII).lower()):
        if word in COLOR_WORDS:
            return COLOR_WORDS[word]
    return None


class VisualVerifier(Protocol):
    def inspect(self, image: ImageMeta, bbox: BBox) -> VisualFinding | None:
        """Kutudaki aracı inceler; bakılamadıysa `None`."""
        ...


class VisualObservation(BaseModel):
    """VLM'den istenen yapılandırılmış cevap."""

    is_vehicle: bool = Field(description="Kutunun ortasında gerçekten bir kara aracı var mı")
    color: VehicleColor | None = Field(description="Aracın gövde rengi; seçilemiyorsa null")
    cargo: CargoState | None = Field(
        description="Yük alanı görünüyorsa: loaded (yüklü) ya da empty (boş); görünmüyorsa null"
    )


def crop_box(path: Path, bbox: BBox) -> bytes:
    """Kutuyu çevresiyle birlikte kırpar, gerekirse büyütür ve JPEG olarak döndürür."""
    x, y, w, h = bbox
    with Image.open(path) as img:
        pad = max(CROP_PADDING * max(w, h), CROP_MIN_PADDING_PX)
        left, top = max(0, int(x - pad)), max(0, int(y - pad))
        right, bottom = min(img.width, int(x + w + pad)), min(img.height, int(y + h + pad))
        crop = img.convert("RGB").crop((left, top, right, bottom))
    scale = CROP_MIN_SIDE_PX / max(crop.size)
    if scale > 1:
        crop = crop.resize(
            (round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS
        )
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


class VlmVerifier:
    """Görev zincirindeki VLM ile doğrulama (`models.toml` → `vision`)."""

    def __init__(
        self, router: LLMRouter, images_dir: Path, *, timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> None:
        self._router = router
        self._images_dir = images_dir
        self._timeout_s = timeout_s

    def inspect(self, image: ImageMeta, bbox: BBox) -> VisualFinding | None:
        path = find_image_file(self._images_dir, image.image_id)
        if path is None:
            logger.warning("Görsel doğrulama atlandı: %s dosyası yok", image.image_id)
            return None
        try:
            crop = crop_box(path, bbox)
        except OSError as exc:  # bozuk ya da desteklenmeyen dosya (UnidentifiedImageError dahil)
            logger.warning("Görsel doğrulama atlandı: %s okunamadı (%s)", path.name, exc)
            return None
        system = PROMPT_PATH.read_text(encoding="utf-8")
        user = "Kırpılmış drone görüntüsündeki, ortadaki aracı incele."
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._router.complete_json,
            TASK,
            system,
            user,
            VisualObservation,
            1024,
            image=crop,
        )
        try:
            observation, model = future.result(timeout=self._timeout_s)
        except FutureTimeout:
            logger.warning("Görsel doğrulama zaman aşımı (%s sn)", self._timeout_s)
            return None
        except LLMUnavailableError as exc:
            logger.warning("Görsel doğrulama yapılamadı: %s", exc)
            return None
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return VisualFinding(**observation.model_dump(), model=model)
