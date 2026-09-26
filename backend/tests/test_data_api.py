"""Salt veri okuyan uçlar: arkalarında servis olmadığı için HTTP seviyesinde test edilir.

Uygulamanın açılışı (Supabase'ten yükleme) çalıştırılmaz; depo ve görüntü klasörü
bağımlılık olarak değiştirilir.
"""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.data import get_image_storage, get_images_dir, get_repository
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.main import app
from app.storage import SupabaseStorage

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
JPEG = b"\xff\xd8\xff\xe0 sahte jpeg"


@pytest.fixture
def images_dir(tmp_path: Path) -> Path:
    (tmp_path / "img_000860.jpg").write_bytes(JPEG)
    return tmp_path


@pytest.fixture
def client(images_dir: Path) -> Iterator[TestClient]:
    repo = InMemoryRepository(read_package(FIXTURE))
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_images_dir] = lambda: images_dir
    app.dependency_overrides[get_image_storage] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


BUCKET_JPEG = b"\xff\xd8\xff\xe0 bucket jpeg"


def storage_client(images_dir: Path, handle: httpx.MockTransport) -> TestClient:
    """Supabase modu: görüntülerin `file_path`'i var, dosyalar bucket'tan gelir."""
    package = read_package(FIXTURE)
    images = [replace(m, file_path=f"drone-images/{m.image_id}.jpg") for m in package.images]
    repo = InMemoryRepository(replace(package, images=images))
    storage = SupabaseStorage(
        "https://proje.supabase.co", "service-role", client=httpx.Client(transport=handle)
    )
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_images_dir] = lambda: images_dir
    app.dependency_overrides[get_image_storage] = lambda: storage
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def test_zones_returns_the_base_and_zone_centres_in_the_package_shape(client: TestClient) -> None:
    body = client.get("/zones").json()

    assert body["base"] == {"name": "Merkez Us", "lat": 39.92184, "lon": 32.85306}
    assert len(body["zones"]) == 8
    assert body["zones"][0] == {"name": "Kuzey Yolu", "center": [39.950586, 32.85306]}
    # Bölgelerin sınırı veride yok; uç da uydurmaz.
    assert all(set(z) == {"name", "center"} for z in body["zones"])


def test_image_detail_returns_meta_corners_centre_and_zone(client: TestClient) -> None:
    body = client.get("/images/img_000860").json()

    assert body == {
        "image_id": "img_000860",
        "width_px": 960,
        "height_px": 540,
        "capture_time": "14:10",
        "corner_coordinates": {
            "top_left": [39.925651, 32.870729],
            "top_right": [39.925651, 32.872131],
            "bottom_left": [39.925045, 32.870729],
            "bottom_right": [39.925045, 32.872131],
        },
        "center": [pytest.approx(39.925348), pytest.approx(32.87143)],
        "zone": "Dogu Yolu",
    }


def test_image_outside_the_data_set_is_404(client: TestClient) -> None:
    assert client.get("/images/img_999999").status_code == 404
    assert client.get("/images/img_999999/file").status_code == 404


def test_image_file_is_served_with_content_type_and_cache_header(client: TestClient) -> None:
    response = client.get("/images/img_000860/file")

    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert "etag" in response.headers


def test_image_in_the_data_set_without_a_file_is_404(client: TestClient) -> None:
    # img_000100 meta'da var, klasörde dosyası yok.
    response = client.get("/images/img_000100/file")

    assert response.status_code == 404
    assert "dosyası" in response.json()["detail"]


def test_with_storage_the_file_comes_from_the_bucket_not_the_local_folder(
    images_dir: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=BUCKET_JPEG)

    # Yerelde aynı adlı bir dosya olsa da kullanılmaz.
    response = storage_client(images_dir, httpx.MockTransport(handle)).get(
        "/images/img_000860/file"
    )

    assert response.status_code == 200
    assert response.content == BUCKET_JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert [r.url.path for r in requests] == ["/storage/v1/object/drone-images/img_000860.jpg"]


def test_with_storage_a_missing_object_is_404(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"statusCode": "404", "error": "not_found"})

    response = storage_client(tmp_path, httpx.MockTransport(handle)).get("/images/img_000860/file")

    assert response.status_code == 404
    assert "dosyası" in response.json()["detail"]


def test_with_storage_an_unreachable_bucket_is_502(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ağ yok", request=request)

    response = storage_client(tmp_path, httpx.MockTransport(handle)).get("/images/img_000860/file")

    assert response.status_code == 502
