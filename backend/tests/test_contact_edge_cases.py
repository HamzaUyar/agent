"""Değerlendirme servisi: temas kenar durumları (ticket 03).

Aynı test noktası (değerlendirme servisi); sahte veri paketi senaryoya göre değiştirilir.
"""

from dataclasses import replace
from datetime import time
from pathlib import Path

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.schemas.api import Brief, ContactFinding
from app.schemas.domain import (
    Corners,
    DataPackage,
    Detection,
    GeoPoint,
    ImageMeta,
    TrackPoint,
    VehicleClass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"

# Organizatör örneğindeki kutu; merkezi 14:10'da T0122'nin konumuna düşer.
TRUCK_BOX = {"x": 727, "y": 284, "w": 58, "h": 34}
T0032_AT = GeoPoint(39.925310, 32.871350)  # karenin içinde, tespit edilmeyen araç
T0122_AT_1400 = GeoPoint(39.936000, 32.915000)  # 13:15–14:00 arası bekleme noktası


def det(label: VehicleClass, confidence: float, **box: float) -> Detection:
    return Detection(label=label, confidence=confidence, **(box or TRUCK_BOX))


def centered_box() -> dict[str, float]:
    """960×540 karenin tam ortasına düşen kutu."""
    return {"x": 470, "y": 260, "w": 20, "h": 20}


def image_at(image_id: str, at: time, center: GeoPoint) -> ImageMeta:
    dlat, dlon = 0.000303, 0.000701
    return ImageMeta(
        image_id=image_id,
        width_px=960,
        height_px=540,
        capture_time=at,
        corners=Corners(
            top_left=GeoPoint(center.lat + dlat, center.lon - dlon),
            top_right=GeoPoint(center.lat + dlat, center.lon + dlon),
            bottom_left=GeoPoint(center.lat - dlat, center.lon - dlon),
            bottom_right=GeoPoint(center.lat - dlat, center.lon + dlon),
        ),
    )


class FakeDetector:
    def __init__(self, detections: dict[str, list[Detection]]) -> None:
        self._detections = detections

    def detect(self, image: ImageMeta) -> list[Detection]:
        return list(self._detections.get(image.image_id, []))


def evaluate(
    detections: dict[str, list[Detection]],
    package: DataPackage | None = None,
    image_id: str = "img_000860",
) -> Brief:
    repo = InMemoryRepository(package or read_package(FIXTURE))
    return EvaluationService(repo, FakeDetector(detections)).run(image_id)


def only(brief: Brief, kind: str) -> ContactFinding:
    [contact] = [c for c in brief.contacts if c.kind == kind]
    return contact


# --- Zayıf tespit -------------------------------------------------------------


def test_weak_detection_that_matches_a_track_is_a_contact_marked_weak() -> None:
    brief = evaluate({"img_000860": [det(VehicleClass.TRUCK, 0.35)]})

    contact = only(brief, "matched")
    assert contact.track_id == "T0122"
    assert contact.is_weak is True
    assert contact.certainty == "weak"


def test_weak_detection_without_a_track_is_ignored() -> None:
    far_box = {"x": 20, "y": 500, "w": 20, "h": 20}  # sol alt köşe, yakınında track yok
    brief = evaluate({"img_000860": [det(VehicleClass.CAR, 0.35, **far_box)]})

    assert [c for c in brief.contacts if c.kind != "missed"] == []


def test_detection_below_minimum_confidence_is_ignored_even_on_a_track() -> None:
    brief = evaluate({"img_000860": [det(VehicleClass.TRUCK, 0.20)]})

    assert [c.kind for c in brief.contacts if c.track_id == "T0122"] == ["missed"]


# --- Kayıt dışı ve kaçırılmış temas -------------------------------------------


def test_strong_detection_without_a_track_is_an_unregistered_contact() -> None:
    far_box = {"x": 20, "y": 500, "w": 20, "h": 20}
    brief = evaluate({"img_000860": [det(VehicleClass.CAR, 0.8, **far_box)]})

    contact = only(brief, "unregistered")
    assert contact.track_id is None
    assert contact.motion is None
    assert contact.base_level == "low"  # kayıt dışı, üsse ~1,6 km: park halinde olabilir


def test_track_inside_the_frame_without_a_detection_is_a_missed_contact() -> None:
    brief = evaluate({"img_000860": [det(VehicleClass.TRUCK, 0.9)]})

    missed = only(brief, "missed")
    assert missed.track_id == "T0032"
    assert missed.label is None
    assert missed.location.lat == T0032_AT.lat
    assert missed.location.lon == T0032_AT.lon
    assert missed.motion is not None and missed.motion.trend == "stationary"
    assert missed.base_level == "medium"  # üsse 1,6 km'de iki saattir park halinde


def test_track_outside_the_frame_is_not_a_missed_contact() -> None:
    brief = evaluate({"img_000860": [det(VehicleClass.TRUCK, 0.9)]})

    assert all(c.track_id != "T0200" for c in brief.contacts)


# --- Belirsiz eşleşme ---------------------------------------------------------


def test_two_tracks_within_the_threshold_make_an_ambiguous_match() -> None:
    package = read_package(FIXTURE)
    near_truck = GeoPoint(39.925310, 32.871900)  # T0122'nin 14:10 konumuna ~6 m
    package = replace(
        package, track_points=[*package.track_points, TrackPoint("T0500", time(14, 10), near_truck)]
    )

    contact = only(evaluate({"img_000860": [det(VehicleClass.TRUCK, 0.9)]}, package), "matched")

    assert contact.track_id == "T0122"
    assert contact.is_ambiguous is True
    assert contact.second_candidate is not None
    assert contact.second_candidate.track_id == "T0500"
    assert contact.certainty == "likely"


def test_single_track_within_the_threshold_is_not_ambiguous() -> None:
    contact = only(evaluate({"img_000860": [det(VehicleClass.TRUCK, 0.9)]}), "matched")

    assert contact.is_ambiguous is False
    assert contact.certainty == "certain"


# --- Adım dışı çekim saati ----------------------------------------------------


def test_off_step_capture_time_estimates_track_positions_without_future_points() -> None:
    package = read_package(FIXTURE)
    image = image_at("img_000900", time(14, 12), T0032_AT)
    far_away = GeoPoint(40.2, 33.2)
    package = replace(
        package,
        images=[*package.images, image],
        # 14:10 sonrası noktalar uzaklara taşınır: kestirim onları kullanmamalı (ADR-0001).
        track_points=[
            p if p.time <= time(14, 10) else replace(p, location=far_away)
            for p in package.track_points
        ],
    )

    brief = evaluate(
        {"img_000900": [det(VehicleClass.CAR, 0.9, **centered_box())]}, package, "img_000900"
    )

    contact = only(brief, "matched")
    assert contact.track_id == "T0032"
    assert contact.position_estimated is True
    assert contact.certainty == "likely"


# --- Farklı karelerde tip çelişkisi -------------------------------------------


def test_type_conflict_across_earlier_frames_uses_the_riskier_type() -> None:
    package = read_package(FIXTURE)
    earlier_truck = image_at("img_000850", time(14, 0), T0122_AT_1400)
    package = replace(package, images=[*package.images, earlier_truck])

    brief = evaluate(
        {
            "img_000850": [det(VehicleClass.TRUCK, 0.9, **centered_box())],
            "img_000860": [det(VehicleClass.CAR, 0.9)],
        },
        package,
    )

    contact = only(brief, "matched")
    assert contact.label == "car"
    assert contact.type_conflict is True
    assert contact.effective_label == "truck"
    assert {(o.image_id, o.label) for o in contact.observed_labels} == {
        ("img_000850", "truck"),
        ("img_000860", "car"),
    }
    # Car olsaydı "yüksek"; truck kabul edildiği için ağır araç kuralıyla kritik.
    assert contact.base_level == "critical"


def test_frames_after_the_capture_time_are_not_used_for_type_history() -> None:
    package = read_package(FIXTURE)
    later = image_at("img_000870", time(14, 30), GeoPoint(39.923000, 32.860000))
    package = replace(package, images=[*package.images, later])

    brief = evaluate(
        {
            "img_000860": [det(VehicleClass.CAR, 0.9)],
            "img_000870": [det(VehicleClass.TRUCK, 0.9, **centered_box())],
        },
        package,
    )

    contact = only(brief, "matched")
    assert contact.type_conflict is False
    assert contact.effective_label == "car"
    assert contact.base_level == "high"
