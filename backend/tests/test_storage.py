"""Supabase Storage: görüntünün yerelde yoksa indirilmesi."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import time
from pathlib import Path

import httpx

from app.schemas.domain import Corners, GeoPoint, ImageMeta
from app.storage import StorageError, SupabaseStorage, resolve_image_file, storage_path

URL = "https://proje.supabase.co"
KEY = "service-role"


def image(file_path: str | None = "drone-images/img_000860.jpg") -> ImageMeta:
    p = GeoPoint(39.9, 32.8)
    return ImageMeta(
        image_id="img_000860",
        width_px=10,
        height_px=10,
        capture_time=time(14, 10),
        corners=Corners(top_left=p, top_right=p, bottom_left=p, bottom_right=p),
        file_path=file_path,
    )


def storage(handler: httpx.MockTransport) -> SupabaseStorage:
    return SupabaseStorage(URL, KEY, client=httpx.Client(transport=handler))


def test_storage_path_is_bucket_and_object() -> None:
    assert storage_path("drone-images", "img_000860.jpg") == "drone-images/img_000860.jpg"


def test_missing_local_file_is_downloaded_once(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"jpeg")

    store = storage(httpx.MockTransport(handle))
    path = resolve_image_file(tmp_path, image(), store)
    again = resolve_image_file(tmp_path, image(), store)

    assert path == again == tmp_path / "img_000860.jpg"
    assert path.read_bytes() == b"jpeg"
    assert len(requests) == 1
    assert str(requests[0].url) == f"{URL}/storage/v1/object/drone-images/img_000860.jpg"
    assert requests[0].headers["Authorization"] == f"Bearer {KEY}"


def test_concurrent_callers_share_one_download(tmp_path: Path) -> None:
    # Görsel doğrulama kutuları paralel inceler; ilk ihtiyaçta hepsi aynı dosyayı ister.
    workers = 4
    arrived = threading.Barrier(workers, timeout=5)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"jpeg")

    store = storage(httpx.MockTransport(handle))

    def resolve(_: int) -> Path | None:
        arrived.wait()
        return resolve_image_file(tmp_path, image(), store)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(resolve, range(workers)))

    assert paths == [tmp_path / "img_000860.jpg"] * workers
    assert (tmp_path / "img_000860.jpg").read_bytes() == b"jpeg"
    assert len(requests) == 1
    assert list(tmp_path.glob(".*.part")) == []


def test_local_file_wins_without_storage_call(tmp_path: Path) -> None:
    (tmp_path / "img_000860.jpg").write_bytes(b"local")

    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Storage çağrılmamalı")

    path = resolve_image_file(tmp_path, image(), storage(httpx.MockTransport(fail)))
    assert path is not None and path.read_bytes() == b"local"


def test_storage_error_or_missing_path_gives_none(tmp_path: Path) -> None:
    store = storage(httpx.MockTransport(lambda r: httpx.Response(404, text="not found")))
    assert resolve_image_file(tmp_path, image(), store) is None
    assert resolve_image_file(tmp_path, image(file_path=None), store) is None
    assert resolve_image_file(tmp_path, image(), None) is None
    assert not any(tmp_path.iterdir())


def test_upload_sends_upsert() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": "drone-images/a.jpg"})

    storage(httpx.MockTransport(handle)).upload("drone-images/a.jpg", b"x", "image/jpeg")
    assert seen[0].method == "POST"
    assert seen[0].headers["x-upsert"] == "true"
    assert seen[0].headers["Content-Type"] == "image/jpeg"


def test_bad_path_is_rejected() -> None:
    store = storage(httpx.MockTransport(lambda r: httpx.Response(200)))
    try:
        store.download("img_000860.jpg")
    except StorageError:
        return
    raise AssertionError("StorageError bekleniyordu")
