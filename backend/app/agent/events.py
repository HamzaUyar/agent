"""Değerlendirme adımlarının SSE yükleri: her aşamanın çıktısından özet ve `data`.

Frontend'le sözleşme buradadır: adların sırası `EvaluationService.evaluate`'te, her adımın
`data` alanlarının yapısı burada. Alan eklemek ya da çıkarmak arayüzü bozar.
"""

from typing import Any

from app.agent.brief_text import LEVEL_TR, TREND_TR, match_summary, reports_summary
from app.agent.stages import (
    ClaimEvaluations,
    Contacts,
    Detections,
    FinalDecision,
    ImageContext,
    Matches,
    RiskResult,
    bbox,
    is_weak,
    latlon,
)
from app.core.rules import DetectionRules
from app.formatting import km
from app.pipelines.matching import LocatedDetection
from app.schemas.api import Brief

Payload = tuple[str, dict[str, Any]]
"""Adımın tek satırlık özeti ve `data` alanı."""


def image(ctx: ImageContext) -> Payload:
    img = ctx.image
    return (
        f"{img.width_px}×{img.height_px} px · {ctx.at} · {ctx.zone}",
        {
            "image_id": img.image_id,
            "zone": ctx.zone,
            "capture_time": ctx.at,
            "corners": [latlon(p).model_dump() for p in img.corners.as_ring()[:4]],
        },
    )


def detections(d: Detections, rules: DetectionRules) -> Payload:
    return (
        f"{len(d.usable)} araç tespit edildi"
        + (f" ({d.ignored} düşük güvenli kutu yok sayıldı)" if d.ignored else ""),
        {
            "detections": [
                {
                    "label": x.label.value,
                    "confidence": x.confidence,
                    "bbox": [x.x, x.y, x.w, x.h],
                    "weak": is_weak(x, rules),
                }
                for x in d.usable
            ],
            "ignored": d.ignored,
        },
    )


def locations(located: tuple[LocatedDetection, ...]) -> Payload:
    return (
        "Kutu merkezleri köşe koordinatlarından konuma çevrildi",
        {"locations": [latlon(item.location).model_dump() for item in located]},
    )


def matches(m: Matches, visually_unconfirmed: list[str]) -> Payload:
    return (
        match_summary(list(m.matches), list(m.missed)),
        {
            "matches": [
                {
                    "bbox": list(bbox(x.located.detection)),
                    "track_id": x.track.track_id if x.track else None,
                    "distance_m": x.track.distance_m if x.track else None,
                    "ambiguous": x.ambiguous,
                    "second": (
                        {"track_id": x.second.track_id, "distance_m": x.second.distance_m}
                        if x.second
                        else None
                    ),
                }
                for x in m.matches
            ],
            "missed": [p.track_id for p in m.missed],
            "estimated_positions": sorted(m.estimated),
            "visually_unconfirmed": visually_unconfirmed,
        },
    )


def motions(contacts: Contacts) -> Payload:
    cs = contacts.contacts
    return (
        "; ".join(
            f"{c.track_id}: {TREND_TR[c.motion.trend]}, üsse {km(c.motion.distance_to_base_m)}"
            for c in cs
            if c.motion and c.track_id
        )
        or "hareket kaydı olan temas yok",
        {
            "motions": {c.track_id: c.motion.model_dump() for c in cs if c.motion and c.track_id},
            # Temel seviyenin girdileri: tip ve mesafe Kol A'dan, eğilim ve duraklama Kol B'den.
            "contacts": [
                {
                    "kind": c.kind,
                    "track_id": c.track_id,
                    "label": c.effective_label,
                    "distance_to_base_m": c.distance_to_base_m,
                    "trend": c.motion.trend if c.motion else None,
                    "base_level": c.base_level,
                    "reasons": c.level_reasons,
                    "certainty": c.certainty,
                }
                for c in cs
            ],
        },
    )


def reports(r: ClaimEvaluations) -> Payload:
    return (
        reports_summary(list(r.findings)),
        {
            "findings": [f.model_dump() for f in r.findings],
            "visual_checks": [
                {"bbox": list(box), **(v.model_dump() if v else {"result": None})}
                for box, v in r.visuals.items()
            ],
        },
    )


def risk(r: RiskResult) -> Payload:
    return (
        f"Görüntü seviyesi: {LEVEL_TR[r.level]}",
        {
            "level": r.level,
            "contacts": [
                {
                    "kind": c.kind,
                    "track_id": c.track_id,
                    "base_level": c.base_level,
                    "final_level": c.final_level,
                    "reasons": c.level_reasons,
                }
                for c in r.contacts
            ],
        },
    )


def decision(d: FinalDecision) -> Payload:
    return (
        f"{d.model}: {d.accepted} ayar kabul, {d.rejected} red"
        if d.model
        else f"Otomatik özet: {d.fallback_reason}",
        {
            "model": d.model,
            "fallback_reason": d.fallback_reason,
            "contacts": [
                {
                    "track_id": c.track_id,
                    "final_level": c.final_level,
                    "adjustment_reason": c.adjustment_reason,
                    "adjustment_rejected": c.adjustment_rejected,
                }
                for c in d.contacts
            ],
        },
    )


def brief(b: Brief) -> Payload:
    return f"Risk: {LEVEL_TR[b.risk_level]} · {b.recommended_action}", b.model_dump()
