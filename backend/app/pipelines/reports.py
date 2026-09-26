"""KOL C: rapor iddialarını temaslarla karşılaştırır (ADR-0002: asimetrik güven).

Kararı kod verir. Bir iddia, **rapor saatinde** konumuna en yakın temasa bağlanır.
Raporlar riski serbestçe yükseltebilir. Düşürebilmeleri için kaynağın resmi olması ve
iddianın belirttiği her özelliğin (konum, zaman, tip, renk, yük) doğrulanması gerekir.
Renk ve yük, yalnızca iddia bunları belirtiyorsa görsel doğrulamaya (VLM) sorulur.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import time
from typing import Literal

from app.core.rules import ReportRules
from app.data_package import format_hhmm, to_minutes
from app.pipelines.geo import distance_m
from app.pipelines.vision import normalize_color
from app.schemas.api import Certainty, Effect, Verdict, VisualFinding
from app.schemas.claims import ClaimRecord, ClaimVehicleType
from app.schemas.domain import CargoState, GeoPoint, ReportSource, VehicleClass

Check = Literal["match", "mismatch", "unverified", "unspecified"]

DAY_WIDE_TYPES = frozenset({"friendly_claim", "threat_warning", "rumor"})
TYPE_GROUPS: dict[ClaimVehicleType, frozenset[VehicleClass]] = {
    "car": frozenset({VehicleClass.CAR}),
    "van": frozenset({VehicleClass.VAN}),
    "truck": frozenset({VehicleClass.TRUCK}),
    "bus": frozenset({VehicleClass.BUS}),
    "heavy": frozenset({VehicleClass.TRUCK, VehicleClass.BUS}),
    "light": frozenset({VehicleClass.CAR, VehicleClass.VAN}),
}


@dataclass(frozen=True)
class ContactView:
    """Rapor karşılaştırması için temasın bilinenleri."""

    track_id: str | None
    label: VehicleClass | None
    location: GeoPoint


@dataclass(frozen=True)
class ClaimEvaluation:
    record: ClaimRecord
    track_id: str | None
    verdict: Verdict
    certainty: Certainty
    effect: Effect
    reasoning: str


PositionAt = Callable[[str, time], GeoPoint | None]
"""Bir track'in verilen andaki (ya da hemen önceki) konumu."""

Observe = Callable[[str], VisualFinding | None]
"""Track'e ait temasın görsel doğrulaması; bakılamıyorsa `None`. Yalnızca gerekince çağrılır."""

VISUAL_CHECKS = frozenset({"renk", "yük"})


def _no_visual(track_id: str) -> None:
    return None


def _type_check(claimed: ClaimVehicleType | None, label: VehicleClass | None) -> Check:
    if claimed is None or claimed == "unknown":
        return "unspecified"
    if label is None:
        return "unverified"
    return "match" if label in TYPE_GROUPS[claimed] else "mismatch"


def _color_check(claimed: str | None, visual: VisualFinding | None) -> Check:
    if not claimed:
        return "unspecified"
    color = normalize_color(claimed)
    if color is None or visual is None or visual.color is None:
        return "unverified"
    return "match" if color == visual.color else "mismatch"


def _cargo_check(claimed: CargoState | None, visual: VisualFinding | None) -> Check:
    if claimed is None:
        return "unspecified"
    if visual is None or visual.cargo is None:
        return "unverified"
    return "match" if claimed == visual.cargo else "mismatch"


def evaluate_claims(
    records: list[ClaimRecord],
    contacts: list[ContactView],
    *,
    image_center: GeoPoint,
    image_zone: str,
    now: time,
    rules: ReportRules,
    position_at: PositionAt,
    observe: Observe = _no_visual,
) -> list[ClaimEvaluation]:
    """Çekim anına kadarki iddiaları değerlendirir; görüntüyle ilgisiz olanlar listeye girmez."""
    window_start = to_minutes(now) - rules.window_minutes
    results: list[ClaimEvaluation] = []
    for record in records:
        claim, report = record.claim, record.report
        if report.time > now:
            continue
        in_window = to_minutes(report.time) >= window_start
        located = claim.location_type == "coordinate" and claim.lat is not None
        if claim.location_type == "zone":
            if in_window and claim.zone == image_zone:
                results.append(
                    ClaimEvaluation(
                        record,
                        None,
                        "unverifiable",
                        "unverified",
                        "none",
                        "bölge düzeyinde iddia; belirli bir temasla karşılaştırılamaz",
                    )
                )
            continue
        if not located:
            if claim.claim_type in DAY_WIDE_TYPES:
                when = claim.time_reference or format_hhmm(report.time)
                results.append(
                    ClaimEvaluation(
                        record,
                        None,
                        "unverifiable",
                        "unverified",
                        "none",
                        f"konumu belirsiz ({when}); hiçbir temasla karşılaştırılamaz",
                    )
                )
            continue
        if not in_window:
            continue
        assert claim.lat is not None and claim.lon is not None
        evaluation = _evaluate_located(
            record,
            GeoPoint(claim.lat, claim.lon),
            contacts,
            image_center,
            rules,
            position_at,
            observe,
        )
        if evaluation is not None:
            results.append(evaluation)
    return results


