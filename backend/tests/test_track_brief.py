"""Görüntüsüz track değerlendirmesi (app/agent/track_brief)."""

from datetime import time

from pydantic import BaseModel

from app.agent.track_brief import (
    TrackBriefDraft,
    level_origin,
    related_claims,
    text_problem,
    track_facts,
    unsupported_numbers,
    write_track_brief,
)
from app.risk_engine import Point, default_config, run_track
from app.schemas.api import MotionFinding
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import FieldReport, GeoPoint, ReportSource

CFG = default_config()
RISK = run_track(
    "T9000", [Point(600 + 5 * i, 4_000 - 110 * i, 0) for i in range(25)], None, None, CFG
)
MOTION = MotionFinding(
    distance_to_base_m=1_360,
    distance_to_base_30min_ago_m=2_020,
    distance_to_base_60min_ago_m=2_680,
    trend="approaching",
    route=[],
    total_distance_m=2_640,
    avg_speed_mps=0.4,
    recent_speed_mps=0.4,
    heading_deg=270,
    stops=[],
    zones_passed=[],
    base_distance_min_m=1_360,
    base_distance_max_m=4_000,
    extent_m=2_640,
    current_stop_minutes=None,
    stop_open_ended=False,
)


class FakeRouter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete_json(
        self, task: str, system: str, user: str, schema: type[BaseModel], max_tokens: int
    ) -> tuple[BaseModel, str]:
        self.calls += 1
        assert task == "track_brief"
        return TrackBriefDraft(ozet=self.text), "test/model"


def claim(lat: float, lon: float, text: str) -> ClaimRecord:
    report = FieldReport(time=time(11, 0), source=ReportSource.THIRD_PARTY, text=text)
    return ClaimRecord(
        claim_id=1,
        report=report,
        claim=ReportClaim(
            location_type="coordinate",
            lat=lat,
            lon=lon,
            zone=None,
            vehicle_type=None,
            vehicle_count=None,
            color=None,
            claim_type="observation",
            behavior="unknown",
            time_reference=None,
            is_verifiable=True,
        ),
    )


def test_facts_carry_level_history_and_the_closest_pass() -> None:
    facts = track_facts(RISK, MOTION, [])

    assert "görüntüsüz" in facts
    assert "seviye_gecmisi:" in facts and "kritik" in facts
    assert "en_yakin_gecis:" in facts


def test_only_reports_near_the_track_are_attached() -> None:
    near = claim(39.9, 32.8, "yakında kamyon")
    far = claim(40.5, 33.5, "uzakta kamyon")

    related = related_claims([("T9000", GeoPoint(39.9, 32.8001))], [near, far])

    assert [r.report.text for r, _ in related] == ["yakında kamyon"]


def test_numbers_not_in_the_facts_are_rejected() -> None:
    assert unsupported_numbers("üsse 1,4 km'de, 7 araç", "uzaklik: 1,4 km") == ["7"]
    assert unsupported_numbers("üsse 1.4 km", "uzaklik: 1,4 km") == []


def test_llm_text_with_an_invented_number_falls_back_to_the_rule_summary() -> None:
    router = FakeRouter("Araç 99 km/sa hızla üsse yaklaşıyor, izlenmeli ve doğrulanmalı.")

    brief = write_track_brief(router, RISK, MOTION, [], timeout_s=5, max_tokens=500)  # type: ignore[arg-type]

    assert brief.is_fallback and brief.rejected is not None and "99" in brief.rejected
    assert brief.text.startswith("Görüntüsüz track")


def test_grounded_llm_text_is_kept_and_level_comes_from_the_engine() -> None:
    router = FakeRouter("Araç üsse yaklaşmaya devam ediyor; kadraj dışında olduğu için izlenmeli.")

    brief = write_track_brief(router, RISK, MOTION, [], timeout_s=5, max_tokens=500)  # type: ignore[arg-type]

    assert not brief.is_fallback and brief.model == "test/model"
    assert brief.level == "critical" and brief.code == RISK.current.code


def test_without_llm_the_rule_summary_is_used() -> None:
    brief = write_track_brief(None, RISK, MOTION, [], timeout_s=5, max_tokens=500)

    assert brief.is_fallback and brief.rejected is None


def test_held_level_is_explained_by_the_rule_it_was_entered_with() -> None:
    approach = [Point(600 + 5 * i, 4_000 - 225 * i, 0) for i in range(13)]
    retreat = [Point(approach[-1].t + 5 * i, 1_300 + 450 * i, 0) for i in range(1, 3)]
    risk = run_track("T9001", approach + retreat, None, None, CFG)

    assert risk.current.held and risk.current.level == 3
    origin = level_origin(risk)
    assert "1,5 km içinde" in origin and "iniş beklemesinde" in origin


def test_long_or_coordinate_text_is_rejected() -> None:
    facts = "uzaklik: 1,4 km"
    assert text_problem("Bir. İki. Üç. Dört. Beş.", facts) is not None
    assert text_problem("Araç 39.94643N civarında.", "39.94643N") == "metinde koordinat var"
    assert text_problem("Araç üsse 1,4 km'de, izlenmeli.", facts) is None
