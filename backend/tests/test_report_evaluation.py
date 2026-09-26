"""Değerlendirme servisi: rapor değerlendirme ve asimetrik güven (ticket 06, ADR-0002).

İddialar, sahte veri paketindeki raporlardan GLM-5.3'ün gerçekte çıkardığı iddiaların
aynısıdır; senaryolar bunlara yenilerini ekler.
"""

from dataclasses import replace
from datetime import time
from math import cos, radians
from pathlib import Path
from typing import Any

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
T0122_AT_1405 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0122" and p.time == time(14, 5)
)
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


def test_report_is_compared_with_where_the_vehicle_was_at_report_time() -> None:
    brief = evaluate(FIXTURE_CLAIMS)

    # 12:35'te o noktada T0122 değil, park halindeki T0032 vardı (~38 m).
    f = finding(brief, 2)
    assert f.track_id == "T0032"
    assert f.verdict == "consistent"
    assert f.certainty == "likely"  # "ağır araç" doğrulanamadı: T0032'nin tipi bilinmiyor


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
        time(14, 5),
        OFFICIAL,
        "T0122 dost devriye, kimlik teyitli",
        at(T0122_AT_1405, claim_type="friendly_claim", vehicle_type="truck"),
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
        time(14, 5),
        THIRD,
        "dost devriye",
        at(T0122_AT_1405, claim_type="friendly_claim", vehicle_type="truck"),
    )

    brief = evaluate([friend])

    assert contact(brief, "T0122").final_level == "critical"
    assert contact(brief, "T0122").verified_friend is False
    assert finding(brief, 10).effect == "none"


def test_official_friendly_claim_with_unverifiable_color_does_not_lower_risk() -> None:
    friend = record(
        10,
        time(14, 5),
        OFFICIAL,
        "mavi kamyon dost",
        at(T0122_AT_1405, claim_type="friendly_claim", vehicle_type="truck", color="mavi"),
    )

    brief = evaluate([friend])

    assert contact(brief, "T0122").final_level == "critical"
    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("unverifiable", "none")


def test_official_friendly_claim_with_wrong_type_contradicts() -> None:
    friend = record(
        10,
        time(14, 5),
        OFFICIAL,
        "binek arac dost",
        at(T0122_AT_1405, claim_type="friendly_claim", vehicle_type="car"),
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


def test_report_contradicting_the_contacts_own_track_raises_to_high() -> None:
    package, detections = parked_scene(parked_since=time(14, 0))
    spot = east_of_base(4_000)
    # 13:30'da bu noktada araç olduğunu söylüyor; T7000 o saatte 8 km ötedeydi.
    lie = record(10, time(13, 30), OFFICIAL, "burada 1 arac bekliyor", at(spot, vehicle_type="car"))

    brief = evaluate([lie], package, detections, "img_7000")

    c = contact(brief, "T7000")
    assert c.base_level == "low"
    assert c.final_level == "high"
    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("contradicts", "raises")


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
    lie = record(11, time(13, 30), OFFICIAL, "burada 1 arac", at(spot, vehicle_type="car"))

    brief = evaluate([friend, lie], package, detections, "img_7000")

    assert contact(brief, "T7000").final_level == "high"
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


def test_track_without_a_record_at_report_time_is_not_a_contradiction() -> None:
    package, detections = parked_scene(parked_since=time(14, 0))
    # T7000'in kaydı ancak 13:40'ta başlıyor; 13:30'daki konumu bilinmiyor.
    package = replace(
        package, track_points=[p for p in package.track_points if p.time >= time(13, 40)]
    )
    claim_ = record(10, time(13, 30), OFFICIAL, "burada 1 arac", at(east_of_base(4_000)))

    brief = evaluate([claim_], package, detections, "img_7000")

    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("unverifiable", "none")
    assert contact(brief, "T7000").final_level == contact(brief, "T7000").base_level
