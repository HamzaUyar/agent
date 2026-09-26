"""Değerlendirme servisi: rapor değerlendirme ve asimetrik güven (ticket 06, ADR-0002).

İddialar, sahte veri paketindeki raporlardan GLM-5.3'ün gerçekte çıkardığı iddiaların
aynısıdır; senaryolar bunlara yenilerini ekler.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import time
from math import cos, radians
from pathlib import Path
from typing import Any

import pytest

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.schemas.api import Brief, ContactFinding, ReportFinding
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import (
    Corners,
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
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
# Dostluk iddiaları çekim anında (14:10) T0122'nin olduğu noktayı ve saati bildirir:
# konum, saat ve tip tutar.
T0122_AT_1410 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0122" and p.time == time(14, 10)
)
AT_CAPTURE = time(14, 10)
OFFICIAL, THIRD = ReportSource.OFFICIAL, ReportSource.THIRD_PARTY


def claim(**overrides: Any) -> ReportClaim:
    base: dict[str, Any] = {
        "location_type": "none",
        "lat": None,
        "lon": None,
        "zone": None,
        "vehicle_type": None,
        "vehicle_count": None,
        "color": None,
        "behavior": None,
        "claim_type": "observation",
        "time_reference": None,
        "is_verifiable": True,
    }
    return ReportClaim.model_validate(base | overrides)


def at(point: GeoPoint, **overrides: Any) -> ReportClaim:
    return claim(location_type="coordinate", lat=point.lat, lon=point.lon, **overrides)


def record(
    claim_id: int, when: time, source: ReportSource, text: str, c: ReportClaim
) -> ClaimRecord:
    return ClaimRecord(claim_id=claim_id, report=FieldReport(when, source, text), claim=c)


# Sahte paketteki raporlar için GLM-5.3'ün 26 Eylül'de çıkardığı iddialar.
SPOT = GeoPoint(39.9253, 32.8718)
FIXTURE_CLAIMS = [
    record(
        1,
        time(11, 55),
        THIRD,
        "Planli tatbikat... dost unsurlar bulunacak.",
        claim(claim_type="friendly_claim", time_reference="gun icinde", is_verifiable=False),
    ),
    record(
        2,
        time(12, 35),
        OFFICIAL,
        "39.9253N 32.8718E cevresinde 1 agir arac...",
        at(SPOT, vehicle_type="heavy", vehicle_count=1, behavior="normal_traffic"),
    ),
    record(
        3,
        time(13, 5),
        OFFICIAL,
        "39.9374N 32.8483E civarinda 1 kamyon goruldu...",
        at(GeoPoint(39.9374, 32.8483), vehicle_type="truck", vehicle_count=1),
    ),
    record(
        4,
        time(13, 40),
        THIRD,
        "39.9253N 32.8718E yakininda mavi bir arac var; dost...",
        at(SPOT, vehicle_type="unknown", vehicle_count=1, color="mavi", behavior="unknown"),
    ),
    record(
        5,
        time(13, 40),
        THIRD,
        "39.9253N 32.8718E yakininda mavi bir arac var; dost...",
        at(
            SPOT, vehicle_type="unknown", vehicle_count=1, color="mavi", claim_type="friendly_claim"
        ),
    ),
    record(
        6,
        time(14, 20),
        OFFICIAL,
        "39.9230N 32.8600E civarinda hizla ilerleyen bir kamyon",
        at(GeoPoint(39.9230, 32.8600), vehicle_type="truck", behavior="moving"),
    ),
]


class FakeDetector:
    version = "test"

    def __init__(self, detections: dict[str, list[Detection]]) -> None:
        self._detections = detections

    def detect(self, image: ImageMeta) -> list[Detection]:
        return list(self._detections.get(image.image_id, []))


def evaluate(
    claims: list[ClaimRecord],
    package: DataPackage = PACKAGE,
    detections: dict[str, list[Detection]] | None = None,
    image_id: str = "img_000860",
) -> Brief:
    repo = InMemoryRepository(package, claims=claims)
    detector = FakeDetector(detections if detections is not None else {"img_000860": [TRUCK]})
    return EvaluationService(repo, detector).run(image_id)


def finding(brief: Brief, claim_id: int) -> ReportFinding:
    [f] = [f for f in brief.report_findings if f.claim_id == claim_id]
    return f


def contact(brief: Brief, track_id: str) -> ContactFinding:
    [c] = [c for c in brief.contacts if c.track_id == track_id]
    return c


# --- Aday seçimi ---------------------------------------------------------------


def test_reports_after_capture_or_far_away_are_not_evaluated() -> None:
    brief = evaluate(FIXTURE_CLAIMS)

    ids = {f.claim_id for f in brief.report_findings}
    assert 6 not in ids  # 14:20, çekim anından sonra (ADR-0001)
    assert 3 not in ids  # 13:05, görüntüden ~2 km uzakta


def test_day_wide_friendly_claim_without_location_is_listed_as_unverifiable() -> None:
    brief = evaluate(FIXTURE_CLAIMS)

    f = finding(brief, 1)
    assert (f.verdict, f.effect, f.track_id) == ("unverifiable", "none", None)


def test_claim_is_bound_to_the_contact_at_its_point_at_capture_time() -> None:
    """Organizatör demosu (12:35): rapor noktası çekim anında T0122'nin konumu.

    Eskiden iddia rapor saatinde o noktada olan araca (park halindeki T0032) bağlanıyordu;
    gerçek veride rapor koordinatları aracın çekim anındaki konumundan üretilmiş.
    """
    brief = evaluate(FIXTURE_CLAIMS)

    f = finding(brief, 2)
    assert f.track_id == "T0122"
    assert (f.verdict, f.effect) == ("consistent", "none")
    # T0122 12:35'te kilometrelerce uzaktaydı: saat tutmuyor, ama risk yükselmiyor.
    assert f.time_check == "mismatch"
    assert contact(brief, "T0122").final_level == contact(brief, "T0122").base_level
    assert "- 12:35 (resmi): tutarlı, saat tutmuyor;" in brief.text


def test_reports_do_not_change_the_reference_levels() -> None:
    brief = evaluate(FIXTURE_CLAIMS)

    assert contact(brief, "T0122").final_level == "critical"
    assert contact(brief, "T0032").final_level == "medium"
    assert brief.risk_level == "critical"


def test_claims_outside_the_window_are_ignored_unless_day_wide() -> None:
    old = record(10, time(11, 0), OFFICIAL, "eski gozlem", at(SPOT, vehicle_type="truck"))

    brief = evaluate([old])

    assert brief.report_findings == []


def test_claim_naming_the_image_zone_is_listed_other_zones_are_not() -> None:
    same = record(
        10,
        time(13, 0),
        OFFICIAL,
        "Dogu Yolu trafik normal",
        claim(location_type="zone", zone="Dogu Yolu", behavior="normal_traffic"),
    )
    other = record(
        11,
        time(13, 0),
        OFFICIAL,
        "Bati Yerlesimi trafik normal",
        claim(location_type="zone", zone="Bati Yerlesimi", behavior="normal_traffic"),
    )

    brief = evaluate([same, other])

    assert [f.claim_id for f in brief.report_findings] == [10]
    assert finding(brief, 10).verdict == "unverifiable"


def test_irrelevant_and_rumor_claims_do_not_affect_risk() -> None:
    rumor = record(10, time(13, 50), THIRD, "duyum", at(SPOT, claim_type="rumor"))
    noise = record(11, time(13, 50), THIRD, "ilgisiz", at(SPOT, claim_type="irrelevant"))

    brief = evaluate([rumor, noise])

    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("unverifiable", "none")
    assert (finding(brief, 11).verdict, finding(brief, 11).effect) == ("irrelevant", "none")


# --- Asimetrik güven (ADR-0002) -------------------------------------------------


def test_official_friendly_claim_matching_everything_makes_a_verified_friend() -> None:
    friend = record(
        10,
        AT_CAPTURE,
        OFFICIAL,
        "T0122 dost devriye, kimlik teyitli",
        at(T0122_AT_1410, claim_type="friendly_claim", vehicle_type="truck"),
    )

    brief = evaluate([friend])

    c = contact(brief, "T0122")
    assert c.base_level == "critical"
    assert c.final_level == "low"
    assert c.verified_friend is True
    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("consistent", "lowers")


def test_third_party_friendly_claim_cannot_lower_risk() -> None:
    friend = record(
        10,
        AT_CAPTURE,
        THIRD,
        "dost devriye",
        at(T0122_AT_1410, claim_type="friendly_claim", vehicle_type="truck"),
    )

    brief = evaluate([friend])

    assert contact(brief, "T0122").final_level == "critical"
    assert contact(brief, "T0122").verified_friend is False
    assert finding(brief, 10).effect == "none"


def test_official_friendly_claim_with_unverifiable_color_does_not_lower_risk() -> None:
    friend = record(
        10,
        AT_CAPTURE,
        OFFICIAL,
        "mavi kamyon dost",
        at(T0122_AT_1410, claim_type="friendly_claim", vehicle_type="truck", color="mavi"),
    )

    brief = evaluate([friend])

    assert contact(brief, "T0122").final_level == "critical"
    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("unverifiable", "none")


def test_official_friendly_claim_with_wrong_type_contradicts() -> None:
    friend = record(
        10,
        AT_CAPTURE,
        OFFICIAL,
        "binek arac dost",
        at(T0122_AT_1410, claim_type="friendly_claim", vehicle_type="car"),
    )

    brief = evaluate([friend])

    assert finding(brief, 10).verdict == "contradicts"
    assert contact(brief, "T0122").final_level == "critical"


# --- Raporun riski yükseltmesi ---------------------------------------------------

BASE = PACKAGE.base.location


def east_of_base(distance_m: float) -> GeoPoint:
    """Üssün `distance_m` doğusu; negatif değer batısı."""
    return GeoPoint(BASE.lat, BASE.lon + distance_m / (111_320 * cos(radians(BASE.lat))))


def parked_scene(parked_since: time) -> tuple[DataPackage, dict[str, list[Detection]]]:
    """Üsse 4 km'de, `parked_since`'ten beri park halindeki araç: temel seviye düşük.

    Öncesinde üssün 4 km batısındaydı: üsse mesafe değişmediği için "yaklaşıyor" sayılmaz.
    """
    spot = east_of_base(4_000)
    far = east_of_base(-4_000)
    points = [
        TrackPoint(
            "T7000", time(h, m), spot if (h, m) >= (parked_since.hour, parked_since.minute) else far
        )
        for h in (12, 13, 14)
        for m in range(0, 60, 5)
        if (h, m) <= (14, 10)
    ]
    dlat, dlon = 0.000303, 0.000701
    image = ImageMeta(
        "img_7000",
        960,
        540,
        time(14, 10),
        Corners(
            GeoPoint(spot.lat + dlat, spot.lon - dlon),
            GeoPoint(spot.lat + dlat, spot.lon + dlon),
            GeoPoint(spot.lat - dlat, spot.lon - dlon),
            GeoPoint(spot.lat - dlat, spot.lon + dlon),
        ),
    )
    box = Detection(VehicleClass.CAR, 0.9, 470, 260, 20, 20)
    package = replace(PACKAGE, images=[image], track_points=points, reports=[])
    return package, {"img_7000": [box]}


def test_observation_whose_report_time_does_not_match_the_track_does_not_raise_risk() -> None:
    """Eskiden "kendi track'iyle çelişiyor → yüksek" sayılıyordu.

    Gerçek veride rapor koordinatları aracın çekim anındaki konumundan üretilmiş; rapor
    saatinde aracın başka yerde olması tek başına yanıltma kanıtı değil, yalnızca not düşülür.
    """
    package, detections = parked_scene(parked_since=time(14, 0))
    spot = east_of_base(4_000)
    # 13:30'da bu noktada araç olduğunu söylüyor; T7000 o saatte 8 km ötedeydi.
    report = record(
        10, time(13, 30), OFFICIAL, "burada 1 arac bekliyor", at(spot, vehicle_type="car")
    )

    brief = evaluate([report], package, detections, "img_7000")

    c = contact(brief, "T7000")
    assert c.final_level == c.base_level == "low"
    f = finding(brief, 10)
    assert (f.track_id, f.verdict, f.effect) == ("T7000", "consistent", "none")
    assert f.time_check == "mismatch"
    assert "uyuşmuyor" in f.reasoning


def test_observation_with_the_wrong_type_contradicts_but_the_detection_decides_the_level() -> None:
    """Görev tanımı s2: çelişki varsa raporu değil tespitinizi esas alın."""
    package, detections = parked_scene(parked_since=time(12, 0))
    lie = record(
        10, time(13, 30), OFFICIAL, "burada 1 kamyon", at(east_of_base(4_000), vehicle_type="truck")
    )

    without = evaluate([], package, detections, "img_7000")
    brief = evaluate([lie], package, detections, "img_7000")

    c = contact(brief, "T7000")
    assert c.final_level == contact(without, "T7000").final_level
    assert "rapor tespitle çelişiyor; tespit esas alındı" in c.level_reasons
    f = finding(brief, 10)
    assert (f.verdict, f.effect) == ("contradicts", "none")
    assert f.reasoning.endswith("tespit esas alındı")


def test_threat_warning_about_a_contact_raises_one_level() -> None:
    package, detections = parked_scene(parked_since=time(12, 0))
    warning = record(
        10,
        time(14, 0),
        OFFICIAL,
        "supheli arac",
        at(east_of_base(4_000), claim_type="threat_warning"),
    )

    brief = evaluate([warning], package, detections, "img_7000")

    assert contact(brief, "T7000").final_level == "medium"
    assert finding(brief, 10).effect == "raises"


def test_contradiction_wins_over_a_verified_friendly_claim() -> None:
    package, detections = parked_scene(parked_since=time(14, 0))
    spot = east_of_base(4_000)
    friend = record(
        10, time(14, 5), OFFICIAL, "dost", at(spot, claim_type="friendly_claim", vehicle_type="car")
    )
    # Eskiden saat çelişkisiyle kurulan yalan artık tip çelişkisiyle kuruluyor.
    lie = record(11, time(13, 30), OFFICIAL, "burada 1 kamyon", at(spot, vehicle_type="truck"))

    without = evaluate([], package, detections, "img_7000")
    brief = evaluate([friend, lie], package, detections, "img_7000")

    # Çelişki seviyeyi yükseltmez ama dostluk iddiasının riski düşürmesini de engeller.
    assert contact(brief, "T7000").final_level == contact(without, "T7000").final_level
    assert contact(brief, "T7000").verified_friend is False


def test_report_step_is_streamed_before_the_risk_step() -> None:
    repo = InMemoryRepository(PACKAGE, claims=FIXTURE_CLAIMS)
    names = [
        e.name
        for e in EvaluationService(repo, FakeDetector({"img_000860": [TRUCK]})).evaluate(
            "img_000860"
        )
    ]

    assert names.index("raporlar") == names.index("risk") - 1


def test_track_without_a_record_at_report_time_leaves_the_time_unknown() -> None:
    package, detections = parked_scene(parked_since=time(14, 0))
    # T7000'in kaydı ancak 13:40'ta başlıyor; 13:30'daki konumu bilinmiyor.
    package = replace(
        package, track_points=[p for p in package.track_points if p.time >= time(13, 40)]
    )
    claim_ = record(10, time(13, 30), OFFICIAL, "burada 1 arac", at(east_of_base(4_000)))

    brief = evaluate([claim_], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.track_id, f.effect, f.time_check) == ("T7000", "none", "unknown")
    assert contact(brief, "T7000").final_level == contact(brief, "T7000").base_level


# --- Çekim anındaki temasa bağlama ------------------------------------------------


def arrival_scene(
    *, car_detected: bool = True
) -> tuple[DataPackage, dict[str, list[Detection]], GeoPoint]:
    """Gerçek verideki 10:20 raporunun kurgusu.

    T0096 (otomobil) 14:10'da noktaya varıyor, öncesinde 8 km batıdaydı. T0019 (kamyon)
    noktanın 20 m doğusunda bütün gün park halinde: rapor saatinde noktaya yakın olan o.
    """
    spot = east_of_base(4_000)
    truck_spot = east_of_base(4_020)
    points = [
        p
        for h in (12, 13, 14)
        for m in range(0, 60, 5)
        if (h, m) <= (14, 10)
        for p in (
            TrackPoint("T0096", time(h, m), spot if (h, m) == (14, 10) else east_of_base(-4_000)),
            TrackPoint("T0019", time(h, m), truck_spot),
        )
    ]
    package, _ = parked_scene(parked_since=time(12, 0))
    package = replace(package, track_points=points)
    boxes = [Detection(VehicleClass.TRUCK, 0.9, 620, 255, 40, 30)]  # merkez 20 m doğuda
    if car_detected:
        boxes.append(Detection(VehicleClass.CAR, 0.9, 470, 260, 20, 20))
    return package, {"img_7000": boxes}, spot


def test_friendly_claim_binds_to_the_arriving_car_not_the_truck_parked_there() -> None:
    """10:20 senaryosu: eskiden park halindeki kamyona bağlanıp onu çelişkili sayıyordu."""
    package, detections, spot = arrival_scene()
    friend = record(
        10,
        time(13, 50),
        OFFICIAL,
        "usse gelen otomobil bize bagli unsurdur",
        at(spot, claim_type="friendly_claim", vehicle_type="car"),
    )

    brief = evaluate([friend], package, detections, "img_7000")

    f = finding(brief, 10)
    assert f.track_id == "T0096"
    # Otomobil 13:50'de orada değildi: saat tutmadığı için dostluk doğrulanamaz.
    assert (f.verdict, f.effect, f.time_check) == ("unverifiable", "none", "mismatch")
    assert "saat 13:50" in f.reasoning
    car, truck = contact(brief, "T0096"), contact(brief, "T0019")
    assert car.verified_friend is False
    assert car.final_level == car.base_level
    assert truck.final_level == truck.base_level


def test_claim_can_bind_to_a_missed_contact_whose_type_is_unknown() -> None:
    package, detections, spot = arrival_scene(car_detected=False)
    report = record(10, time(13, 50), OFFICIAL, "burada 1 otomobil", at(spot, vehicle_type="car"))

    brief = evaluate([report], package, detections, "img_7000")

    f = finding(brief, 10)
    assert contact(brief, "T0096").kind == "missed"
    assert (f.track_id, f.verdict, f.effect) == ("T0096", "consistent", "none")
    assert "tip doğrulanamadı" in f.reasoning


def test_claim_near_the_image_but_far_from_every_contact_is_unverifiable() -> None:
    package, detections = parked_scene(parked_since=time(12, 0))
    # Temastan ~100 m kuzeyde: bağlanma eşiğinin (60 m) dışında, görüntüye ise yakın.
    point = east_of_base(4_000)
    point = GeoPoint(point.lat + 100 / 111_320, point.lon)
    report = record(10, time(13, 50), OFFICIAL, "1 kamyon", at(point, vehicle_type="truck"))

    brief = evaluate([report], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.track_id, f.verdict, f.effect) == (None, "unverifiable", "none")
    assert contact(brief, "T7000").final_level == "low"


def test_report_at_an_off_step_capture_time_is_checked_against_the_current_position() -> None:
    """Çekim 14:12'de: rapor saatindeki konum için 14:10 noktası değil, temasın o anki konumu."""
    spot = east_of_base(4_000)
    # 100 m/dk: 14:10'da noktanın 200 m gerisinde, 14:12'ye kestirilen konumu noktada.
    behind, before = east_of_base(3_800), east_of_base(3_300)
    points = [
        TrackPoint("T0096", time(h, m), before if (h, m) < (14, 10) else behind)
        for h in (12, 13, 14)
        for m in range(0, 60, 5)
        if (h, m) <= (14, 10)
    ]
    package, detections = parked_scene(parked_since=time(12, 0))
    [image] = package.images
    package = replace(
        package, track_points=points, images=[replace(image, capture_time=time(14, 12))]
    )
    friend = record(
        10,
        time(14, 12),
        OFFICIAL,
        "dost",
        at(spot, claim_type="friendly_claim", vehicle_type="car"),
    )

    brief = evaluate([friend], package, detections, "img_7000")

    f = finding(brief, 10)
    assert f.track_id == "T0096"
    assert (f.time_check, f.effect) == ("ok", "lowers")


