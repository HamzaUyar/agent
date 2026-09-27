"""Görüntüsüz track'lerin değerlendirmesi: risk motorunun sonucu + LLM'in kısa metni.

Bazı araçların hareket kaydı var ama hiçbir görüntünün adayı değiller (çekim anında
kadrajın dışında kaldılar, görev tanımı s3). Bunlar görüntü değerlendirmesine girmez;
seviyelerini risk motoru hareketlerinden verir, LLM yalnızca operatör için kısa bir
değerlendirme yazar ve seviyeyi değiştirmez. Olguları kod hesaplar; LLM'in metninde
olgularda olmayan bir sayı varsa metin atılır ve otomatik özet kullanılır.
"""

import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from app.formatting import km, mps
from app.llm.client import LLMRouter, LLMUnavailableError
from app.pipelines.geo import distance_m
from app.pipelines.risk import LEVELS, rule_of
from app.risk_engine import RULE_TEXT, TrackRisk
from app.risk_engine.summary import events, hhmm
from app.schemas.api import MotionFinding
from app.schemas.claims import ClaimRecord
from app.schemas.domain import GeoPoint

PROMPT_PATH = Path(__file__).parent / "prompts" / "track_brief.md"
TASK = "track_brief"
REPORT_RADIUS_M = 300.0
"""İddianın konumu track'in son iki saatteki bir noktasına bu kadar yakınsa ilgili sayılır."""
LEVEL_TR = {"low": "düşük", "medium": "orta", "high": "yüksek", "critical": "kritik"}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_COORDINATE = re.compile(r"\d+\.\d{3,}\s*[NE]")
MAX_SENTENCES = 4


class TrackBriefDraft(BaseModel):
    ozet: str = Field(min_length=20, description="Operatör için 2-4 cümlelik değerlendirme")


@dataclass(frozen=True)
class TrackBrief:
    track_id: str
    level: str
    code: str
    priority_score: float
    facts: str
    text: str
    is_fallback: bool
    rejected: str | None
    """LLM metni atıldıysa sebebi (ör. olgularda olmayan sayı)."""
    model: str | None


def related_claims(
    points: Sequence[tuple[str, GeoPoint]], claims: Sequence[ClaimRecord]
) -> list[tuple[ClaimRecord, float]]:
    """Koordinatı track'in bir noktasına `REPORT_RADIUS_M` içinde olan iddialar ve mesafe."""
    out = []
    for record in claims:
        c = record.claim
        if c.lat is None or c.lon is None:
            continue
        spot = GeoPoint(c.lat, c.lon)
        d = min(distance_m(spot, p) for _, p in points)
        if d <= REPORT_RADIUS_M:
            out.append((record, d))
    return out


def level_origin(risk: TrackRisk) -> str:
    """Seviyenin nedeni: hangi kuralla ve ne zaman girildiği; tutuluyorsa şu anki durum.

    Seviye iniş beklemesindeyken son adımın kuralı seviyeyi açıklamaz (ör. kritik seviye
    tutulurken araç yalnızca "3 km içinde"); nedeni seviyenin açıldığı adım söyler.
    """
    cur = risk.current
    if cur.level == 0:
        return RULE_TEXT.get(cur.code_raw, cur.code_raw)
    entry = [e for e in events(risk, cur.level) if e.t_out is None][-1]
    rule = rule_of(entry.entry_code)
    text = f"giriş {hhmm(entry.t_in)}, {RULE_TEXT.get(rule, rule)}"
    if cur.held:
        now = RULE_TEXT.get(cur.code_raw, cur.code_raw)
        text += f"; şu an: {now}, koşul kalktı, seviye iniş beklemesinde"
    return text


