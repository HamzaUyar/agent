"""Brief ve adım özetlerinin Türkçe metinleri; yalnızca biçimlendirir, hesap yapmaz."""

from collections import defaultdict

from app.formatting import km, mps
from app.pipelines.matching import MatchResult
from app.pipelines.motion import Position
from app.schemas.api import ContactFinding, MotionFinding, ReportFinding
from app.schemas.domain import RiskLevel

LEVEL_TR = {"low": "DÜŞÜK", "medium": "ORTA", "high": "YÜKSEK", "critical": "KRİTİK"}
TREND_TR = {
    "approaching": "üsse yaklaşıyor",
    "receding": "üsten uzaklaşıyor",
    "stationary": "yerinde duruyor",
    "passing": "üsse yaklaşmadan geçiyor",
    "unknown": "hareket eğilimi belirsiz",
}
CARGO_TR = {"loaded": "yüklü", "empty": "boş"}
VERDICT_TR = {
    "consistent": "tutarlı",
    "contradicts": "çelişkili",
    "unverifiable": "doğrulanamaz",
    "irrelevant": "ilgisiz",
}


def reports_summary(findings: list[ReportFinding]) -> str:
    if not findings:
        return "İlgili rapor yok"
    counts: dict[str, int] = defaultdict(int)
    for f in findings:
        counts[VERDICT_TR[f.verdict]] += 1
    return f"{len(findings)} iddia: " + ", ".join(f"{n} {v}" for v, n in counts.items())


def match_summary(matches: list[MatchResult], missed: list[Position]) -> str:
    parts = []
    for m in matches:
        if m.track is None:
            parts.append("track yok (kayıt dışı)")
        else:
            note = " · belirsiz" if m.ambiguous else ""
            parts.append(f"{m.track.track_id} · {m.track.distance_m:.0f} m{note}")
    parts += [f"{p.track_id} karede ama tespit yok (kaçırılmış)" for p in missed]
    return ", ".join(parts) or "eşleşecek tespit yok"


def contact_notes(c: ContactFinding) -> list[str]:
    notes = []
    if c.is_weak:
        if c.visual is None:
            notes.append("zayıf tespit")
        elif c.visual.is_vehicle:
            notes.append("zayıf tespit, görsel olarak araç doğrulandı")
        else:
            notes.append("zayıf tespit, araç görsel olarak seçilemedi (hareket kaydı var)")
    if c.visual:
        looks: list[str] = [c.visual.color] if c.visual.color else []
        looks += [CARGO_TR[c.visual.cargo]] if c.visual.cargo else []
        notes.append(f"görsel: {', '.join(looks) or 'renk ve yük seçilemedi'}")
    if c.is_ambiguous and c.second_candidate:
        notes.append(f"belirsiz eşleşme, diğer aday {c.second_candidate.track_id}")
    if c.position_estimated:
        notes.append("konum kestirildi")
    if c.type_conflict:
        seen = ", ".join(f"{o.image_id}: {o.label}" for o in c.observed_labels)
        notes.append(f"tip çelişkisi ({seen}); {c.effective_label} kabul edildi")
    return notes


def movement_text(m: MotionFinding) -> str:
    parts = [TREND_TR[m.trend]]
    if m.distance_to_base_30min_ago_m is not None:
        hour = (
            f"1 saat önce {km(m.distance_to_base_60min_ago_m)}, "
            if m.distance_to_base_60min_ago_m is not None
            else ""
        )
        parts.append(
            f"üsse uzaklık {hour}30 dk önce {km(m.distance_to_base_30min_ago_m)}, "
            f"şimdi {km(m.distance_to_base_m)}"
        )
    parts.append(f"son 30 dk {mps(m.recent_speed_mps)}, 2 saatlik ortalama {mps(m.avg_speed_mps)}")
    if m.heading_deg is not None:
        parts.append(f"yön {m.heading_deg:.0f}°")
    if m.stops:
        parts.append(
            "duraklamalar: " + ", ".join(f"{st.start} ({st.minutes} dk)" for st in m.stops)
        )
    return ", ".join(parts)


def brief_text(
    image_id: str,
    zone: str,
    at: str,
    level: RiskLevel,
    contacts: list[ContactFinding],
    findings: list[ReportFinding],
    action: str,
    assessment: str | None,
    *,
    automatic: bool,
) -> str:
    """Başlık, bulgular ve eylem kodla; LLM varsa değerlendirme paragrafı ondan gelir."""
    header = f"{image_id} · {zone} · {at} · Risk: {LEVEL_TR[level]}"
    lines = [f"{header} (otomatik özet)" if automatic else header]
    if assessment:
        lines.append(f"Değerlendirme: {assessment}")
    if not contacts:
        lines.append("Karede temas yok.")
    for c in contacts:
        who = c.track_id or "kayıt dışı temas"
        label = c.effective_label or "tipi bilinmiyor"
        movement = movement_text(c.motion) if c.motion else "hareket geçmişi yok"
        notes = contact_notes(c)
        if c.adjustment_reason:
            notes.append(f"LLM ayarı: {c.adjustment_reason.rstrip('. ')}")
        lines.append(
            f"- {who} ({label}): üsse {km(c.distance_to_base_m)}, {movement}; "
            f"seviye {LEVEL_TR[c.final_level]} ({'; '.join(c.level_reasons)})."
            + (f" Not: {'; '.join(notes)}." if notes else "")
        )
    if findings:
        lines.append("Raporlar:")
        lines += [
            f"- {f.report_time} ({'resmi' if f.source == 'official' else 'üçüncü taraf'}): "
            f"{VERDICT_TR[f.verdict]}; {f.reasoning}."
            for f in findings
        ]
    lines.append(f"Önerilen eylem: {action}")
    return "\n".join(lines)


def sources(
    detector: str, contacts: list[ContactFinding], findings: list[ReportFinding]
) -> list[str]:
    result = [f"tespit: {detector}", "konum: köşe koordinatları"]
    result += [f"hareket: {c.track_id}" for c in contacts if c.track_id]
    result += sorted({f"görsel: {c.visual.model}" for c in contacts if c.visual})
    result += sorted({f"rapor: {f.report_time}" for f in findings})
    return result
