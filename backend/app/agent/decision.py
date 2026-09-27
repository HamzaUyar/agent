"""LLM karar ayarı (ADR-0002): LLM dikkat maddeleri önerir, kod her birini veriyle doğrular.

Görev tanımı s1: agent "hangi durumların dikkat gerektirdiğini, nedenlerini ve dayandığı
verileri" açıklamalı. LLM serbest metin gerekçe yazmaz; her temas için sabit bir neden
(`AttentionReason`), dayandığı bulgu alanlarını ya da rapor iddialarını ve isteğe bağlı bir
seviye önerisi seçer. Temas kimlikleri şemada o karenin temaslarından oluşan bir enum'dur;
şema her çağrıda yeniden üretilir.

Kod her nedeni veriyle doğrular; doğrulanamayan madde reddedilir, sebebi brief'te kalır.
Seviye en fazla bir kademe ve yalnızca doğrulanmış bir nedenle değişir: yükseltme için
riski artıran ve kuralların seviyede zaten saymadığı (`level_basis`) bir neden, düşürme
için "dikkat_gerekmiyor" ve o temasa bağlı, kararı "consistent" bir rapor iddiası gerekir
(rapor doğrulama v2 kimlik iddialarını hiçbir zaman "consistent" saymaz; dost raporuyla
seviye düşmez). Raporun yükselttiği
temas düşürülemez; gösterilen rapor o temasa ait ve çelişkisiz olmalıdır (görev tanımı s2).

"Değerlendirme" metnini kod yazar: kabul edilen her madde için sabit Türkçe şablon, sayılar
bulgu alanlarından. LLM'den yalnızca kısa bir özet alınır; özette sayı, kimlik, bölge adı ya
da İngilizce terim geçerse özet atılır.

LLM cevap vermezse, süre aşılırsa ya da hiçbir model şemaya uymazsa `DecisionUnavailableError`
fırlatılır; servis otomatik özete geçer.
"""

import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, create_model, field_validator

from app.agent.brief_text import CARGO_TR, LEVEL_TR, TREND_TR, VERDICT_TR
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
from app.schemas.domain import HEAVY_CLASSES, RiskLevel

TASK = "reasoning"
PROMPT_PATH = Path(__file__).parent / "prompts" / "brief.md"
NO_ATTENTION: AttentionReason = "dikkat_gerekmiyor"

FactKey = Literal[
    "tur",
    "tip",
    "kesinlik",
    "uzaklik",
    "hareket",
    "duraklamalar",
    "yakin_duraklama",
    "cevrede_dolasma",
    "seviye",
    "dost",
    "gorsel",
    "notlar",
    "raporlar",
]
"""LLM girdisindeki temas olgularının anahtarları; `dayanak`'ta yalnızca bunlar gösterilebilir.

Girdi `contact_facts` ile bu anahtarlardan kurulur: LLM'in gösterebileceği anahtar ile
girdide gördüğü anahtar aynı listedir. Neden doğrulaması girdi metnine değil temas verisine
(`ContactFinding`) bakar.
"""

