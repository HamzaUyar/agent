"""Değerlendirme servisi: LLM karar ayarı ve brief yazarı (ticket 07, ADR-0002).

LLM sahte sağlayıcıdan cevap verir; ±1 kademe ve kanıtlı düşürme kuralları, yedek
modele geçiş, zaman sınırı ve otomatik özet gerçek kodla çalışır.
"""

import time as clock
from datetime import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.llm.client import LLMRouter, load_model_config
from app.schemas.api import Brief
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import Detection, FieldReport, ImageMeta, ReportSource, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
CONFIG = load_model_config()
CHAIN = [CONFIG.models[name] for name in CONFIG.tasks["reasoning"]]
PRIMARY, FALLBACK = CHAIN[0], CHAIN[1]

# img_000860: K1 = T0122 (truck, KRİTİK), K2 = T0032 (kaçırılmış, ORTA).
T0032_AT_1235 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0032" and p.time == time(12, 35)
)
CONSISTENT_CLAIM = ClaimRecord(
    claim_id=2,
    report=FieldReport(time(12, 35), ReportSource.OFFICIAL, "1 agir arac, hareketleri olagan"),
    claim=ReportClaim(
        location_type="coordinate",
        lat=T0032_AT_1235.lat,
        lon=T0032_AT_1235.lon,
        zone=None,
        vehicle_type=None,
        vehicle_count=1,
        color=None,
        behavior="normal_traffic",
        claim_type="observation",
        time_reference=None,
        is_verifiable=True,
    ),
)


class FakeDetector:
    version = "test"

    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK] if image.image_id == "img_000860" else []


class FakeProvider:
    def __init__(self, reply: Any = None, *, delay_s: float = 0.0, available: bool = True) -> None:
        self.reply = reply
        self.delay_s = delay_s
        self.available = available
        self.calls = 0

    def is_available(self) -> bool:
        return self.available

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int,
        extra_body: object = None,
    ) -> BaseModel:
        self.calls += 1
        if self.delay_s:
            clock.sleep(self.delay_s)
        if isinstance(self.reply, Exception):
            raise self.reply
        return schema.model_validate(self.reply)


def draft(
    adjustments: list[dict[str, Any]], assessment: str = "T0122 üsse yaklaşıyor."
) -> dict[str, Any]:
    return {"adjustments": adjustments, "assessment": assessment}


def run(
    primary: FakeProvider | None,
    fallback: FakeProvider | None = None,
    *,
    claims: list[ClaimRecord] | None = None,
    timeout_s: float | None = None,
) -> Brief:
    router = None
    if primary is not None:
        providers = {e.provider: FakeProvider(available=False) for e in CHAIN}
        providers[PRIMARY.provider] = primary
        providers[FALLBACK.provider] = fallback or FakeProvider(available=False)
        router = LLMRouter(CONFIG, providers)
    service = EvaluationService(
        InMemoryRepository(PACKAGE, claims=claims or []),
        FakeDetector(),
        router=router,
        brief_timeout_s=timeout_s,
    )
    return service.run("img_000860")


def level_of(brief: Brief, track_id: str) -> tuple[str, str]:
    [c] = [c for c in brief.contacts if c.track_id == track_id]
    return c.base_level, c.final_level


def test_llm_can_raise_a_level_by_one_with_a_reason() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    {
                        "contact": "K2",
                        "level": "high",
                        "reason": "üsse yakın park",
                        "evidence_claim_ids": [],
                    }
                ]
            )
        )
    )

    assert level_of(brief, "T0032") == ("medium", "high")
    [c] = [c for c in brief.contacts if c.track_id == "T0032"]
    assert c.adjustment_reason == "üsse yakın park"
    assert brief.is_fallback is False
    assert brief.model == f"{PRIMARY.provider}/{PRIMARY.model_id}"


def test_llm_assessment_is_in_the_brief_text_with_code_generated_header_and_action() -> None:
    brief = run(FakeProvider(draft([], assessment="T0122 üsse hızla yaklaşan bir kamyon.")))

    assert "T0122 üsse hızla yaklaşan bir kamyon." in brief.text
    assert brief.text.splitlines()[0].startswith("img_000860 · Dogu Yolu · 14:10 · Risk: KRİTİK")
    assert f"Önerilen eylem: {brief.recommended_action}" in brief.text
    assert "otomatik özet" not in brief.text


def test_jump_of_more_than_one_level_is_rejected() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    {
                        "contact": "K2",
                        "level": "low",
                        "reason": "zararsız",
                        "evidence_claim_ids": [2],
                    },
                    {
                        "contact": "K1",
                        "level": "medium",
                        "reason": "sadece kamyon",
                        "evidence_claim_ids": [],
                    },
                ]
            )
        ),
        claims=[CONSISTENT_CLAIM],
    )

    assert level_of(brief, "T0122") == ("critical", "critical")
    [c] = [c for c in brief.contacts if c.track_id == "T0122"]
    assert c.adjustment_rejected is not None and "bir kademe" in c.adjustment_rejected


def test_lowering_without_evidence_is_rejected() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    {
                        "contact": "K2",
                        "level": "low",
                        "reason": "park etmiş sivil",
                        "evidence_claim_ids": [],
                    }
                ]
            )
        )
    )

    assert level_of(brief, "T0032") == ("medium", "medium")
    [c] = [c for c in brief.contacts if c.track_id == "T0032"]
    assert c.adjustment_rejected is not None and "kanıt" in c.adjustment_rejected


def test_lowering_with_a_consistent_claim_about_that_contact_is_accepted() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    {
                        "contact": "K2",
                        "level": "low",
                        "reason": "resmi rapor olağan diyor",
                        "evidence_claim_ids": [2],
                    }
                ]
            )
        ),
        claims=[CONSISTENT_CLAIM],
    )

    assert level_of(brief, "T0032") == ("medium", "low")