def test_claims_about_an_unregistered_contact_do_not_claim_an_effect_they_cannot_apply() -> None:
    """Kayıt dışı temasın track'i yok; rapor etkisi seviyesine uygulanamıyor (ADR-0003)."""
    package, detections = parked_scene(parked_since=time(12, 0))
    package = replace(package, track_points=[])
    spot = east_of_base(4_000)
    lie = record(10, time(13, 30), OFFICIAL, "1 kamyon", at(spot, vehicle_type="truck"))
    friend = record(
        11,
        time(14, 10),
        OFFICIAL,
        "dost",
        at(spot, claim_type="friendly_claim", vehicle_type="car"),
    )

    brief = evaluate([lie, friend], package, detections, "img_7000")

    [c] = brief.contacts
    assert c.kind == "unregistered"
    assert c.final_level == c.base_level
    assert c.verified_friend is False
    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("contradicts", "none")
    assert (finding(brief, 11).verdict, finding(brief, 11).effect) == ("unverifiable", "none")


# --- Hareket ve sayı iddiaları ------------------------------------------------------

SPOT_4KM = east_of_base(4_000)


def north_of(point: GeoPoint, distance_m: float) -> GeoPoint:
    return GeoPoint(point.lat + distance_m / 111_320, point.lon)


def moving_scene(
    position_at: Callable[[int], GeoPoint],
    *,
    since: time = time(12, 0),
    label: VehicleClass = VehicleClass.CAR,
    extra_boxes: int = 0,
) -> tuple[DataPackage, dict[str, list[Detection]]]:
    """T0500 `since`'ten 14:10'a; `position_at(dakika)` çekimden kaç dakika önce nerede.

    14:10'da noktası karenin ortasında (SPOT_4KM). `extra_boxes` track'siz komşu araçlar.
    """
    points = [
        TrackPoint("T0500", time(h, m), position_at(14 * 60 + 10 - (h * 60 + m)))
        for h in (12, 13, 14)
        for m in range(0, 60, 5)
        if (since.hour, since.minute) <= (h, m) <= (14, 10)
    ]
    package, _ = parked_scene(parked_since=time(12, 0))
    package = replace(package, track_points=points)
    boxes = [Detection(label, 0.9, 470, 260, 20, 20)]
    boxes += [
        Detection(VehicleClass.CAR, 0.9, 400 + 40 * i, 150, 20, 20) for i in range(extra_boxes)
    ]
    return package, {"img_7000": boxes}


