"""Değerlendirme aşamaları: eşleşme ve rapor etkilerinin temaslara bağlanması.

Ana test noktası değerlendirme servisidir; burada yalnızca kuralı ince olan iki aşama
doğrudan sınanır.
"""

from datetime import time
from pathlib import Path

from app.agent import stages
from app.agent.stages import ClaimEvaluations, Contacts, TrackBranch
from app.core.rules import default_rules
from app.data_package import read_package
from app.pipelines.geo import pixel_to_geo
from app.pipelines.motion import Position
from app.pipelines.reports import ClaimEvaluation
from app.schemas.api import ContactFinding, Effect, LatLon, Verdict, VisualFinding
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import (
    Detection,
    FieldReport,
    GeoPoint,
    ReportSource,
    RiskLevel,
    VehicleClass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
[IMAGE] = [m for m in read_package(FIXTURE).images if m.image_id == "img_000860"]
RULES = default_rules()
METERS_PER_DEGREE_LAT = 111_320


def det(confidence: float, x: float, y: float) -> Detection:
    return Detection(label=VehicleClass.TRUCK, confidence=confidence, x=x, y=y, w=20, h=20)


def at_center_of(d: Detection) -> GeoPoint:
    return pixel_to_geo(IMAGE, *d.center_px)


def just_north_of_frame() -> GeoPoint:
    """Karenin dışında ama eşleşme eşiği içinde."""
    c = IMAGE.corners
    meters = RULES.matching.threshold_m / 2
    return GeoPoint(
        c.top_left.lat + meters / METERS_PER_DEGREE_LAT, (c.top_left.lon + c.top_right.lon) / 2
    )


# --- eşleşme -------------------------------------------------------------------------


def test_match_contacts_keeps_tracked_and_strong_detections_and_finds_missed_tracks() -> None:
    strong_tracked = det(0.9, 700, 280)
    weak_tracked = det(0.3, 300, 300)
    weak_alone = det(0.3, 470, 260)
    strong_alone = det(0.9, 100, 100)
    unseen = pixel_to_geo(IMAGE, 850, 450)
    branch = TrackBranch(
        positions=[
            Position("T_STRONG", at_center_of(strong_tracked), estimated=False),
            Position("T_WEAK", at_center_of(weak_tracked), estimated=False),
            Position("T_UNSEEN", unseen, estimated=True),
            Position("T_EDGE", just_north_of_frame(), estimated=False),
        ],
        motions={},
    )
    located = stages.locate(IMAGE, (strong_tracked, weak_tracked, weak_alone, strong_alone))

    result = stages.match_contacts(IMAGE, located, branch, RULES)

    by_box = {m.located.detection: m.track.track_id if m.track else None for m in result.matches}
    assert by_box == {strong_tracked: "T_STRONG", weak_tracked: "T_WEAK", strong_alone: None}
    # Eşleşmeyen zayıf tespit düşer; karenin dışındaki aday kaçırılmış sayılmaz.
    assert [p.track_id for p in result.missed] == ["T_UNSEEN"]
    assert result.estimated == frozenset({"T_UNSEEN"})


# --- rapor etkileri ------------------------------------------------------------------


def contact(track_id: str | None, level: RiskLevel = "medium") -> ContactFinding:
    return ContactFinding(
        kind="matched" if track_id else "unregistered",
        label="truck",
        effective_label="truck",
        confidence=0.9,
        bbox=(1.0, 2.0, 3.0, 4.0) if track_id != "T_NOBOX" else None,
        location=LatLon(lat=39.9, lon=32.8),
        distance_to_base_m=1000.0,
        track_id=track_id,
        base_level=level,
        final_level=level,
        level_reasons=["temel"],
        certainty="certain",
    )


RECORD = ClaimRecord(
    claim_id=1,
    report=FieldReport(time(13, 0), ReportSource.OFFICIAL, "rapor"),
    claim=ReportClaim(
        location_type="coordinate",
        lat=39.9,
        lon=32.8,
        zone=None,
        vehicle_type=None,
        vehicle_count=None,
        color=None,
        behavior=None,
        claim_type="observation",
        time_reference=None,
        is_verifiable=True,
    ),
)


def evaluation(track_id: str | None, verdict: Verdict, effect: Effect) -> ClaimEvaluation:
    return ClaimEvaluation(RECORD, track_id, verdict, "certain", effect, "gerekçe", "ok")


def reports(
    *evaluations: ClaimEvaluation, visuals: stages.Visuals | None = None
) -> ClaimEvaluations:
    return ClaimEvaluations(tuple(evaluations), (), visuals or {})


def applied(c: ContactFinding, *evaluations: ClaimEvaluation) -> ContactFinding:
    [result] = stages.apply_reports(Contacts((c,)), reports(*evaluations)).contacts
    return result


def test_verified_friend_lowers_to_low() -> None:
    result = applied(contact("T1", "high"), evaluation("T1", "consistent", "lowers"))

    assert (result.final_level, result.verified_friend) == ("low", True)
    assert result.base_level == "high"


def test_contradicting_report_keeps_the_level_and_blocks_lowering() -> None:
    """ADR-0002: çelişki seviyeyi değiştirmez, aynı temasın dostluk raporunu da geçersiz kılar."""
    result = applied(
        contact("T1", "high"),
        evaluation("T1", "contradicts", "none"),
        evaluation("T1", "consistent", "lowers"),
    )

    assert (result.final_level, result.verified_friend) == ("high", False)
    assert "rapor tespitle çelişiyor; tespit esas alındı" in result.level_reasons


def test_threat_warning_raises_one_step_overrides_lowering_and_caps_at_critical() -> None:
    raised = applied(
        contact("T1", "medium"),
        evaluation("T1", "consistent", "raises"),
        evaluation("T1", "consistent", "lowers"),
    )
    capped = applied(contact("T1", "critical"), evaluation("T1", "consistent", "raises"))

    assert (raised.final_level, raised.verified_friend) == ("high", False)
    assert capped.final_level == "critical"


def test_report_effects_apply_only_to_the_linked_track() -> None:
    """Başka track'e ya da kayıt dışı temasa bağlı iddianın etkisi seviyeye işlenmez."""
    other = applied(contact("T1"), evaluation("T2", "consistent", "raises"))
    unregistered = applied(contact(None), evaluation(None, "consistent", "raises"))

    assert other.final_level == unregistered.final_level == "medium"
    assert other.level_reasons == unregistered.level_reasons == ["temel"]


def test_visual_findings_are_attached_to_boxed_contacts() -> None:
    seen = VisualFinding(is_vehicle=True, color="beyaz", cargo=None, model="fake/vlm")
    boxed, boxless = contact("T1"), contact("T_NOBOX")

    result = stages.apply_reports(
        Contacts((boxed, boxless)), reports(visuals={(1.0, 2.0, 3.0, 4.0): seen})
    ).contacts

    assert [c.visual for c in result] == [seen, None]
