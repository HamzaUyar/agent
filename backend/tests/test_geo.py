"""Piksel → koordinat: görev tanımının formülü ve örnekleri (gorev_tanimi.pdf s2-s3).

Konumlandırma ana test noktası (değerlendirme servisi) üzerinden de test ediliyor; bu dosya
organizatörün verdiği sayıları doğrudan kilitler.
"""

from datetime import time

import pytest

from app.pipelines.geo import pixel_to_geo
from app.schemas.domain import Corners, Detection, GeoPoint, ImageMeta, VehicleClass


def image(width: int, height: int, tl: GeoPoint, tr_lon: float, bl_lat: float) -> ImageMeta:
    return ImageMeta(
        "img",
        width,
        height,
        time(13, 25),
        Corners(tl, GeoPoint(tl.lat, tr_lon), GeoPoint(bl_lat, tl.lon), GeoPoint(bl_lat, tr_lon)),
    )


def test_task_definition_example_img_000123() -> None:
    """s2: 1360×765, kutu (610, 380, 60, 28) → merkez (640, 394) → 39.94439, 32.86350."""
    img = image(1360, 765, GeoPoint(39.94510, 32.86200), 32.86519, 39.94373)
    box = Detection(VehicleClass.TRUCK, 0.9, 610, 380, 60, 28)

    assert box.center_px == (640, 394)
    point = pixel_to_geo(img, *box.center_px)
    assert point.lat == pytest.approx(39.94439, abs=5e-6)
    assert point.lon == pytest.approx(32.86350, abs=5e-6)


def test_case_brief_example_img_000860() -> None:
    """Case brief s21: 960×540, merkez (756, 301) → 39.92531, 32.87183."""
    img = image(960, 540, GeoPoint(39.925651, 32.870729), 32.872131, 39.925045)

    point = pixel_to_geo(img, 756, 301)

    assert point.lat == pytest.approx(39.92531, abs=5e-6)
    assert point.lon == pytest.approx(32.87183, abs=5e-6)


def test_corners_map_to_their_coordinates() -> None:
    """Üst kenar kuzey, sol kenar batı (s3); sol üst (0, 0)."""
    img = image(960, 540, GeoPoint(39.9, 32.8), 32.9, 39.8)

    assert pixel_to_geo(img, 0, 0) == GeoPoint(39.9, 32.8)
    assert pixel_to_geo(img, 960, 540) == pytest.approx(GeoPoint(39.8, 32.9))