def approaching(minutes_before: int) -> GeoPoint:
    """Son 30 dk'da üsse 2 km yaklaşıyor, öncesinde 6 km'de park halinde."""
    return east_of_base(4_000 + min(minutes_before, 30) * 2_000 / 30)


def receding(minutes_before: int) -> GeoPoint:
    return east_of_base(4_000 - min(minutes_before, 30) * 2_000 / 30)


def parked(minutes_before: int) -> GeoPoint:
    return SPOT_4KM


def test_stationary_claim_about_a_vehicle_approaching_the_base_contradicts() -> None:
    """Gerçek veride 11:05 "5 kamyonun durdugu bildirildi" → T0112 3 m/s ile yaklaşıyor."""
    package, detections = moving_scene(approaching, label=VehicleClass.TRUCK)
    lie = record(
        10,
        time(14, 5),
        OFFICIAL,
        "1 kamyonun durdugu bildirildi",
        at(SPOT_4KM, vehicle_type="truck", behavior="stationary"),
    )

    brief = evaluate([lie], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.track_id, f.verdict, f.effect) == ("T0500", "contradicts", "none")
    assert "hareket" in f.reasoning
    # Seviyeyi track'in kendi hareketi verir (4 km'de yaklaşan kamyon), rapor değil.
    assert contact(brief, "T0500").final_level == contact(brief, "T0500").base_level


