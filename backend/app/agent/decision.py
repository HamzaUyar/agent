"""LLM karar ayarı (ADR-0002): kodun seviyesini en fazla bir kademe, gerekçesiyle değiştirir.

LLM önerir, kod doğrular. Bir kademeden fazla değişiklik ve kanıtsız düşürme reddedilir.
Düşürme için kanıt, o temasa bağlı ve kararı "consistent" olan bir rapor iddiasıdır.
LLM cevap vermezse ya da süre aşılırsa `DecisionUnavailableError` fırlatılır; servis
otomatik özete geçer.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from app.llm.client import LLMRouter, LLMUnavailableError
from app.pipelines.risk import LEVELS
from app.schemas.api import ContactFinding, ReportFinding
from app.schemas.domain import RiskLevel

TASK = "reasoning"
PROMPT_PATH = Path(__file__).parent / "prompts" / "brief.md"


class LevelProposal(BaseModel):
    contact: str = Field(description="Temas etiketi (K1, K2, ...)")
    level: RiskLevel
    reason: str
    evidence_claim_ids: list[int] = Field(
        description="Düşürme için: bu temasa bağlı, kararı consistent olan iddiaların kimlikleri"
    )


class DecisionDraft(BaseModel):
    adjustments: list[LevelProposal]
    assessment: str = Field(description="Operatör için kısa Türkçe değerlendirme")


class DecisionUnavailableError(RuntimeError):
    """LLM kararı alınamadı; sebep otomatik özette gösterilir."""


@dataclass(frozen=True)
class Decision:
    contacts: list[ContactFinding]
    assessment: str
    model: str
    accepted: int
    rejected: int


def contact_ref(index: int) -> str:
    return f"K{index + 1}"


def _contact_facts(i: int, c: ContactFinding) -> dict[str, object]:
    motion = c.motion
    return {
        "ref": contact_ref(i),
        "kind": c.kind,
        "track_id": c.track_id,
        "type": c.effective_label,
        "certainty": c.certainty,
        "distance_to_base_km": round(c.distance_to_base_m / 1000, 2),
        "trend": motion.trend if motion else None,
        "recent_speed_mps": round(motion.recent_speed_mps, 1) if motion else None,
        "stops": [
            f"{s.start} ({s.minutes} dk, üsse {s.distance_to_base_m / 1000:.1f} km)"
            for s in motion.stops
        ]
        if motion
        else [],
        "level": c.final_level,
        "level_reasons": c.level_reasons,
        "verified_friend": c.verified_friend,
        "visual": c.visual.model_dump(exclude={"model"}) if c.visual else None,
        "notes": {
            "weak_detection": c.is_weak,
            "ambiguous_match": c.is_ambiguous,
            "type_conflict": c.type_conflict,
            "position_estimated": c.position_estimated,
        },
    }


def build_input(
    image_id: str, zone: str, at: str, contacts: list[ContactFinding], findings: list[ReportFinding]
) -> str:
    payload = {
        "image": {"id": image_id, "zone": zone, "capture_time": at},
        "contacts": [_contact_facts(i, c) for i, c in enumerate(contacts)],
        "reports": [
            {
                "claim_id": f.claim_id,
                "time": f.report_time,
                "source": f.source,
                "claim_type": f.claim_type,
                "track_id": f.track_id,
                "verdict": f.verdict,
                "reasoning": f.reasoning,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1)


def _validate(
    contact: ContactFinding, proposal: LevelProposal, findings: list[ReportFinding]
) -> str | None:
    """Öneri kabul edilemezse sebebini döndürür."""
    step = LEVELS.index(proposal.level) - LEVELS.index(contact.final_level)
    if abs(step) > 1:
        return f"{contact.final_level} → {proposal.level}: bir kademeden fazla değişiklik önerildi"
    if step < 0:
        linked = [f for f in findings if contact.track_id and f.track_id == contact.track_id]
        if any(f.effect == "raises" for f in linked):
            # ADR-0002: riski artıran rapor etkisi her zaman kazanır.
            return (
                f"{contact.final_level} → {proposal.level}: raporlar bu temasın riskini "
                "yükseltti, düşürülemez"
            )
        usable = {
            f.claim_id
            for f in findings
            if f.verdict == "consistent" and contact.track_id and f.track_id == contact.track_id
        }
        if not proposal.evidence_claim_ids:
            return f"{contact.final_level} → {proposal.level}: düşürme için kanıt gösterilmedi"
        if not set(proposal.evidence_claim_ids) <= usable:
            return (
                f"{contact.final_level} → {proposal.level}: gösterilen kanıt bu temasa bağlı "
                "tutarlı bir rapor değil"
            )
    return None


def apply_proposals(
    contacts: list[ContactFinding], draft: DecisionDraft, findings: list[ReportFinding]
) -> tuple[list[ContactFinding], int, int]:
    by_ref = {contact_ref(i): i for i in range(len(contacts))}
    updated = list(contacts)
    seen: set[int] = set()
    accepted = rejected = 0
    for proposal in draft.adjustments:
        i = by_ref.get(proposal.contact)
        if i is None or i in seen:
            continue
        seen.add(i)
        contact = updated[i]
        if proposal.level == contact.final_level:
            continue
        reason = _validate(contact, proposal, findings)
        if reason is None:
            accepted += 1
            updated[i] = contact.model_copy(
                update={"final_level": proposal.level, "adjustment_reason": proposal.reason}
            )
        else:
            rejected += 1
            updated[i] = contact.model_copy(update={"adjustment_rejected": reason})
    return updated, accepted, rejected


def decide(
    router: LLMRouter,
    *,
    image_id: str,
    zone: str,
    at: str,
    contacts: list[ContactFinding],
    findings: list[ReportFinding],
    timeout_s: float,
    max_tokens: int,
) -> Decision:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    user = build_input(image_id, zone, at, contacts, findings)
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(router.complete_json, TASK, system, user, DecisionDraft, max_tokens)
    try:
        draft, model = future.result(timeout=timeout_s)
    except FutureTimeout as exc:
        raise DecisionUnavailableError(f"LLM zaman aşımı ({timeout_s:g} sn)") from exc
    except LLMUnavailableError as exc:
        raise DecisionUnavailableError("kullanılabilir model yok") from exc
    finally:
        # Süresi dolan çağrı arka planda bitebilir; beklemeden devam ediyoruz.
        executor.shutdown(wait=False, cancel_futures=True)
    updated, accepted, rejected = apply_proposals(contacts, draft, findings)
    return Decision(updated, draft.assessment.strip(), model, accepted, rejected)
