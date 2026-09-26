"""LLM karar ayarı (ADR-0002): LLM dikkat maddeleri önerir, kod her birini veriyle doğrular.

Görev tanımı s1: agent "hangi durumların dikkat gerektirdiğini, nedenlerini ve dayandığı
verileri" açıklamalı. LLM serbest metin gerekçe yazmaz; her temas için sabit bir neden
(`AttentionReason`), dayandığı bulgu alanlarını ya da rapor iddialarını ve isteğe bağlı bir
seviye önerisi seçer. Temas kimlikleri şemada o karenin temaslarından oluşan bir enum'dur;
şema her çağrıda yeniden üretilir.

Kod her nedeni veriyle doğrular; doğrulanamayan madde reddedilir, sebebi brief'te kalır.
Seviye en fazla bir kademe ve yalnızca doğrulanmış bir nedenle değişir: yükseltme için
riski artıran ve kuralların seviyede zaten saymadığı (`level_basis`) bir neden, düşürme
için "dikkat_gerekmiyor" ve o temasa bağlı, kararı "consistent", saati tutan (`time_check`
ok) bir rapor iddiası gerekir. Raporun yükselttiği
temas düşürülemez; gösterilen rapor o temasa ait ve çelişkisiz olmalıdır (görev tanımı s2).

"Değerlendirme" metnini kod yazar: kabul edilen her madde için sabit Türkçe şablon, sayılar
bulgu alanlarından. LLM'den yalnızca kısa bir özet alınır; özette sayı, kimlik, bölge adı ya
da İngilizce terim geçerse özet atılır.

LLM cevap vermezse, süre aşılırsa ya da hiçbir model şemaya uymazsa `DecisionUnavailableError`
fırlatılır; servis otomatik özete geçer.
"""

import json
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, create_model, field_validator

from app.agent.brief_text import TREND_TR
from app.core.rules import LevelRules
from app.formatting import km, mps
from app.llm.client import LLMRouter, LLMUnavailableError
from app.pipelines.risk import LEVELS, circling_path_m, loiter_minutes
from app.schemas.api import (
    AttentionFinding,
    AttentionReason,
    ContactFinding,
    MotionFinding,
    ReportFinding,
)
from app.schemas.domain import RiskLevel

TASK = "reasoning"
PROMPT_PATH = Path(__file__).parent / "prompts" / "brief.md"
NO_ATTENTION: AttentionReason = "dikkat_gerekmiyor"

FactField = Literal[
    "kind",
    "type",
    "certainty",
    "distance_to_base_km",
    "trend",
    "distance_to_base_60min_ago_km",
    "distance_to_base_30min_ago_km",
    "recent_speed_mps",
    "avg_speed_mps",
    "heading_deg",
    "stops",
    "long_stop_near_base_min",
    "circling",
    "base_distance_range_km",
    "zones_passed",
    "level",
    "level_reasons",
    "level_basis",
    "verified_friend",
    "visual",
    "notes",
]
"""LLM'e verilen temas bulgularının alan adları; `dayanak`'ta yalnızca bunlar gösterilebilir."""

REASON_TR: dict[AttentionReason, str] = {
    "yaklasma": "yaklaşma",
    "dolasma": "dolaşma",
    "uzun_duraklama": "uzun duraklama",
    "tehdit_uyarisi": "tehdit uyarısı",
    "rapor_celiskisi": "rapor çelişkisi",
    "kacirilmis_temas": "kaçırılmış temas",
    "kayit_disi": "kayıt dışı temas",
    "dikkat_gerekmiyor": "dikkat gerekmiyor",
}