def friendly_approach(when: time) -> ClaimRecord:
    return record(
        10,
        when,
        OFFICIAL,
        "usse dogru ilerleyen otomobil planli ikmal aracidir",
        at(SPOT_4KM, claim_type="friendly_claim", vehicle_type="car", behavior="approaching"),
    )


def test_friendly_claim_says_approaching_but_the_vehicle_recedes_contradicts() -> None:
    """Gerçek veride 14:50 dostluk bildirimi: "üsse doğru ilerleyen" T0075 uzaklaşıyor."""
    package, detections = moving_scene(receding)

    brief = evaluate([friendly_approach(time(14, 10))], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.verdict, f.effect) == ("contradicts", "none")
    assert "üsse yaklaşıyor diyor, üsten uzaklaşıyor" in f.reasoning
    assert contact(brief, "T0500").verified_friend is False


def test_friendly_claim_whose_movement_also_matches_verifies_a_friend() -> None:
    package, detections = moving_scene(approaching)

    brief = evaluate([friendly_approach(time(14, 10))], package, detections, "img_7000")

    assert finding(brief, 10).effect == "lowers"
    assert contact(brief, "T0500").verified_friend is True


def test_transit_claim_about_a_vehicle_approaching_the_base_contradicts() -> None:
    package, detections = moving_scene(approaching, label=VehicleClass.TRUCK)
    report = record(10, time(14, 0), THIRD, "transit geciyor", at(SPOT_4KM, behavior="transit"))

    brief = evaluate([report], package, detections, "img_7000")

    assert finding(brief, 10).verdict == "contradicts"


