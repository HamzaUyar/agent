"""Tespit–track eşleşmesi: görüntü başına birebir, toplam mesafeyi en aza indiren atama."""

import csv
import statistics
from datetime import time
from math import cos, radians

import pytest

from app.core.config import BACKEND_DIR
from app.data_package import read_package
from app.pipelines.detection import read_detections_csv
from app.pipelines.geo import in_footprint, pixel_to_geo
from app.pipelines.matching import (
    METERS_PER_DEGREE,
    LocatedDetection,
    MatchResult,
    local_distance_m,
    match_detections,
)
from app.schemas.domain import Detection, GeoPoint, TrackPoint, VehicleClass

ORIGIN = GeoPoint(39.9, 32.9)
AT = time(14, 10)


def east(m: float, north: float = 0.0) -> GeoPoint:
    """ORIGIN'den `m` metre doğu, `north` metre kuzey (eşleşme mesafesiyle tutarlı)."""
    lat = ORIGIN.lat + north / METERS_PER_DEGREE
    return GeoPoint(lat, ORIGIN.lon + m / (METERS_PER_DEGREE * cos(radians(lat))))


def located(at: GeoPoint, confidence: float = 0.9) -> LocatedDetection:
    return LocatedDetection(Detection(VehicleClass.CAR, confidence, 0, 0, 10, 10), at)


def point(track_id: str, at: GeoPoint) -> TrackPoint:
    return TrackPoint(track_id, AT, at)


def assignment(results: list[MatchResult]) -> list[str | None]:
    return [r.track.track_id if r.track else None for r in results]


def test_distance_is_the_flat_approximation_from_the_task() -> None:
    assert local_distance_m(ORIGIN, east(3.0, 4.0)) == pytest.approx(5.0, abs=1e-3)


def test_assignment_minimises_the_total_distance_not_each_nearest() -> None:
    # En yakın çift A–T1 (0,2 m). Açgözlü eşleme onu alıp B'yi eşsiz bırakırdı (B'nin eşik
    # içindeki tek adayı T1). Birebir atama ikisini de eşler: A–T0 (1,0 m), B–T1 (1,2 m).
    detections = [located(east(1.0)), located(east(2.4))]
    points = [point("T0", east(0.0)), point("T1", east(1.2))]

    results = match_detections(detections, points, threshold_m=1.5)

    assert assignment(results) == ["T0", "T1"]


def test_pairs_beyond_the_threshold_never_match() -> None:
    results = match_detections([located(east(0.0))], [point("T0", east(5.5))], threshold_m=5.0)

    assert assignment(results) == [None]
    assert results[0].second is None  # tek aday, ikinci yok


def test_a_track_goes_to_one_detection_only() -> None:
    detections = [located(east(0.0)), located(east(0.5))]

    results = match_detections(detections, [point("T0", east(0.2))])

    assert assignment(results) == ["T0", None]


def test_near_equal_distances_are_won_by_the_higher_score() -> None:
    weak, strong = located(east(0.0), 0.3), located(east(0.0), 0.9)

    results = match_detections([weak, strong], [point("T0", east(0.001))])

    assert assignment(results) == [None, "T0"]


# --- Gerçek veri: detections_all.csv (paket yerelde yoksa atlanır) -------------------

STAGE2 = (BACKEND_DIR / "../../stage2").resolve()


@pytest.mark.skipif(not (STAGE2 / "detections_all.csv").is_file(), reason="stage2 veri paketi yok")
def test_real_data_matches_191_of_206_track_points() -> None:
    package = read_package(STAGE2)
    detections = read_detections_csv(STAGE2 / "detections_all.csv")
    with (STAGE2 / "tracks.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    candidates = total = 0
    distances: list[float] = []
    for image in package.images:
        at = image.capture_time.strftime("%H:%M")
        points = [
            TrackPoint(
                r["track_id"], image.capture_time, GeoPoint(float(r["lat"]), float(r["lon"]))
            )
            for r in rows
            if r["time"] == at
        ]
        points = [p for p in points if in_footprint(image, p.location)]
        candidates += len(points)
        items = [
            LocatedDetection(d, pixel_to_geo(image, *d.center_px))
            for d in detections.get(image.image_id, [])
        ]
        for r in match_detections(items, points):
            if r.track:
                total += 1
                distances.append(r.track.distance_m)

    assert candidates == 206
    assert total == 191
    assert statistics.median(distances) == pytest.approx(0.13, abs=0.005)
    assert max(distances) == pytest.approx(1.85, abs=0.005)