# Bu kadar kelimeden kısa özet gerçek bir özet sayılmaz. GLM-5.3 zaman zaman boş ya da "..."
# döndürüyor; şemaya uymayan cevap zincirde sıradaki modele geçer.
MIN_SUMMARY_WORDS = 3
MAX_SUMMARY_SENTENCES = 2
# Özette sayı ve kimlik (T0020, K1, kayit_disi_1) yok: sayıları kod yazar, LLM uydurabilir.
_DIGIT_OR_ID = re.compile(r"\d|kayit_disi", re.IGNORECASE)
# Kodun alan değerleri Türkçe metne sızmasın (canlı denemede "low seviyede").
_ENGLISH = re.compile(
    r"\b(low|medium|high|critical|matched|unregistered|missed|approaching|receding|"
    r"stationary|passing|truck|car|bus)\b",
    re.IGNORECASE,
)
_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
# Türkçe harfleri sadeleştirilmiş özette aranır. Yazıyla sayılar da sayıdır (canlı denemede
# "iki başka temas duruyor" yanlıştı); "bir" belirsizlik sıfatı olarak serbest.
_NUMBER_WORDS = re.compile(
    r"\b(iki|uc|dort|bes|alti|yedi|sekiz|dokuz|on|yirmi|otuz|kirk|elli|altmis|yetmis|"
    r"seksen|doksan|yuz|bin)\b"
)
# Bütün bölge adları bir yönle başlıyor (Kuzey Yolu, Guneybati Yolu...); yön, konum iddiasıdır.
_DIRECTIONS = re.compile(r"\b(kuzey|guney|dogu(?![mr])|bati)\w*")


class AttentionDraft(BaseModel):
    """LLM'in bir dikkat maddesi; `track_id` her çağrıda temas etiketlerinin enum'u olur."""

    track_id: str = Field(description="Temasın kimliği (listeden)")
    neden: AttentionReason = Field(description="Dikkat nedeni kodu")
    dayanak: list[int | FactField] = Field(
        description="Dayanılan bulgu alanlarının adları ve bu temasa bağlı iddiaların claim_id'leri"
    )
    seviye_onerisi: RiskLevel | None = Field(
        default=None, description="Seviyeyi en fazla bir kademe değiştirmek istersen yeni seviye"
    )