def track_facts(
    risk: TrackRisk,
    motion: MotionFinding,
    claims: Sequence[tuple[ClaimRecord, float]],
) -> str:
    """Saf: LLM'e giden olgu satırları; hepsi kodla hesaplanır."""
    cur = risk.current
    lines = [
        f"Track {risk.track_id} (görüntüsüz: kaydı var, hiçbir karede değil; tip bilinmiyor)",
        f"  seviye: {LEVEL_TR[LEVELS[cur.level]]} ({level_origin(risk)})",
        f"  kayit: {hhmm(risk.steps[0].t)}-{hhmm(cur.t)}",
    ]
    parts = []
    if motion.distance_to_base_60min_ago_m is not None:
        parts.append(f"1 saat önce {km(motion.distance_to_base_60min_ago_m)}")
    if motion.distance_to_base_30min_ago_m is not None:
        parts.append(f"30 dk önce {km(motion.distance_to_base_30min_ago_m)}")
    parts.append(f"son an {km(motion.distance_to_base_m)}")
    lines.append("  uzaklik: " + " → ".join(parts))
    closest = min(risk.steps, key=lambda s: s.features.d)
    lines.append(f"  en_yakin_gecis: {km(closest.features.d)} ({hhmm(closest.t)})")
    lines.append(
        f"  hareket: son dönem {mps(motion.recent_speed_mps)}, "
        f"2 saatlik ortalama {mps(motion.avg_speed_mps)}"
    )
    if motion.stops:
        stops = ", ".join(
            f"{s.start} ({s.minutes} dk, üsse {km(s.distance_to_base_m)})" for s in motion.stops
        )
        lines.append(f"  duraklamalar: {stops}")
    history: list[tuple[str, str]] = []
    for s in risk.steps:
        name = LEVEL_TR[LEVELS[s.level]]
        if not history or history[-1][1] != name:
            history.append((hhmm(s.t), name))
    lines.append("  seviye_gecmisi: " + " → ".join(f"{t} {n}" for t, n in history))
    evs = [e for level in (3, 2) for e in events(risk, level)]
    if evs:
        lines.append("  olaylar:")
        lines += [f"    - {e.reason()}" for e in evs]
    if cur.tags:
        lines.append("  kaliplar: " + ", ".join(cur.tags))
    if claims:
        lines.append("  raporlar (doğrulanmamış):")
        for record, d in claims:
            r = record.report
            lines.append(
                f"    - {r.time.strftime('%H:%M')} {r.source.value}: {r.text} "
                f"(iz noktasına {km(d)})"
            )
    return "\n".join(lines)


def text_problem(text: str, facts: str) -> str | None:
    """LLM metni kodun denetleyemeyeceği bir şey içeriyorsa atılma sebebi."""
    extra = unsupported_numbers(text, facts)
    if extra:
        return f"olgularda olmayan sayı: {', '.join(extra)}"
    if _COORDINATE.search(text):
        return "metinde koordinat var"
    sentences = [x for x in re.split(r"(?<![0-9])[.!?]+", text) if x.strip()]
    if len(sentences) > MAX_SENTENCES:
        return f"{len(sentences)} cümle (en fazla {MAX_SENTENCES})"
    return None


def unsupported_numbers(text: str, facts: str) -> list[str]:
    """Metinde olup olgularda geçmeyen sayılar (virgül ve nokta eşit sayılır)."""
    known = {n.replace(".", ",") for n in _NUMBER.findall(facts)}
    return [n for n in _NUMBER.findall(text) if n.replace(".", ",") not in known]


def fallback_text(risk: TrackRisk) -> str:
    cur = risk.current
    closest = min(risk.steps, key=lambda s: s.features.d)
    return (
        f"Görüntüsüz track: seviye {LEVEL_TR[LEVELS[cur.level]]} ({level_origin(risk)}). "
        f"Son anda üsse {km(cur.features.d)}; "
        f"en yakın geçiş {km(closest.features.d)} ({hhmm(closest.t)})."
    )


def write_track_brief(
    router: LLMRouter | None,
    risk: TrackRisk,
    motion: MotionFinding,
    claims: Sequence[tuple[ClaimRecord, float]],
    *,
    timeout_s: float,
    max_tokens: int,
) -> TrackBrief:
    facts = track_facts(risk, motion, claims)
    cur = risk.current

    def brief(text: str | None, rejected: str | None, model: str | None) -> TrackBrief:
        """`text` None ise otomatik özet kullanılır."""
        return TrackBrief(
            track_id=risk.track_id,
            level=LEVELS[cur.level],
            code=cur.code,
            priority_score=round(cur.score, 2),
            facts=facts,
            text=text if text is not None else fallback_text(risk),
            is_fallback=text is None,
            rejected=rejected,
            model=model,
        )

    if router is None:
        return brief(None, None, None)
    executor = ThreadPoolExecutor(max_workers=1)
    system = PROMPT_PATH.read_text(encoding="utf-8")
    future = executor.submit(router.complete_json, TASK, system, facts, TrackBriefDraft, max_tokens)
    try:
        draft, model = future.result(timeout=timeout_s)
    except FutureTimeout:
        return brief(None, "zaman aşımı", None)
    except LLMUnavailableError:
        return brief(None, "kullanılabilir model yok", None)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    text = draft.ozet.strip()
    problem = text_problem(text, facts)
    if problem:
        return brief(None, problem, model)
    return brief(text, None, model)