def long_stop_claim(time_reference: str) -> ClaimRecord:
    return record(
        10,
        time(14, 0),
        OFFICIAL,
        "otomobil uzun suredir yerinden ayrilmadi",
        at(SPOT_4KM, behavior="stationary", time_reference=time_reference),
    )


def test_stop_long_enough_for_the_claimed_duration_is_consistent() -> None:
    package, detections = moving_scene(parked)

    brief = evaluate([long_stop_claim("bir saatten uzun suredir")], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.verdict, f.certainty) == ("consistent", "certain")


def test_stop_shorter_than_the_claimed_duration_contradicts() -> None:
    package, detections = moving_scene(lambda m: parked(m) if m <= 20 else east_of_base(6_000))

    brief = evaluate([long_stop_claim("bir saatten uzun suredir")], package, detections, "img_7000")

    f = finding(brief, 10)
    assert f.verdict == "contradicts"
    assert "en az 60 dk" in f.reasoning


def test_stop_that_began_before_the_record_is_at_least_as_long_as_seen() -> None:
    """Kayıt 13:50'de başlıyor ve araç o andan beri duruyor: 60 dk olup olmadığı bilinmez."""
    package, detections = moving_scene(parked, since=time(13, 50))

    brief = evaluate([long_stop_claim("bir saatten uzun suredir")], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.verdict, f.certainty, f.effect) == ("consistent", "likely", "none")