class DecisionDraft(BaseModel):
    dikkat: list[AttentionDraft]
    ozet: str = Field(
        min_length=20,
        description="Operatör için en fazla 2 cümlelik Türkçe özet; sayı, kimlik ve bölge adı yok",
    )

    @field_validator("ozet", mode="before")
    @classmethod
    def _real_summary(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.lower().startswith(("değerlendirme:", "özet:", "ozet:")):
            text = text.split(":", 1)[1].strip()
        words = [w for w in text.split() if any(ch.isalpha() for ch in w)]
        if len(words) < MIN_SUMMARY_WORDS:
            raise ValueError(f"özet boş ya da yer tutucu: {value!r}")
        return text


class DecisionUnavailableError(RuntimeError):
    """LLM kararı alınamadı; sebep otomatik özette gösterilir."""


@dataclass(frozen=True)
class Decision:
    contacts: list[ContactFinding]
    assessment: str
    """Kodun yazdığı "Değerlendirme" metni: temiz özet ve kabul edilen maddelerin şablonları."""
    model: str
    accepted: int
    """Kabul edilen seviye ayarları."""
    rejected: int
    """Reddedilen seviye ayarları."""
    attention: list[AttentionFinding]
    summary: str | None
    summary_rejected: str | None


# --- şema --------------------------------------------------------------------------------


def contact_labels(contacts: Sequence[ContactFinding]) -> list[str]:
    """Temas etiketleri: track kimliği; track'i olmayan temas için `kayit_disi_N`."""
    labels: list[str] = []
    unregistered = 0
    for c in contacts:
        if c.track_id:
            labels.append(c.track_id)
        else:
            unregistered += 1
            labels.append(f"kayit_disi_{unregistered}")
    return labels


def draft_schema(labels: Sequence[str]) -> type[DecisionDraft]:
    """Bu karenin temas etiketleriyle sınırlı karar şeması; model başka kimlik yazamaz."""
    # Temas yoksa liste boş kalmak zorunda; enum'a yer tutucu bir değer konur.
    choices: Any = Literal.__getitem__(tuple(labels) or ("temas_yok",))
    item = create_model(
        "DikkatMaddesi",
        __base__=AttentionDraft,
        track_id=(choices, Field(description="Temasın kimliği (listeden)")),
    )
    items: Any = list[item]  # type: ignore[valid-type]
    limit: dict[str, Any] = {} if labels else {"max_length": 0}
    return create_model("KararTaslagi", __base__=DecisionDraft, dikkat=(items, Field(**limit)))


# --- LLM girdisi -------------------------------------------------------------------------


def _contact_facts(label: str, c: ContactFinding, levels: LevelRules) -> dict[str, object]:
    motion = c.motion
    facts: dict[str, object] = {
        "id": label,
        "kind": c.kind,
        "type": c.effective_label,
        "certainty": c.certainty,
        "distance_to_base_km": round(c.distance_to_base_m / 1000, 2),
        "trend": motion.trend if motion else None,
        "distance_to_base_60min_ago_km": (
            round(motion.distance_to_base_60min_ago_m / 1000, 2)
            if motion and motion.distance_to_base_60min_ago_m is not None
            else None
        ),
        "distance_to_base_30min_ago_km": (
            round(motion.distance_to_base_30min_ago_m / 1000, 2)
            if motion and motion.distance_to_base_30min_ago_m is not None
            else None
        ),
        "recent_speed_mps": round(motion.recent_speed_mps, 1) if motion else None,
        "avg_speed_mps": round(motion.avg_speed_mps, 1) if motion else None,
        "heading_deg": round(motion.heading_deg)
        if motion and motion.heading_deg is not None
        else None,
        "stops": [
            f"{s.start}–{s.end} ({s.minutes} dk, üsse {km(s.distance_to_base_m)})"
            for s in motion.stops
        ]
        if motion
        else [],
        "long_stop_near_base_min": loiter_minutes(motion, levels),
        "circling": _is_circling(motion, levels),
        "base_distance_range_km": [
            round(motion.base_distance_min_m / 1000, 2),
            round(motion.base_distance_max_m / 1000, 2),
        ]
        if motion
        else None,
        "zones_passed": motion.zones_passed if motion else [],
        "level": c.final_level,
        "level_reasons": c.level_reasons,
        "level_basis": c.level_basis,
        "verified_friend": c.verified_friend,
        "visual": c.visual.model_dump(exclude={"model"}) if c.visual else None,
        "notes": {
            "weak_detection": c.is_weak,
            "ambiguous_match": c.is_ambiguous,
            "type_conflict": c.type_conflict,
            "position_estimated": c.position_estimated,
        },
    }
    return facts


def build_input(
    image_id: str,
    zone: str,
    at: str,
    contacts: list[ContactFinding],
    findings: list[ReportFinding],
    levels: LevelRules,
) -> str:
    labels = contact_labels(contacts)
    payload = {
        "image": {"id": image_id, "zone": zone, "capture_time": at},
        "thresholds": {"long_stop_min": levels.loiter_minutes},
        "contacts": [
            _contact_facts(label, c, levels) for label, c in zip(labels, contacts, strict=True)
        ],
        "reports": [
            {
                "claim_id": f.claim_id,
                "time": f.report_time,
                "source": f.source,
                "claim_type": f.claim_type,
                "track_id": f.track_id,
                "verdict": f.verdict,
                "time_check": f.time_check,
                "reasoning": f.reasoning,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1)


# --- doğrulama ---------------------------------------------------------------------------


def _is_circling(motion: MotionFinding | None, levels: LevelRules) -> bool:
    """Temel seviye tablosuyla aynı koşul: üs çevresinde yeterince yol yaparak dolaşıyor."""
    return circling_path_m(motion, levels) >= levels.circle_min_path_m


def _linked(contact: ContactFinding, findings: list[ReportFinding]) -> list[ReportFinding]:
    return [f for f in findings if contact.track_id and f.track_id == contact.track_id]


def _threats(contact: ContactFinding, findings: list[ReportFinding]) -> list[ReportFinding]:
    return [
        f
        for f in _linked(contact, findings)
        if f.verdict == "consistent" and f.claim_type == "threat_warning"
    ]


def _contradictions(contact: ContactFinding, findings: list[ReportFinding]) -> list[ReportFinding]:
    return [f for f in _linked(contact, findings) if f.verdict == "contradicts"]


def _reason_problem(
    reason: AttentionReason,
    contact: ContactFinding,
    findings: list[ReportFinding],
    levels: LevelRules,
) -> str | None:
    """Neden veriyle doğrulanamıyorsa sebebini döndürür."""
    motion = contact.motion
    match reason:
        case "yaklasma":
            if motion is None:
                return "temasın hareket kaydı yok"
            if motion.trend != "approaching":
                return f"temas üsse yaklaşmıyor ({TREND_TR[motion.trend]})"
        case "dolasma":
            if not _is_circling(motion, levels):
                return "temas üs çevresinde dolaşmıyor"
        case "uzun_duraklama":
            if loiter_minutes(motion, levels) < levels.loiter_minutes:
                return (
                    f"üsse {km(levels.loiter_m)}'den yakın en az {levels.loiter_minutes} dk "
                    "duraklama yok"
                )
        case "tehdit_uyarisi":
            if not _threats(contact, findings):
                return "bu temasa bağlı tutarlı bir tehdit uyarısı yok"
        case "rapor_celiskisi":
            if not _contradictions(contact, findings):
                return "bu temasa bağlı, tespitle çelişen bir rapor yok"
        case "kacirilmis_temas":
            if contact.kind != "missed":
                return "temas kaçırılmış değil, tespit edildi"
        case "kayit_disi":
            if contact.kind != "unregistered":
                return "temasın track'i var, kayıt dışı değil"
        case "dikkat_gerekmiyor":
            present = _present_reasons(contact, findings, levels)
            if present:
                return f"veride {', '.join(REASON_TR[r] for r in present)} var"
    return None


def _present_reasons(
    contact: ContactFinding, findings: list[ReportFinding], levels: LevelRules
) -> list[AttentionReason]:
    """Veride doğrulanan ve "dikkat gerekmiyor" demeyi engelleyen dikkat nedenleri.

    Kayıt dışı temas yalnızca üssün hemen yakınındaysa dikkat ister (ADR-0003); uzakta
    park halindeki araç için "dikkat gerekmiyor" geçerlidir.
    """
    reasons: tuple[AttentionReason, ...] = get_args(AttentionReason)
    return [
        r
        for r in reasons
        if r != NO_ATTENTION
        and _reason_problem(r, contact, findings, levels) is None
        and (r != "kayit_disi" or contact.distance_to_base_m < levels.unregistered_alert_m)
    ]


def _basis_problem(
    contact: ContactFinding, basis: list[int | str], findings: list[ReportFinding]
) -> str | None:
    linked = {f.claim_id for f in _linked(contact, findings)}
    foreign = [i for i in basis if isinstance(i, int) and i not in linked]
    if foreign:
        return f"dayanaktaki iddia {', '.join(map(str, foreign))} bu temasa bağlı değil"
    return None


def _level_problem(
    contact: ContactFinding,
    level: RiskLevel,
    reason: AttentionReason,
    evidence: list[int],
    findings: list[ReportFinding],
) -> str | None:
    """Seviye önerisi kabul edilemezse sebebini döndürür (ADR-0002)."""
    now = contact.final_level
    step = LEVELS.index(level) - LEVELS.index(now)
    if abs(step) > 1:
        return f"{now} → {level}: bir kademeden fazla değişiklik önerildi"
    if reason == "rapor_celiskisi":
        # ADR-0002: çelişkide tespit esas alınır; çelişen rapor seviyeyi değiştirmez.
        return f"{now} → {level}: çelişen rapor seviyeyi değiştirmez"
    if step > 0 and reason in contact.level_basis:
        # Aynı olgu iki kez sayılmasın: yükseltme kuralların kullanmadığı bir neden ister.
        return f"{now} → {level}: {REASON_TR[reason]} kuralların verdiği seviyede zaten sayıldı"
    if step > 0 and reason == NO_ATTENTION:
        return f"{now} → {level}: dikkat gerekmiyorsa seviye yükseltilemez"
    if step < 0 and reason != NO_ATTENTION:
        return f"{now} → {level}: {REASON_TR[reason]} seviye düşürme gerekçesi olamaz"
    linked = _linked(contact, findings)
    if step > 0 and evidence:
        usable = {f.claim_id for f in linked if f.verdict != "contradicts"}
        if not set(evidence) <= usable:
            return f"{now} → {level}: gösterilen rapor bu temasa ait değil ya da tespitle çelişiyor"
    if step < 0:
        if any(f.effect == "raises" for f in linked):
            # ADR-0002: riski artıran rapor etkisi her zaman kazanır.
            return f"{now} → {level}: raporlar bu temasın riskini yükseltti, düşürülemez"
        about = {f.claim_id: f for f in linked if f.verdict == "consistent"}
        if not evidence:
            return f"{now} → {level}: düşürme için kanıt gösterilmedi"
        if not set(evidence) <= about.keys():
            return f"{now} → {level}: gösterilen kanıt bu temasa bağlı tutarlı bir rapor değil"
        if any(about[i].time_check != "ok" for i in evidence):
            # Rapor saatinde araç orada değilse ya da bilinmiyorsa iddia bu araca ait olmayabilir.
            return (
                f"{now} → {level}: gösterilen raporun saati temasın o saatteki konumuyla "
                "doğrulanamadı"
            )
    return None


# --- kodun yazdığı metin -----------------------------------------------------------------


def _times(findings: list[ReportFinding]) -> str:
    return ", ".join(sorted({f.report_time for f in findings}))


def reason_text(
    reason: AttentionReason,
    contact: ContactFinding,
    findings: list[ReportFinding],
    levels: LevelRules,
    *,
    evidence: list[ReportFinding] | None = None,
) -> str:
    """Doğrulanmış nedenin sabit Türkçe şablonu; sayılar bulgu alanlarından."""
    m = contact.motion
    match reason:
        case "yaklasma" if m is not None:
            parts = ["üsse yaklaşıyor"]
            if m.distance_to_base_30min_ago_m is not None:
                parts.append(
                    f"30 dk önce {km(m.distance_to_base_30min_ago_m)}, "
                    f"şimdi {km(m.distance_to_base_m)}"
                )
            else:
                parts.append(f"üsse {km(m.distance_to_base_m)}")
            parts.append(f"son 30 dk {mps(m.recent_speed_mps)}")
            return ", ".join(parts)
        case "dolasma" if m is not None:
            closest, farthest = km(m.base_distance_min_m), km(m.base_distance_max_m)
            band = closest if closest == farthest else f"{closest}–{farthest}"
            return (
                f"üs çevresinde dolaşıyor, kayıt boyunca üsse {band} mesafede, "
                f"{km(circling_path_m(m, levels))} yol"
            )
        case "uzun_duraklama" if m is not None:
            near = [s for s in m.stops if s.distance_to_base_m < levels.loiter_m]
            stop = max(near, key=lambda s: s.minutes)
            ongoing = m.current_stop_minutes is not None and stop is m.stops[-1]
            if ongoing:
                at_least = "en az " if m.stop_open_ended else ""
                return (
                    f"üsse {km(stop.distance_to_base_m)}'de {at_least}{stop.minutes} dk'dır duruyor"
                )
            return (
                f"{stop.start}–{stop.end} arası üsse {km(stop.distance_to_base_m)}'de "
                f"{stop.minutes} dk durakladı"
            )
        case "tehdit_uyarisi":
            return f"{_times(_threats(contact, findings))} tehdit uyarısı bu temasla tutarlı"
        case "rapor_celiskisi":
            return (
                f"{_times(_contradictions(contact, findings))} raporu tespitle çelişiyor; "
                "tespit esas alındı"
            )
        case "kacirilmis_temas":
            return "karede ama tespit edilmedi (kaçırılmış temas), tipi bilinmiyor"
        case "kayit_disi":
            return (
                f"track'i yok (kayıt dışı), hareket geçmişi bilinmiyor, "
                f"üsse {km(contact.distance_to_base_m)}"
            )
    text = "dikkat gerektiren bir durum yok"
    if evidence:
        sources = {"resmi" if f.source == "official" else "üçüncü taraf" for f in evidence}
        text += f"; {_times(evidence)} {' ve '.join(sorted(sources))} raporu doğruluyor"
    return text


def summary_problem(text: str, zone_names: Sequence[str]) -> str | None:
    """Özet kodun denetleyemeyeceği bir olgu içeriyorsa atılma sebebini döndürür."""
    folded = text.translate(_ASCII).casefold()
    if _DIGIT_OR_ID.search(text) or _NUMBER_WORDS.search(folded):
        return "özette sayı ya da temas kimliği var"
    zones = [z for z in zone_names if z.translate(_ASCII).casefold() in folded]
    if zones:
        return f"özette bölge adı var ({', '.join(zones)})"
    direction = _DIRECTIONS.search(folded)
    if direction:
        return f"özette yön var ({direction.group(0)}); konumu kod yazar"
    english = _ENGLISH.search(text)
    if english:
        return f"özette İngilizce terim var ({english.group(0)})"
    sentences = [s for s in re.split(r"[.!?…]+", text) if s.strip()]
    if len(sentences) > MAX_SUMMARY_SENTENCES:
        return f"özet {MAX_SUMMARY_SENTENCES} cümleden uzun"
    return None


def _who(label: str) -> str:
    if label.startswith("kayit_disi_"):
        return f"kayıt dışı temas {label.removeprefix('kayit_disi_')}"
    return label


# --- uygulama ----------------------------------------------------------------------------


def _check(
    contact: ContactFinding,
    proposal: AttentionDraft,
    findings: list[ReportFinding],
    levels: LevelRules,
    *,
    wants_level: bool,
) -> tuple[bool, bool | None, str | None]:
    """(neden doğrulandı, seviye kabul edildi ya da öneri yok, ret sebebi)."""
    reason = proposal.neden
    evidence = [b for b in proposal.dayanak if isinstance(b, int)]
    problem = _basis_problem(contact, list(proposal.dayanak), findings)
    if problem:
        return False, False if wants_level else None, problem
    reason_problem = _reason_problem(reason, contact, findings, levels)
    if not wants_level or proposal.seviye_onerisi is None:
        return reason_problem is None, None, reason_problem
    level_problem = _level_problem(contact, proposal.seviye_onerisi, reason, evidence, findings)
    if reason == NO_ATTENTION:
        # Doğrulanmış dost (ADR-0002): veride dikkat nedeni olsa da tutarlı, saati tutan
        # rapor riski düşürebilir. Düşürme reddedilirse sebebi seviye kuralıdır.
        if level_problem is None:
            return True, True, None
        return reason_problem is None, False, level_problem
    if reason_problem:
        return False, False, reason_problem
    return True, level_problem is None, level_problem


def apply_attention(
    contacts: list[ContactFinding],
    draft: DecisionDraft,
    findings: list[ReportFinding],
    levels: LevelRules,
) -> tuple[list[ContactFinding], list[AttentionFinding], int, int]:
    """Maddeleri veriyle doğrular; doğrulanmış nedenle önerilen seviye ayarını uygular.

    Bir temasın seviyesi en fazla bir kez değişir (±1 kademe); reddedilen bir öneri aynı temas
    için sonraki doğrulanmış öneriyi engellemez.
    """
    index = {label: i for i, label in enumerate(contact_labels(contacts))}
    by_id = {f.claim_id: f for f in findings}
    updated = list(contacts)
    adjusted: set[int] = set()
    results: list[AttentionFinding] = []
    accepted = rejected = 0
    for proposal in draft.dikkat:
        i = index.get(proposal.track_id)
        if i is None:  # şema bunu engelliyor; elle kurulmuş taslak için
            continue
        contact = updated[i]
        level = proposal.seviye_onerisi
        wants_level = level is not None and level != contact.final_level and i not in adjusted
        verified, level_ok, problem = _check(
            contact, proposal, findings, levels, wants_level=wants_level
        )
        evidence = [by_id[b] for b in proposal.dayanak if isinstance(b, int) and b in by_id]
        text = (
            reason_text(
                proposal.neden, contact, findings, levels, evidence=evidence if level_ok else None
            )
            if verified
            else None
        )
        rejection = f"{REASON_TR[proposal.neden]}: {problem}" if problem else None
        if level_ok:
            accepted += 1
            adjusted.add(i)
            updated[i] = contact.model_copy(
                update={
                    "final_level": level,
                    "adjustment_reason": text,
                    "adjustment_rejected": None,
                }
            )
        elif level_ok is False:
            rejected += 1
            updated[i] = contact.model_copy(update={"adjustment_rejected": rejection})
        results.append(
            AttentionFinding(
                contact=proposal.track_id,
                track_id=contact.track_id,
                reason=proposal.neden,
                basis=list(proposal.dayanak),
                level_proposal=level,
                accepted=verified,
                level_accepted=level_ok,
                rejection=rejection,
                text=text,
            )
        )
    return updated, results, accepted, rejected


def compose_assessment(summary: str | None, attention: list[AttentionFinding]) -> str:
    """Kodun "Değerlendirme" metni: temiz özet ve doğrulanmış dikkat nedenleri.

    Aynı temasın nedenleri tek cümlede birleşir. "Dikkat gerekmiyor" maddeleri brief
    verisinde kalır; yalnızca seviyeyi düşürdüyse metne girer.
    """
    by_contact: dict[str, list[str]] = {}
    for a in attention:
        if a.accepted and a.text and (a.reason != NO_ATTENTION or a.level_accepted):
            by_contact.setdefault(a.contact, []).append(a.text)
    items = [f"{_who(label)}: {'; '.join(texts)}." for label, texts in by_contact.items()]
    parts = ([summary] if summary else []) + items
    return " ".join(parts) or "Dikkat gerektiren bir durum bildirilmedi."


def decide(
    router: LLMRouter,
    *,
    image_id: str,
    zone: str,
    at: str,
    contacts: list[ContactFinding],
    findings: list[ReportFinding],
    levels: LevelRules,
    zone_names: Sequence[str],
    timeout_s: float,
    max_tokens: int,
) -> Decision:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    user = build_input(image_id, zone, at, contacts, findings, levels)
    schema = draft_schema(contact_labels(contacts))
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(router.complete_json, TASK, system, user, schema, max_tokens)
    try:
        draft, model = future.result(timeout=timeout_s)
    except FutureTimeout as exc:
        raise DecisionUnavailableError(f"LLM zaman aşımı ({timeout_s:g} sn)") from exc
    except LLMUnavailableError as exc:
        raise DecisionUnavailableError("kullanılabilir model yok") from exc
    finally:
        # Süresi dolan çağrı arka planda bitebilir; beklemeden devam ediyoruz.
        executor.shutdown(wait=False, cancel_futures=True)
    updated, attention, accepted, rejected = apply_attention(contacts, draft, findings, levels)
    summary: str | None = draft.ozet.strip()
    summary_rejected = summary_problem(summary, [zone, *zone_names]) if summary else None
    if summary_rejected:
        summary = None
    return Decision(
        contacts=updated,
        assessment=compose_assessment(summary, attention),
        model=model,
        accepted=accepted,
        rejected=rejected,
        attention=attention,
        summary=summary,
        summary_rejected=summary_rejected,
    )