def _evaluate_located(
    record: ClaimRecord,
    point: GeoPoint,
    contacts: list[ContactView],
    image_center: GeoPoint,
    rules: ReportRules,
    position_at: PositionAt,
    observe: Observe,
) -> ClaimEvaluation | None:
    claim, report = record.claim, record.report
    when = format_hhmm(report.time)

    at_report: list[tuple[float, ContactView]] = []
    known_at_report: set[str] = set()  # rapor saatinde konumu kayıtlı track'ler
    for c in contacts:
        pos = position_at(c.track_id, report.time) if c.track_id else None
        if pos is not None and c.track_id:
            known_at_report.add(c.track_id)
        if pos is not None and (d := distance_m(pos, point)) <= rules.match_m:
            at_report.append((d, c))
    now_near = [(d, c) for c in contacts if (d := distance_m(c.location, point)) <= rules.match_m]
    relevant = distance_m(image_center, point) <= rules.relevance_m or at_report or now_near
    if not relevant:
        return None

    linked = min(at_report, key=lambda x: x[0])[1] if at_report else None
    track_id = linked.track_id if linked else None

    if claim.claim_type == "irrelevant":
        return ClaimEvaluation(
            record, track_id, "irrelevant", "likely", "none", "üs güvenliğiyle ilgisiz"
        )
    if claim.claim_type == "rumor":
        return ClaimEvaluation(
            record, track_id, "unverifiable", "unverified", "none", "doğrulanmamış ihbar/söylenti"
        )

    if linked is None:
        # Çelişki ancak track'in rapor saatinde başka bir yerde olduğu biliniyorsa vardır;
        # o saatte kaydı olmayan track için veri yok, çelişki de yok.
        tracked_now = [(d, c) for d, c in now_near if c.track_id in known_at_report]
        if tracked_now:
            contact = min(tracked_now, key=lambda x: x[0])[1]
            return ClaimEvaluation(
                record,
                contact.track_id,
                "contradicts",
                "likely",
                "raises",
                f"rapor saat {when} için bu noktada araç bildiriyor; {contact.track_id} o saatte "
                "orada değildi (kendi track'iyle çelişiyor)",
            )
        return ClaimEvaluation(
            record,
            None,
            "unverifiable",
            "unverified",
            "none",
            f"saat {when} itibarıyla bu noktada kayıtlı bir temas yok; karşılaştırılamadı",
        )

    needs_visual = bool(claim.color) or claim.cargo is not None
    visual = observe(track_id) if needs_visual and track_id else None
    checks = {
        "tip": _type_check(claim.vehicle_type, linked.label),
        "renk": _color_check(claim.color, visual),
        "yük": _cargo_check(claim.cargo, visual),
    }
    mismatched = [name for name, v in checks.items() if v == "mismatch"]
    unverified = [name for name, v in checks.items() if v == "unverified"]
    friendly = claim.claim_type == "friendly_claim"
    official = report.source == ReportSource.OFFICIAL

    if mismatched:
        # Yalnızca VLM'in gördüğüne dayanan çelişki "olası"; tip çelişkisi kesin.
        visual_only = set(mismatched) <= VISUAL_CHECKS
        return ClaimEvaluation(
            record,
            track_id,
            "contradicts",
            "likely" if visual_only else "certain",
            "raises",
            f"{track_id} konum ve saat uyuyor ama {', '.join(mismatched)} uyuşmuyor",
        )
    if friendly and unverified:
        return ClaimEvaluation(
            record,
            track_id,
            "unverifiable",
            "unverified",
            "none",
            f"dostluk iddiası doğrulanamadı: {', '.join(unverified)} kontrol edilemedi",
        )
    if friendly and not official:
        return ClaimEvaluation(
            record,
            track_id,
            "consistent",
            "likely",
            "none",
            f"{track_id} ile uyuşuyor ama üçüncü taraf dostluk iddiası riski düşüremez",
        )
    if friendly:
        return ClaimEvaluation(
            record,
            track_id,
            "consistent",
            "certain",
            "lowers",
            f"resmi dostluk iddiası {track_id} ile konum, saat ve belirtilen her özellikte "
            "uyuşuyor: doğrulanmış dost",
        )
    certainty: Certainty = "likely" if unverified else "certain"
    note = f" ({', '.join(unverified)} doğrulanamadı)" if unverified else ""
    if claim.claim_type == "threat_warning":
        return ClaimEvaluation(
            record,
            track_id,
            "consistent",
            certainty,
            "raises",
            f"{track_id} hakkında tehdit uyarısı{note}",
        )
    return ClaimEvaluation(
        record,
        track_id,
        "consistent",
        certainty,
        "none",
        f"{track_id} ile saat {when} konumunda uyuşuyor{note}",
    )
