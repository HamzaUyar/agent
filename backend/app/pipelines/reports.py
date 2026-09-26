"""KOL C: rapor iddialarını temaslarla karşılaştırır (ADR-0002: asimetrik güven).

Kararı kod verir. Bir iddia, **çekim anında** konumuna en yakın temasa bağlanır; organizatör
rapor koordinatlarını aracın çekim anındaki konumundan üretmiş. Saat ayrı bir doğrulama
özelliğidir: bağlanan temasın rapor saatindeki konumu iddia noktasıyla karşılaştırılır.
Raporlar riski serbestçe yükseltebilir. Düşürebilmeleri için kaynağın resmi olması ve
iddianın belirttiği her özelliğin (konum, saat, tip, renk, yük) doğrulanması gerekir.
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
from app.schemas.api import Certainty, Effect, TimeCheck, Verdict, VisualFinding
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
    time_check: TimeCheck = "unknown"


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
            now,
            rules,
            position_at,
            observe,
        )
        if evaluation is not None:
            results.append(evaluation)
    return results


TIME_NOTE: dict[TimeCheck, str] = {
    "ok": "",
    "mismatch": "; rapor saatindeki konumu uyuşmuyor",
    "unknown": "; rapor saatindeki konumu bilinmiyor",
}


def _time_check(
    contact: ContactView,
    point: GeoPoint,
    when: time,
    now: time,
    rules: ReportRules,
    position_at: PositionAt,
) -> TimeCheck:
    """Bağlanan temasın rapor saatinde iddia noktasında olup olmadığı.

    Rapor çekim anındaysa temasın şimdiki konumu kullanılır: çekim saati 5 dakikalık
    adıma denk gelmiyorsa `position_at` bir önceki adımın konumunu verir.
    """
    if when == now:
        return "ok" if distance_m(contact.location, point) <= rules.match_m else "mismatch"
    pos = position_at(contact.track_id, when) if contact.track_id else None
    if pos is None:
        return "unknown"
    return "ok" if distance_m(pos, point) <= rules.match_m else "mismatch"


def _evaluate_located(
    record: ClaimRecord,
    point: GeoPoint,
    contacts: list[ContactView],
    image_center: GeoPoint,
    now: time,
    rules: ReportRules,
    position_at: PositionAt,
    observe: Observe,
) -> ClaimEvaluation | None:
    claim, report = record.claim, record.report
    when = format_hhmm(report.time)

    near = [(d, c) for c in contacts if (d := distance_m(c.location, point)) <= rules.bind_now_m]
    if distance_m(image_center, point) > rules.relevance_m and not near:
        return None

    linked = min(near, key=lambda x: x[0])[1] if near else None
    track_id = linked.track_id if linked else None
    time_check = (
        _time_check(linked, point, report.time, now, rules, position_at) if linked else "unknown"
    )

    def result(
        verdict: Verdict, certainty: Certainty, effect: Effect, reasoning: str
    ) -> ClaimEvaluation:
        if linked is not None and track_id is None and effect != "none":
            # Rapor etkileri temasa track'i üzerinden uygulanır; kayıt dışı temasın seviyesi
            # rapordan etkilenmez (ADR-0003).
            effect = "none"
            reasoning += "; kayıt dışı temasın seviyesine uygulanmadı"
        return ClaimEvaluation(record, track_id, verdict, certainty, effect, reasoning, time_check)

    if claim.claim_type == "irrelevant":
        return result("irrelevant", "likely", "none", "üs güvenliğiyle ilgisiz")
    if claim.claim_type == "rumor":
        return result("unverifiable", "unverified", "none", "doğrulanmamış ihbar/söylenti")

    if linked is None:
        return result(
            "unverifiable",
            "unverified",
            "none",
            "çekim anında bu noktada bir temas yok; karşılaştırılamadı",
        )

    who = track_id or "kayıt dışı temas"
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
    time_note = TIME_NOTE[time_check]

    if mismatched:
        # Yalnızca VLM'in gördüğüne dayanan çelişki "olası"; tip çelişkisi kesin.
        visual_only = set(mismatched) <= VISUAL_CHECKS
        return result(
            "contradicts",
            "likely" if visual_only else "certain",
            "raises",
            f"{who} iddianın konumunda ama {', '.join(mismatched)} uyuşmuyor{time_note}",
        )
    if friendly and unverified:
        return result(
            "unverifiable",
            "unverified",
            "none",
            f"dostluk iddiası doğrulanamadı: {', '.join(unverified)} kontrol edilemedi{time_note}",
        )
    if friendly and track_id is None:
        return result(
            "unverifiable",
            "unverified",
            "none",
            "dostluk iddiası doğrulanamadı: kayıt dışı temasın hareket kaydı yok",
        )
    if friendly and time_check != "ok":
        # Düşürmek için saat de tutmalı (ADR-0002): rapor saatinde araç orada değilse
        # ya da o saatteki konumu bilinmiyorsa iddia bu araca ait olmayabilir.
        return result(
            "unverifiable",
            "unverified",
            "none",
            f"dostluk iddiası doğrulanamadı: {who} konumda ama saat {when} "
            + ("konumu iddiayla uyuşmuyor" if time_check == "mismatch" else "konumu bilinmiyor"),
        )
    if friendly and not official:
        return result(
            "consistent",
            "likely",
            "none",
            f"{who} ile uyuşuyor ama üçüncü taraf dostluk iddiası riski düşüremez",
        )
    if friendly:
        return result(
            "consistent",
            "certain",
            "lowers",
            f"resmi dostluk iddiası {who} ile konum, saat ve belirtilen her özellikte "
            "uyuşuyor: doğrulanmış dost",
        )
    certainty: Certainty = "likely" if unverified or time_check != "ok" else "certain"
    note = f" ({', '.join(unverified)} doğrulanamadı)" if unverified else ""
    if claim.claim_type == "threat_warning":
        return result(
            "consistent", certainty, "raises", f"{who} hakkında tehdit uyarısı{note}{time_note}"
        )
    where = f"konumunda ve saat {when} itibarıyla" if time_check == "ok" else "konumunda"
    return result(
        "consistent", certainty, "none", f"{who} iddianın {where} uyuşuyor{note}{time_note}"
    )
