"""Değerlendirme servisi: hareket özeti ve temel seviye tablosu (ticket 04).

Senaryolar üssün doğusunda, bilinen mesafelerde kurulan track'lerle yazılır; her biri
görüntünün ortasındaki tek bir temastan oluşur.
"""

import json
from dataclasses import replace
from datetime import time
from math import cos, radians, sin
from pathlib import Path

import pytest

from app.agent.decision import build_input
from app.agent.service import EvaluationService
from app.core.rules import DEFAULT_RULES_PATH, LevelRules, RiskRules, load_rules
from app.data_package import from_minutes, read_package, to_minutes
from app.db.repositories import InMemoryRepository
from app.schemas.api import Brief
from app.schemas.domain import (
    Corners,
    Detection,
    GeoPoint,
    ImageMeta,
    TrackPoint,
    VehicleClass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
BASE = PACKAGE.base.location
NOW = time(14, 10)
START = time(12, 10)


def east_of_base(distance_m: float, north_m: float = 0.0) -> GeoPoint:
    lon_m = 111_320 * cos(radians(BASE.lat))
    return GeoPoint(BASE.lat + north_m / 111_320, BASE.lon + distance_m / lon_m)


def track(track_id: str, start_m: float, now_m: float, north_m: float = 0.0) -> list[TrackPoint]:
    """12:10–14:10 arası, üsse mesafesi `start_m`'den `now_m`'e doğrusal değişen track."""
    first, last = to_minutes(START), to_minutes(NOW)
    points = []
    for m in range(first, last + 1, 5):
        f = (m - first) / (last - first)
        points.append(
            TrackPoint(
                track_id, from_minutes(m), east_of_base(start_m + f * (now_m - start_m), north_m)
            )
        )
    return points


def image_on(center: GeoPoint, image_id: str = "img_test") -> ImageMeta:
    dlat, dlon = 0.000303, 0.000701
    return ImageMeta(
        image_id=image_id,
        width_px=960,
        height_px=540,
        capture_time=NOW,
        corners=Corners(
            top_left=GeoPoint(center.lat + dlat, center.lon - dlon),
            top_right=GeoPoint(center.lat + dlat, center.lon + dlon),
            bottom_left=GeoPoint(center.lat - dlat, center.lon - dlon),
            bottom_right=GeoPoint(center.lat - dlat, center.lon + dlon),
        ),
    )


def box_on(image: ImageMeta, point: GeoPoint, label: VehicleClass) -> Detection:
    c = image.corners
    x = (point.lon - c.top_left.lon) / (c.top_right.lon - c.top_left.lon) * image.width_px
    y = (c.top_left.lat - point.lat) / (c.top_left.lat - c.bottom_left.lat) * image.height_px
    return Detection(label=label, confidence=0.9, x=x - 10, y=y - 10, w=20, h=20)


class FakeDetector:
    version = "test"

    def __init__(self, detections: dict[str, list[Detection]]) -> None:
        self._detections = detections

    def detect(self, image: ImageMeta) -> list[Detection]:
        return list(self._detections.get(image.image_id, []))


def scenario(
    label: VehicleClass | None,
    start_m: float,
    now_m: float,
    rules: RiskRules | None = None,
    with_track: bool = True,
) -> Brief:
    """Tek temaslı senaryo; `label` None ise tespit yok (kaçırılmış temas)."""
    points = track("T9000", start_m, now_m) if with_track else []
    image = image_on(east_of_base(now_m))
    detections = [box_on(image, east_of_base(now_m), label)] if label else []
    package = replace(PACKAGE, images=[image], track_points=points, reports=[])
    service = EvaluationService(
        InMemoryRepository(package), FakeDetector({image.image_id: detections}), rules=rules
    )
    return service.run(image.image_id)


# --- Temel seviye tablosu: her satır ------------------------------------------


@pytest.mark.parametrize(
    ("label", "start_m", "now_m", "expected"),
    [
        pytest.param(VehicleClass.CAR, 2_800, 800, "critical", id="yaklasan-1km-alti-kritik"),
        pytest.param(
            VehicleClass.TRUCK, 3_800, 1_800, "critical", id="yaklasan-agir-2km-alti-kritik"
        ),
        pytest.param(VehicleClass.CAR, 3_800, 1_800, "high", id="yaklasan-binek-2km-alti-yuksek"),
        pytest.param(VehicleClass.CAR, 4_800, 2_800, "high", id="yaklasan-3km-alti-yuksek"),
        pytest.param(VehicleClass.TRUCK, 6_000, 4_000, "medium", id="yaklasan-uzak-orta"),
        pytest.param(VehicleClass.CAR, 2_000, 2_000, "medium", id="uzun-duraklama-3km-alti-orta"),
        pytest.param(VehicleClass.CAR, 4_000, 4_000, "low", id="uzun-duraklama-uzakta-dusuk"),
        pytest.param(VehicleClass.TRUCK, 500, 1_500, "low", id="uzaklasan-dusuk"),
    ],
)
def test_rule_table_row(label: VehicleClass, start_m: float, now_m: float, expected: str) -> None:
    [contact] = scenario(label, start_m, now_m).contacts

    assert contact.base_level == expected


@pytest.mark.parametrize(
    ("now_m", "expected"),
    [
        pytest.param(800, "medium", id="kayit-disi-1km-alti-orta"),
        pytest.param(1_500, "low", id="kayit-disi-1km-ustu-dusuk"),
        pytest.param(2_500, "low", id="kayit-disi-uzak-dusuk"),
    ],
)
def test_rule_table_row_for_unregistered_contacts(now_m: float, expected: str) -> None:
    """Park halindeki araçların hareket kaydı olmayabilir (görev tanımı): track'siz araç
    kendi başına risk değildir; yalnızca üssün hemen yakınındaysa dikkat gerektirir."""
    [contact] = scenario(VehicleClass.CAR, now_m, now_m, with_track=False).contacts

    assert contact.kind == "unregistered"
    assert contact.base_level == expected


def test_unregistered_contact_reason_says_it_may_be_parked() -> None:
    [contact] = scenario(VehicleClass.CAR, 2_500, 2_500, with_track=False).contacts

    assert any("park halinde olabilir" in r for r in contact.level_reasons)


def test_unregistered_threshold_comes_from_the_rules_file(tmp_path: Path) -> None:
    text = DEFAULT_RULES_PATH.read_text(encoding="utf-8").replace(
        "unregistered_alert_m = 1000", "unregistered_alert_m = 3000"
    )
    custom = tmp_path / "rules.toml"
    custom.write_text(text, encoding="utf-8")

    [contact] = scenario(
        VehicleClass.CAR, 2_500, 2_500, with_track=False, rules=load_rules(custom)
    ).contacts

    assert contact.base_level == "medium"


def test_missed_contact_approaching_close_is_critical_without_a_type() -> None:
    [contact] = scenario(None, 2_800, 800).contacts

    assert contact.kind == "missed"
    assert contact.base_level == "critical"


def test_image_level_is_the_highest_contact_level() -> None:
    receding = track("T9001", 500, 1_500)
    approaching = track("T9002", 3_530, 1_530, north_m=25)  # karenin içinde
    image = image_on(east_of_base(1_500, north_m=10))
    detections = [
        box_on(image, east_of_base(1_500), VehicleClass.CAR),
        box_on(image, east_of_base(1_530, north_m=25), VehicleClass.CAR),
    ]
    package = replace(PACKAGE, images=[image], track_points=receding + approaching, reports=[])

    brief = EvaluationService(
        InMemoryRepository(package), FakeDetector({image.image_id: detections})
    ).run(image.image_id)

    assert sorted(c.base_level for c in brief.contacts) == ["high", "low"]
    assert brief.risk_level == "high"


# --- Eşikler ayar dosyasından ------------------------------------------------


def test_default_rules_come_from_the_rules_file() -> None:
    rules = load_rules()

    assert rules.levels.critical_heavy_m == 2_000
    assert rules.levels.loiter_minutes == 30


def test_changed_thresholds_change_the_level() -> None:
    defaults = load_rules()
    stricter = replace(defaults, levels=replace(defaults.levels, critical_heavy_m=1_500))

    assert scenario(VehicleClass.TRUCK, 3_800, 1_800).contacts[0].base_level == "critical"
    assert scenario(VehicleClass.TRUCK, 3_800, 1_800, stricter).contacts[0].base_level == "high"


def test_rules_file_can_be_loaded_from_a_custom_path(tmp_path: Path) -> None:
    text = (Path(__file__).parents[1] / "app" / "core" / "risk_rules.toml").read_text()
    custom = tmp_path / "rules.toml"
    custom.write_text(text.replace("critical_heavy_m = 2000", "critical_heavy_m = 1500"))

    assert load_rules(custom).levels == replace(load_rules().levels, critical_heavy_m=1_500)
    assert isinstance(load_rules(custom).levels, LevelRules)


# --- Hareket özeti: organizatör örneği (T0122) --------------------------------


def test_t0122_motion_summary_matches_the_reference_example() -> None:
    truck = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
    brief = EvaluationService(
        InMemoryRepository(PACKAGE), FakeDetector({"img_000860": [truck]})
    ).run("img_000860")

    [contact] = [c for c in brief.contacts if c.track_id == "T0122"]
    motion = contact.motion
    assert motion is not None
    # Organizatör örneği: 13:15'te 45 dk ve 12:10'da 40 dk bekleme. Hız son 30 dakikadan
    # okunur (görev tanımı s3: tek adımdan değil): 20 dk'sı 13:15 duraklamasının sonu, bu
    # yüzden yalnızca son 10 dakikaya bakan eski ölçümün ~6,4 m/s'si yerine ~2,1 m/s.
    assert motion.recent_speed_mps == pytest.approx(2.1, abs=0.2)
    assert motion.distance_to_base_30min_ago_m is not None
    assert motion.distance_to_base_30min_ago_m > motion.distance_to_base_m  # yaklaşıyor
    stops = {(s.start, s.minutes) for s in motion.stops}
    assert ("12:10", 40) in stops
    assert ("13:15", 45) in stops
    assert motion.heading_deg is not None and 240 <= motion.heading_deg <= 265  # batı-güneybatı
    # Demo 10,5 km diyor; sahte verideki rota daha kısa (~7,8 km).
    assert motion.total_distance_m > 7_000
    assert motion.avg_speed_mps == pytest.approx(motion.total_distance_m / 7_200, rel=1e-6)
    assert motion.zones_passed[-1] == "Dogu Yolu"
    assert len(motion.route) == 25


def test_stationary_contact_has_no_heading_and_one_long_stop() -> None:
    [contact] = scenario(VehicleClass.CAR, 2_000, 2_000).contacts

    assert contact.motion is not None
    assert contact.motion.heading_deg is None
    assert [s.minutes for s in contact.motion.stops] == [120]
    assert contact.motion.recent_speed_mps == pytest.approx(0, abs=0.01)


def test_llm_input_and_brief_carry_the_whole_track_motion_not_a_single_step() -> None:
    """Görev tanımı s3: hız ve yön tek adımdan değil, kaydın tamamından okunur."""
    truck = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
    brief = EvaluationService(
        InMemoryRepository(PACKAGE), FakeDetector({"img_000860": [truck]})
    ).run("img_000860")
    [contact] = [c for c in brief.contacts if c.track_id == "T0122"]
    motion = contact.motion
    assert motion is not None and motion.distance_to_base_30min_ago_m is not None

    payload = json.loads(
        build_input(brief.image_id, brief.zone, brief.capture_time, brief.contacts, [])
    )
    [facts] = [c for c in payload["contacts"] if c["track_id"] == "T0122"]
    assert facts["avg_speed_mps"] == round(motion.avg_speed_mps, 1)
    assert facts["distance_to_base_30min_ago_km"] == round(
        motion.distance_to_base_30min_ago_m / 1000, 2
    )
    assert facts["heading_deg"] == round(motion.heading_deg or 0)

    assert f"2 saatlik ortalama {motion.avg_speed_mps:.1f} m/s" in brief.text
    assert f"30 dk önce {motion.distance_to_base_30min_ago_m / 1000:.1f} km" in brief.text


# --- Üs çevresinde dolaşma (görev tanımı s3) -------------------------------------


def around_base(radius_m: float, arc_m: float) -> list[TrackPoint]:
    """12:10–14:10 arası, üssü `radius_m` uzaklıkta, `arc_m` uzunluğunda bir yay üzerinde
    gidip gelen track: üsse mesafesi hiç değişmez."""
    first, last = to_minutes(START), to_minutes(NOW)
    points = []
    for i, m in enumerate(range(first, last + 1, 5)):
        # 0 → arc → 0 → arc ... her 6 adımda bir yön değiştirir.
        leg, step = divmod(i, 6)
        along = (step if leg % 2 == 0 else 6 - step) / 6 * arc_m
        angle = along / radius_m
        points.append(
            TrackPoint(
                "T9000",
                from_minutes(m),
                east_of_base(radius_m * cos(angle), radius_m * sin(angle)),
            )
        )
    return points


def circling_scenario(radius_m: float, arc_m: float) -> Brief:
    points = around_base(radius_m, arc_m)
    now = points[-1].location
    image = image_on(now)
    package = replace(PACKAGE, images=[image], track_points=points, reports=[])
    service = EvaluationService(
        InMemoryRepository(package),
        FakeDetector({image.image_id: [box_on(image, now, VehicleClass.CAR)]}),
    )
    return service.run(image.image_id)


def test_vehicle_circling_the_base_at_a_steady_distance_is_medium() -> None:
    """Gerçek veride T0035, T0146, T0181: üsse ~1,7 km'de, mesafesi 20 m oynayarak 20 km yol."""
    [contact] = circling_scenario(radius_m=1_800, arc_m=3_000).contacts

    assert contact.motion is not None
    assert contact.motion.trend != "approaching"
    assert contact.motion.base_distance_max_m - contact.motion.base_distance_min_m < 50
    assert contact.base_level == "medium"
    assert "üs çevresinde sabit mesafede dolaşıyor" in contact.level_reasons[0]


def test_local_back_and_forth_traffic_is_not_circling() -> None:
    """Yerinde gidip gelen yerel trafik (600 m içinde) üssü dolaşmıyor."""
    [contact] = circling_scenario(radius_m=1_800, arc_m=500).contacts

    assert contact.base_level == "low"


def test_circling_far_from_the_base_is_not_circling_the_base() -> None:
    [contact] = circling_scenario(radius_m=4_000, arc_m=3_000).contacts

    assert contact.base_level == "low"