def test_movement_of_an_unregistered_contact_cannot_be_checked() -> None:
    package, detections = moving_scene(parked)
    package = replace(package, track_points=[])

    brief = evaluate([long_stop_claim("uzun suredir")], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.verdict, f.certainty) == ("consistent", "likely")
    assert "hareket doğrulanamadı" in f.reasoning


def count_claim(n: int) -> ClaimRecord:
    return record(10, time(14, 0), OFFICIAL, f"{n} kamyon goruldu", at(SPOT_4KM, vehicle_count=n))


def test_count_far_above_what_is_seen_contradicts_without_raising_risk() -> None:
    """Gerçek veride 11:40 "7 kamyon" noktasında 30 m içinde tek araç var."""
    package, detections = moving_scene(parked)

    brief = evaluate([count_claim(7)], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.verdict, f.certainty, f.effect) == ("contradicts", "likely", "none")
    assert "sayı" in f.reasoning and "1 araç" in f.reasoning
    assert contact(brief, "T0500").final_level == contact(brief, "T0500").base_level


def test_count_close_to_what_is_seen_is_consistent() -> None:
    # Hedef araç + 30 m içinde iki komşu: "5 araç" için yarıdan fazlası görülüyor.
    package, detections = moving_scene(parked, extra_boxes=2)

    brief = evaluate([count_claim(5)], package, detections, "img_7000")

    assert finding(brief, 10).verdict == "consistent"


