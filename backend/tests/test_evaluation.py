"""Değerlendirme servisi: ana test noktası.

Beklenen değerler organizatörlerin uçtan uca örneğinden (img_000860) gelir.
"""

from dataclasses import replace
from datetime import time
from pathlib import Path

import pytest

from app.agent.service import EvaluationService, ImageNotFoundError
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.schemas.domain import (
    DataPackage,
    Detection,
    FieldReport,
    GeoPoint,
    ImageMeta,
    ReportSource,
    TrackPoint,
    VehicleClass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"

TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)


class FakeDetector:
    def __init__(self, detections: dict[str, list[Detection]]) -> None:
        self._detections = detections

    def detect(self, image: ImageMeta) -> list[Detection]:
        return list(self._detections.get(image.image_id, []))


@pytest.fixture
def service() -> EvaluationService:
    repo = InMemoryRepository(read_package(FIXTURE))
    return EvaluationService(repo, FakeDetector({"img_000860": [TRUCK]}))


def test_img_000860_truck_is_located_matched_and_critical(service: EvaluationService) -> None:
    brief = service.run("img_000860")

    assert brief.zone == "Dogu Yolu"
    assert brief.capture_time == "14:10"
    [contact] = [c for c in brief.contacts if c.kind == "matched"]
    assert contact.label == "truck"
    assert contact.location.lat == pytest.approx(39.92531, abs=1e-5)
    assert contact.location.lon == pytest.approx(32.87183, abs=1e-5)
    assert contact.track_id == "T0122"
    assert contact.match_distance_m is not None and contact.match_distance_m < 1
    assert contact.second_candidate is not None
    assert contact.second_candidate.track_id == "T0032"
    assert contact.second_candidate.distance_m == pytest.approx(41, abs=1)
    assert contact.motion is not None
    assert contact.motion.distance_to_base_m == pytest.approx(1600, abs=100)
    assert contact.motion.trend == "approaching"
    assert contact.base_level == "critical"
    assert brief.risk_level == "critical"


def test_route_points_carry_their_time_and_stop_at_the_capture_time(
    service: EvaluationService,
) -> None:
    brief = service.run("img_000860")

    [contact] = [c for c in brief.contacts if c.kind == "matched"]
    assert contact.motion is not None
    route = contact.motion.route
    times = [p.time for p in route if p.time is not None]
    assert len(times) == len(route)
    # T0122'nin 14:10'dan sonra da noktaları var; rota çekim anında biter (ADR-0001).
    assert times[0] == "12:10"
    assert times[-1] == "14:10"
    assert times == sorted(times)
    assert (route[-1].lat, route[-1].lon) == pytest.approx((39.92531, 32.87183), abs=1e-5)


def _service_for(package: DataPackage) -> EvaluationService:
    return EvaluationService(InMemoryRepository(package), FakeDetector({"img_000860": [TRUCK]}))


def test_data_after_capture_time_does_not_change_the_brief() -> None:
    package = read_package(FIXTURE)
    far_away = GeoPoint(40.2, 33.2)
    after_capture = replace(
        package,
        track_points=[
            *(
                p if p.time <= time(14, 10) else replace(p, location=far_away)
                for p in package.track_points
            ),
            # Çekim anından sonra, tespitin tam üstünde beliren bir track.
            TrackPoint("T0999", time(14, 15), GeoPoint(39.92531, 32.87183)),
        ],
        reports=[
            *package.reports,
            FieldReport(time(14, 12), ReportSource.OFFICIAL, "39.9253N 32.8718E dost unsur."),
        ],
    )

    assert _service_for(after_capture).run("img_000860") == _service_for(package).run("img_000860")


def test_events_stream_in_order_and_end_with_the_brief(service: EvaluationService) -> None:
    events = list(service.evaluate("img_000860"))

    assert [e.name for e in events] == [
        "goruntu",
        "tespit",
        "konum",
        "eslesme",
        "hareket",
        "raporlar",
        "risk",
        "karar",
        "brief",
    ]
    assert [e.step_no for e in events] == list(range(1, 10))
    assert "T0122" in events[3].summary
    assert events[-1].data["risk_level"] == "critical"


def test_brief_recommends_alarm_and_names_the_contact(service: EvaluationService) -> None:
    brief = service.run("img_000860")

    assert "alarm" in brief.recommended_action
    assert "T0122" in brief.recommended_action
    assert brief.is_fallback is True
    assert "KRİTİK" in brief.text
    assert "hareket: T0122" in brief.sources


def test_image_outside_the_data_set_is_rejected(service: EvaluationService) -> None:
    with pytest.raises(ImageNotFoundError):
        service.run("img_999999")


def test_image_without_detections_reports_the_receding_track_as_missed_and_low(
    service: EvaluationService,
) -> None:
    brief = service.run("img_000100")

    assert brief.zone == "Kuzey Yolu"
    assert [(c.kind, c.track_id) for c in brief.contacts] == [("missed", "T0200")]
    assert brief.contacts[0].motion is not None
    assert brief.contacts[0].motion.trend == "receding"
    assert brief.risk_level == "low"
