"""Salt veri okuyan uçlar: arkalarında servis olmadığı için HTTP seviyesinde test edilir.

Uygulamanın açılışı (Supabase'ten yükleme) çalıştırılmaz; depo ve görüntü klasörü
bağımlılık olarak değiştirilir.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.data import get_images_dir, get_repository
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.main import app

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
    yield TestClient(app)
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