def test_count_mismatch_alongside_a_movement_mismatch_is_a_certain_contradiction() -> None:
    package, detections = moving_scene(approaching)
    lie = record(
        10,
        time(14, 0),
        OFFICIAL,
        "7 kamyon durdu",
        at(SPOT_4KM, vehicle_count=7, behavior="stationary"),
    )

    brief = evaluate([lie], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.verdict, f.certainty, f.effect) == ("contradicts", "certain", "none")
    assert "hareket" in f.reasoning and "sayı" in f.reasoning


def test_claimed_stop_duration_is_unverified_when_no_stop_is_recorded() -> None:
    """Araç her adımda 60 m ileri geri gidiyor: eğilim "duruyor", 50 m'lik duraklama kaydı yok."""
    package, detections = moving_scene(
        lambda m: SPOT_4KM if (m // 5) % 2 == 0 else north_of(SPOT_4KM, 60)
    )

    brief = evaluate([long_stop_claim("bir saatten uzun")], package, detections, "img_7000")

    f = finding(brief, 10)
    assert (f.verdict, f.certainty) == ("consistent", "likely")


# --- Görev tanımındaki uçtan uca örnek (gorev_tanimi.pdf s2) ---------------------


def pdf_example_scene() -> tuple[DataPackage, dict[str, list[Detection]]]:
    """img_000123, 13:25: kutu (610, 380, 60, 28) → 39.94439, 32.86350; T0187 ~2,5 m."""
    image = ImageMeta(
        "img_000123",
        1360,
        765,
        time(13, 25),
        Corners(
            GeoPoint(39.94510, 32.86200),
            GeoPoint(39.94510, 32.86519),
            GeoPoint(39.94373, 32.86200),
            GeoPoint(39.94373, 32.86519),
        ),
    )
    end = GeoPoint(39.94441, 32.86353)
    # Kuzeyden gelip çekim anında kutunun konumunda biten iz.
    points = [
        TrackPoint(
            "T0187", time(11 + (25 + 5 * i) // 60, (25 + 5 * i) % 60), end_minus(end, 24 - i)
        )
        for i in range(25)
    ]
    package = replace(PACKAGE, images=[image], track_points=points, reports=[])
    truck = Detection(VehicleClass.TRUCK, 0.9, 610, 380, 60, 28)
    return package, {"img_000123": [truck]}


def end_minus(end: GeoPoint, steps: int) -> GeoPoint:
    return GeoPoint(end.lat + steps * 0.0015, end.lon)


def test_pdf_example_report_with_three_decimal_coordinates_binds_to_the_truck() -> None:
    """ "39.944N 32.863E" 3 ondalıklı: nokta tespitten ~61 m uzakta, yuvarlama payı içinde.

    Görev tanımı bu raporu tespitle uyumlu sayıyor; eskiden 60 m eşiğini aşıp
    "doğrulanamaz" kalıyordu.
    """
    package, detections = pdf_example_scene()
    report = record(
        10,
        time(12, 40),
        THIRD,
        "39.944N 32.863E civarinda bir kamyon",
        at(GeoPoint(39.944, 32.863), vehicle_type="truck", vehicle_count=1),
    )

    brief = evaluate([report], package, detections, "img_000123")

    [truck] = brief.contacts
    assert truck.track_id == "T0187"
    assert (truck.location.lat, truck.location.lon) == (
        pytest.approx(39.94439, abs=1e-5),
        pytest.approx(32.86350, abs=1e-5),
    )
    # PDF "~2,5 m" diyor; yuvarlanmış örnek değerlerle 3,0 m.
    assert truck.match_distance_m is not None and truck.match_distance_m < 5
    f = finding(brief, 10)
    assert (f.track_id, f.verdict, f.effect) == ("T0187", "consistent", "none")


def test_five_decimal_coordinates_keep_the_tight_binding_radius() -> None:
    """5 ondalıklı koordinatta pay 1 m'nin altında: 61 m uzaktaki temasa bağlanmaz."""
    package, detections = pdf_example_scene()
    report = record(
        10,
        time(12, 40),
        THIRD,
        "39.94400N 32.86300E civarinda bir kamyon",
        at(GeoPoint(39.944, 32.863), vehicle_type="truck", vehicle_count=1),
    )

    brief = evaluate([report], package, detections, "img_000123")

    f = finding(brief, 10)
    assert (f.track_id, f.verdict) == (None, "unverifiable")