KIND_TR = {
    "matched": "eşleşmiş (tespit ve track)",
    "unregistered": "kayıt dışı (track'i yok, hareket geçmişi bilinmiyor)",
    "missed": "kaçırılmış (track karede, tespit yok)",
}
TYPE_TR = {"car": "otomobil", "van": "panelvan", "truck": "kamyon", "bus": "otobüs"}
CERTAINTY_TR = {
    "certain": "kesin",
    "likely": "olası",
    "weak": "zayıf",
    "unverified": "doğrulanamadı",
}
SOURCE_TR = {"official": "resmi", "third_party": "üçüncü taraf"}
CLAIM_TYPE_TR = {
    "observation": "gözlem",
    "friendly_claim": "dostluk iddiası",
    "threat_warning": "tehdit uyarısı",
    "rumor": "söylenti",
    "irrelevant": "ilgisiz",
}
COLOR_TR = {
    "beyaz": "beyaz",
    "siyah": "siyah",
    "gri": "gri",
    "kirmizi": "kırmızı",
    "mavi": "mavi",
    "yesil": "yeşil",
    "sari": "sarı",
    "turuncu": "turuncu",
    "kahverengi": "kahverengi",
    "bej": "bej",
    "mor": "mor",
}
_TYPE_WORD = re.compile(r"\b(car|van|truck|bus)\b")
COMPASS = ("kuzey", "kuzeydoğu", "doğu", "güneydoğu", "güney", "güneybatı", "batı", "kuzeybatı")

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
MAX_COMMENT_SENTENCES = 1
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
    dayanak: list[int | FactKey] = Field(
        description="Dayanılan olgu anahtarları ve bu temasa bağlı iddiaların numaraları"
    )
    seviye_onerisi: RiskLevel | None = Field(
        default=None, description="Seviyeyi en fazla bir kademe değiştirmek istersen yeni seviye"
    )
    yorum: str = Field(
        default="",
        description=(
            "Operatör için tek cümlelik analiz: bu davranışın ne anlama geldiği; "
            "sayı, kimlik, mesafe, bölge adı ve yön yok"
        ),
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


def compass(degrees: float) -> str:
    """Derece (kuzey = 0, saat yönünde) → sekiz yönden biri."""
    return COMPASS[round(degrees / 45) % 8]


def _distance_line(c: ContactFinding) -> str:
    m = c.motion
    now = f"şimdi {km(c.distance_to_base_m)}"
    if m is None:
        return now
    steps = [
        f"{label} {km(value)}"
        for label, value in (
            ("1 saat önce", m.distance_to_base_60min_ago_m),
            ("30 dk önce", m.distance_to_base_30min_ago_m),
        )
        if value is not None
    ]
    return " → ".join([*steps, now])


def _movement_line(m: MotionFinding) -> str:
    recent = [f"son 30 dk {TREND_TR[m.trend]}"]
    if m.trend != "stationary":
        recent.append(mps(m.recent_speed_mps))
    if m.heading_deg is not None:
        recent.append(f"yön {compass(m.heading_deg)}")
    return f"{', '.join(recent)}; 2 saatlik ortalama {mps(m.avg_speed_mps)}"


def _stops_line(m: MotionFinding) -> str:
    stops = []
    for i, st in enumerate(m.stops):
        ongoing = i == len(m.stops) - 1 and m.current_stop_minutes is not None
        minutes = f"en az {st.minutes}" if ongoing and m.stop_open_ended else str(st.minutes)
        state = ", sürüyor" if ongoing else ""
        stops.append(f"{st.start}–{st.end} ({minutes} dk{state}, üsse {km(st.distance_to_base_m)})")
    return "; ".join(stops) or "yok"


def _loiter_line(m: MotionFinding, levels: LevelRules) -> str:
    minutes = loiter_minutes(m, levels)
    if minutes == 0:
        return "yok"
    longest = max(
        (s for s in m.stops if s.distance_to_base_m < levels.loiter_m), key=lambda s: s.minutes
    )
    open_ended = longest is m.stops[-1] and m.current_stop_minutes is not None and m.stop_open_ended
    at_least = "en az " if open_ended else ""
    verdict = "aşıyor" if minutes >= levels.loiter_minutes else "altında"
    return f"{at_least}{minutes} dk, eşik {levels.loiter_minutes} dk: {verdict}"


def _circling_line(m: MotionFinding, levels: LevelRules) -> str:
    if not _is_circling(m, levels):
        return "yok"
    closest, farthest = km(m.base_distance_min_m), km(m.base_distance_max_m)
    band = closest if closest == farthest else f"{closest}–{farthest}"
    return f"var, üsse {band} bandında, {km(circling_path_m(m, levels))} yol"


def _type_line(c: ContactFinding) -> str:
    if c.effective_label is None:
        return "bilinmiyor"
    name = TYPE_TR[c.effective_label]
    return f"{name} (ağır araç)" if c.effective_label in HEAVY_CLASSES else name


def _visual_line(c: ContactFinding) -> str | None:
    v = c.visual
    if v is None:
        return None
    if not v.is_vehicle:
        return "araç görsel olarak seçilemedi"
    looks = [COLOR_TR[v.color]] if v.color else []
    looks += [CARGO_TR[v.cargo]] if v.cargo else []
    return ", ".join(["araç doğrulandı", *looks])


def _notes_line(c: ContactFinding) -> str | None:
    notes = []
    if c.is_weak:
        notes.append("zayıf tespit")
    if c.is_ambiguous:
        other = f", diğer aday {c.second_candidate.track_id}" if c.second_candidate else ""
        notes.append(f"belirsiz eşleşme{other}")
    if c.type_conflict:
        seen = ", ".join(sorted({TYPE_TR[o.label] for o in c.observed_labels}))
        notes.append(f"tip çelişkisi (görülen: {seen}), riskli olan kabul edildi")
    if c.position_estimated:
        notes.append("konum kestirildi")
    return "; ".join(notes) or None


def _level_line(c: ContactFinding) -> str:
    basis = ", ".join(c.level_basis) or "yok"
    return f"{LEVEL_TR[c.final_level]} (kuralların saydığı neden: {basis})"


def _report_line(f: ReportFinding) -> str:
    parts = [f"karar: {VERDICT_TR[f.verdict]}"]
    if f.dangerous_reassurance:
        parts.append("tehlikeli güvence")
    if f.context_flags:
        parts.append("bağlam: " + ", ".join(f.context_flags))
    # Gerekçe brief'te aynen kalır; LLM girdisinde tip adı İngilizce kalmasın.
    reasoning = _TYPE_WORD.sub(lambda m: TYPE_TR[m.group(0)], f.reasoning)
    parts.append(f"gerekçe: {reasoning}")
    what = CLAIM_TYPE_TR.get(f.claim_type, f.claim_type)
    return f"[{f.claim_id}] {f.report_time} {SOURCE_TR[f.source]} {what} — {'; '.join(parts)}"


def contact_facts(
    c: ContactFinding, findings: list[ReportFinding], levels: LevelRules
) -> list[tuple[FactKey, str]]:
    """Temasın olguları, kodla yazılmış kısa Türkçe satırlar (anahtar, değer).

    Sayılar virgüllü ve birimli; kod değerleri Türkçe; karşılaştırmaları (eşik, dolaşma)
    kod yapar. Bağlı rapor iddiaları `raporlar` altında, alt satırlarda verilir.
    """
    m = c.motion
    facts: list[tuple[FactKey, str | None]] = [
        ("tur", KIND_TR[c.kind]),
        ("tip", _type_line(c)),
        ("kesinlik", CERTAINTY_TR[c.certainty]),
        ("uzaklik", _distance_line(c)),
        ("hareket", _movement_line(m) if m else "kayıt yok"),
        ("duraklamalar", _stops_line(m) if m else None),
        ("yakin_duraklama", _loiter_line(m, levels) if m else None),
        ("cevrede_dolasma", _circling_line(m, levels) if m else None),
        ("seviye", _level_line(c)),
        ("dost", "doğrulanmış dost (resmi rapor)" if c.verified_friend else None),
        ("gorsel", _visual_line(c)),
        ("notlar", _notes_line(c)),
    ]
    linked = _linked(c, findings)
    if linked:
        facts.append(("raporlar", "\n".join(f"    {_report_line(f)}" for f in linked)))
    return [(key, value) for key, value in facts if value is not None]


def build_input(
    image_id: str,
    at: str,
    contacts: list[ContactFinding],
    findings: list[ReportFinding],
    levels: LevelRules,
) -> str:
    """Karar LLM'inin girdisi: temas başına Türkçe olgu satırları ve track'e bağlanmayan raporlar.

    Track'i olmayan iddia bölge düzeyinde olabilir ya da kayıt dışı bir temasa bağlanmış
    olabilir (ADR-0003); `ReportFinding` hangisi olduğunu taşımadığı için ayrı bölümdedir.

    Bölge adı verilmez: kararın hiçbir nedeni ona dayanmaz, özette de yasak.
    """
    lines = [f"Görüntü {image_id} · çekim anı {at}"]
    for label, c in zip(contact_labels(contacts), contacts, strict=True):
        lines += ["", f"Temas {label}"]
        for key, value in contact_facts(c, findings, levels):
            lines.append(f"  {key}:\n{value}" if key == "raporlar" else f"  {key}: {value}")
    linked = {f.claim_id for c in contacts for f in _linked(c, findings)}
    unlinked = [f for f in findings if f.claim_id not in linked]
    if unlinked:
        lines += [
            "",
            "Track'e bağlanmayan raporlar (bölge düzeyinde ya da kayıt dışı bir temasla ilgili)",
        ]
        lines += [f"  {_report_line(f)}" for f in unlinked]
    return "\n".join(lines)


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
        if any(about[i].needs_review for i in evidence):
            # Kurallar ile LLM ayrıştı: operatör bakmadan düşürme kanıtı olamaz.
            return f"{now} → {level}: gösterilen rapor operatör incelemesi bekliyor"
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


def summary_problem(
    text: str,
    zone_names: Sequence[str],
    *,
    name: str = "özet",
    where: str = "özette",
    max_sentences: int = MAX_SUMMARY_SENTENCES,
) -> str | None:
    """Özet (ya da madde yorumu) kodun denetleyemeyeceği bir olgu içeriyorsa atılma sebebi."""
    folded = text.translate(_ASCII).casefold()
    if _DIGIT_OR_ID.search(text) or _NUMBER_WORDS.search(folded):
        return f"{where} sayı ya da temas kimliği var"
    zones = [z for z in zone_names if z.translate(_ASCII).casefold() in folded]
    if zones:
        return f"{where} bölge adı var ({', '.join(zones)})"
    direction = _DIRECTIONS.search(folded)
    if direction:
        return f"{where} yön var ({direction.group(0)}); konumu kod yazar"
    english = _ENGLISH.search(text)
    if english:
        return f"{where} İngilizce terim var ({english.group(0)})"
    sentences = [s for s in re.split(r"[.!?…]+", text) if s.strip()]
    if len(sentences) > max_sentences:
        return f"{name} {max_sentences} cümleden uzun"
    return None


def comment_problem(text: str, zone_names: Sequence[str]) -> str | None:
    """Madde yorumu: özetle aynı sınırlar, tek cümle ve gerçek bir cümle."""
    words = [w for w in text.split() if any(ch.isalpha() for ch in w)]
    if len(words) < MIN_SUMMARY_WORDS:
        return "yorum boş ya da yer tutucu"
    return summary_problem(
        text, zone_names, name="yorum", where="yorumda", max_sentences=MAX_COMMENT_SENTENCES
    )


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
    zone_names: Sequence[str] = (),
) -> tuple[list[ContactFinding], list[AttentionFinding], int, int]:
    """Maddeleri veriyle doğrular; doğrulanmış nedenle önerilen seviye ayarını uygular.

    Bir temasın seviyesi en fazla bir kez değişir (±1 kademe); reddedilen bir öneri aynı temas
    için sonraki doğrulanmış öneriyi engellemez. LLM'in madde yorumu yalnızca doğrulanmış
    maddede ve özetle aynı sınırlar içindeyse (tek cümle) kalır.
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
        comment: str | None = proposal.yorum.strip() or None
        comment_rejected = None
        if comment and verified:
            comment_rejected = comment_problem(comment, zone_names)
        if comment_rejected or not verified:
            comment = None
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
                comment=comment,
                comment_rejected=comment_rejected,
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
    user = build_input(image_id, at, contacts, findings, levels)
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
    updated, attention, accepted, rejected = apply_attention(
        contacts, draft, findings, levels, [zone, *zone_names]
    )
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