def test_lowering_citing_a_claim_about_another_contact_is_rejected() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    {
                        "contact": "K1",
                        "level": "high",
                        "reason": "rapor olağan diyor",
                        "evidence_claim_ids": [2],
                    }
                ]
            )
        ),
        claims=[CONSISTENT_CLAIM],
    )

    assert level_of(brief, "T0122") == ("critical", "critical")


def test_image_level_and_action_follow_the_final_levels() -> None:
    brief = run(
        FakeProvider(
            draft([{"contact": "K1", "level": "high", "reason": "x", "evidence_claim_ids": [2]}])
        ),
        claims=[ClaimRecord(3, CONSISTENT_CLAIM.report, CONSISTENT_CLAIM.claim)],
    )

    assert brief.risk_level == "critical"  # K1 düşürülemedi (kanıt başka temasa ait)
    assert "alarm" in brief.recommended_action


def test_failing_primary_falls_back_to_the_next_model() -> None:
    brief = run(FakeProvider(RuntimeError("503")), FakeProvider(draft([])))

    assert brief.is_fallback is False
    assert brief.model == f"{FALLBACK.provider}/{FALLBACK.model_id}"


def test_all_models_failing_gives_the_automatic_summary_with_code_levels() -> None:
    brief = run(FakeProvider(RuntimeError("503")), FakeProvider(RuntimeError("timeout")))

    assert brief.is_fallback is True
    assert brief.fallback_reason is not None
    assert "otomatik özet" in brief.text
    assert level_of(brief, "T0122") == ("critical", "critical")


def test_slow_llm_hits_the_time_limit_and_gives_the_automatic_summary() -> None:
    brief = run(FakeProvider(draft([]), delay_s=1.0), timeout_s=0.1)

    assert brief.is_fallback is True
    assert brief.fallback_reason is not None and "zaman" in brief.fallback_reason


def test_without_an_llm_the_brief_is_the_automatic_summary() -> None:
    brief = run(None)

    assert brief.is_fallback is True
    assert brief.model is None


def test_decision_step_is_streamed_between_risk_and_brief() -> None:
    service = EvaluationService(
        InMemoryRepository(PACKAGE),
        FakeDetector(),
        router=LLMRouter(CONFIG, {PRIMARY.provider: FakeProvider(draft([]))}),
    )
    names = [e.name for e in service.evaluate("img_000860")]

    assert names[-3:] == ["risk", "karar", "brief"]


PLACEHOLDERS = ["", "   ", "...", "…", "-", "Değerlendirme:", "T0122."]


@pytest.mark.parametrize("empty", PLACEHOLDERS)
def test_empty_or_placeholder_assessment_falls_through_to_the_next_model(empty: str) -> None:
    primary = FakeProvider(draft([], assessment=empty))
    fallback = FakeProvider(draft([], assessment="T0122 üsse yaklaşan kamyon; kritik."))

    brief = run(primary, fallback)

    assert brief.model == f"{FALLBACK.provider}/{FALLBACK.model_id}"
    assert "Değerlendirme: T0122 üsse yaklaşan kamyon; kritik." in brief.text


def test_no_model_writing_a_real_assessment_gives_the_automatic_summary() -> None:
    brief = run(FakeProvider(draft([], assessment="...")), FakeProvider(draft([], assessment="")))

    assert brief.is_fallback is True
    assert brief.model is None
    assert brief.fallback_reason == "kullanılabilir model yok"
    assert "(otomatik özet)" in brief.text


def test_llm_cannot_lower_a_contact_that_a_report_has_raised() -> None:
    contradiction = ClaimRecord(
        claim_id=9,
        report=FieldReport(time(13, 0), ReportSource.OFFICIAL, "burada kamyon var"),
        claim=CONSISTENT_CLAIM.claim.model_copy(update={"claim_type": "threat_warning"}),
    )
    brief = run(
        FakeProvider(
            draft(
                [
                    {
                        "contact": "K2",
                        "level": "medium",
                        "reason": "olağan",
                        "evidence_claim_ids": [2],
                    }
                ]
            )
        ),
        claims=[CONSISTENT_CLAIM, contradiction],
    )

    base, final = level_of(brief, "T0032")
    assert (base, final) == ("medium", "high")  # tehdit uyarısı +1; LLM düşüremedi
    [c] = [c for c in brief.contacts if c.track_id == "T0032"]
    assert c.adjustment_rejected is not None and "yükseltti" in c.adjustment_rejected


def test_lowering_citing_a_claim_whose_report_time_does_not_match_is_rejected() -> None:
    """İddia T0122'nin çekim anındaki noktasını gösteriyor ama T0122 12:35'te orada değildi."""
    t0122_now = next(
        p.location for p in PACKAGE.track_points if p.track_id == "T0122" and p.time == time(14, 10)
    )
    stale = ClaimRecord(
        claim_id=7,
        report=FieldReport(time(12, 35), ReportSource.OFFICIAL, "1 agir arac, hareketleri olagan"),
        claim=CONSISTENT_CLAIM.claim.model_copy(
            update={"lat": t0122_now.lat, "lon": t0122_now.lon}
        ),
    )
    brief = run(
        FakeProvider(
            draft(
                [
                    {
                        "contact": "K1",
                        "level": "high",
                        "reason": "resmi rapor olağan diyor",
                        "evidence_claim_ids": [7],
                    }
                ]
            )
        ),
        claims=[stale],
    )

    assert level_of(brief, "T0122") == ("critical", "critical")
    [c] = [c for c in brief.contacts if c.track_id == "T0122"]
    assert c.adjustment_rejected is not None and "saat" in c.adjustment_rejected
