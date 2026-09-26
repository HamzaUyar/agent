"""KOL C: rapor iddialarını temaslarla karşılaştırır (ADR-0002: asimetrik güven).

Kararı kod verir. Bir iddia, **çekim anında** konumuna en yakın temasa bağlanır; organizatör
rapor koordinatlarını aracın çekim anındaki konumundan üretmiş. Saat ayrı bir doğrulama
özelliğidir: bağlanan temasın rapor saatindeki konumu iddia noktasıyla karşılaştırılır.
Hareket iddiası (duruyor, yaklaşıyor, uzaklaşıyor, geçiyor) temasın çekim anındaki hareketiyle
karşılaştırılır; track verisine dayandığı için tip gibi kesin bir kontroldür.
Çelişkide rapor değil tespit esas alınır (görev tanımı s2): çelişen iddia seviyeyi
değiştirmez, yalnızca not düşülür. Tutarlı bir tehdit uyarısı riski yükseltebilir. Raporların
riski düşürebilmesi için kaynağın resmi olması ve iddianın belirttiği her özelliğin (konum,
saat, tip, hareket, renk, yük) doğrulanması gerekir.
Renk ve yük, yalnızca iddia bunları belirtiyorsa görsel doğrulamaya (VLM) sorulur.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import time
from typing import Literal

from app.core.rules import ReportRules
from app.data_package import format_hhmm, to_minutes
from app.pipelines.geo import distance_m
from app.pipelines.report_parser import rounding_error_m
from app.pipelines.vision import normalize_color
from app.schemas.api import (
    Certainty,
    Effect,
    MotionFinding,
    TimeCheck,
    Verdict,
    VisualFinding,
)
from app.schemas.claims import ClaimBehavior, ClaimRecord, ClaimVehicleType
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
    motion: MotionFinding | None = None


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

InFrame = Callable[[GeoPoint], bool]
"""Nokta görüntünün kapladığı alanda mı."""

VISUAL_CHECKS = frozenset({"renk", "yük"})
# Tespit modelinin gördüğüne dayanan kontroller: uyuşmazlıkları "olası" kesinlikte.
DETECTOR_CHECKS = VISUAL_CHECKS | {"sayı"}


def _no_visual(track_id: str) -> None:
    return None


def _outside(point: GeoPoint) -> bool:
    return False


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


TREND_TR = {
    "approaching": "üsse yaklaşıyor",
    "receding": "üsten uzaklaşıyor",
    "stationary": "yerinde duruyor",
    "passing": "üsse yaklaşmadan geçiyor",
    "unknown": "hareketi belirsiz",
}
BEHAVIOR_TR: dict[ClaimBehavior, str] = {
    "approaching": "üsse yaklaşıyor",
    "receding": "uzaklaşıyor",
    "transit": "transit geçiyor",
}
# Beklenen eğilimler; `stationary` ve `moving` duraklamaya göre ayrıca değerlendirilir.
BEHAVIOR_TRENDS: dict[ClaimBehavior, frozenset[str]] = {
    "approaching": frozenset({"approaching"}),
    "receding": frozenset({"receding"}),
    "transit": frozenset({"passing", "receding"}),
}


def stop_minutes_claimed(time_reference: str | None, long_stop_minutes: int) -> int | None:
    """ "40 dakikadir" → 40, "bir saatten uzun" → 60, "uzun suredir" → `long_stop_minutes`."""
    if not time_reference:
        return None
    text = time_reference.lower()
    if m := re.search(r"(\d+)\s*dakika", text):
        return int(m.group(1))
    if m := re.search(r"(\d+|bir)\s*saat", text):
        return 60 * (1 if m.group(1) == "bir" else int(m.group(1)))
    if "uzun" in text:
        return long_stop_minutes
    return None


def _behavior_check(
    claimed: ClaimBehavior | None, stop_minutes: int | None, motion: MotionFinding | None
) -> tuple[Check, str]:
    """Hareket iddiası temasın çekim anındaki hareketiyle; ikinci değer uyuşmazlığın açıklaması."""
    if claimed is None or claimed not in (*BEHAVIOR_TRENDS, "stationary", "moving"):
        return "unspecified", ""
    if motion is None or motion.trend == "unknown":
        return "unverified", ""
    stopped = motion.current_stop_minutes is not None or motion.trend == "stationary"
    actual = f"{TREND_TR[motion.trend]}, son 30 dk {motion.recent_speed_mps:.1f} m/s"
    if claimed == "moving":
        return ("mismatch", "iddia hareket halinde diyor, " + actual) if stopped else ("match", "")
    if claimed == "stationary":
        if not stopped:
            return "mismatch", "iddia duruyor diyor, " + actual
        minutes = motion.current_stop_minutes
        if stop_minutes is None or (minutes is not None and minutes >= stop_minutes):
            return "match", ""
        if minutes is None or motion.stop_open_ended:
            # Eğilim "duruyor" ama duraklama kaydı yok, ya da kayıt duraklamanın ortasında
            # başlıyor: süre bilinmiyor.
            return "unverified", ""
        return "mismatch", f"iddia en az {stop_minutes} dk duruyor diyor, duraklama {minutes} dk"
    if motion.trend in BEHAVIOR_TRENDS[claimed]:
        return "match", ""
    return "mismatch", f"iddia {BEHAVIOR_TR[claimed]} diyor, " + actual


def _count_check(claimed: int | None, seen: int, rules: ReportRules) -> Check:
    """İddia edilen sayı, noktanın çevresinde görülen temas sayısıyla (tipten bağımsız)."""
    if claimed is None or claimed < 2:
        return "unspecified"  # tek araç: bağlanan temas zaten orada
    return "match" if seen >= claimed * rules.count_ratio else "mismatch"


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
    in_frame: InFrame = _outside,
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
                    _evaluate_zone_type(record, contacts)
                    or ClaimEvaluation(
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
            in_frame,
        )
        if evaluation is not None:
            results.append(evaluation)
    return results


def _evaluate_zone_type(record: ClaimRecord, contacts: list[ContactView]) -> ClaimEvaluation | None:
    """Görüntünün bölgesini anan tip gözlemi karedeki tespitlerle (s2: tip karşılaştırması).

    Kare bölgenin yalnızca bir parçası: "yalnızca hafif araç" iddiası karede ağır araç
    görülürse çelişir; "ağır araç var" iddiası ancak karede görülürse doğrulanır. Tespite
    dayandığı ve rapor çekimden önce olduğu için kesinlik "olası"; seviye değişmez.
    """
    claim = record.claim
    if claim.claim_type != "observation" or claim.vehicle_type not in ("light", "heavy"):
        return None
    when = format_hhmm(record.report.time)
    heavy = [c for c in contacts if c.label in TYPE_GROUPS["heavy"]]
    if claim.vehicle_type == "light" and heavy:
        c = heavy[0]
        who = c.track_id or "kayıt dışı temas"
        label = c.label.value if c.label else ""
        return ClaimEvaluation(
            record,
            c.track_id,
            "contradicts",
            "likely",
            "none",
            f"bölgede yalnızca hafif araç dendi (saat {when}) ama karede ağır araç var "
            f"({who}, {label}); tespit esas alındı",
        )
    if claim.vehicle_type == "light" and any(c.label is not None for c in contacts):
        return ClaimEvaluation(
            record,
            None,
            "consistent",
            "likely",
            "none",
            "bölgede yalnızca hafif araç iddiası karedeki tespitlerle uyuşuyor",
        )
    if claim.vehicle_type == "heavy" and heavy:
        return ClaimEvaluation(
            record,
            heavy[0].track_id,
            "consistent",
            "likely",
            "none",
            "bölgede ağır araç iddiası karedeki tespitle uyuşuyor",
        )
    return None


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
    slack_m: float,
) -> TimeCheck:
    """Bağlanan temasın rapor saatinde iddia noktasında olup olmadığı.

    Rapor çekim anındaysa temasın şimdiki konumu kullanılır: çekim saati 5 dakikalık
    adıma denk gelmiyorsa `position_at` bir önceki adımın konumunu verir.
    `slack_m`: rapordaki koordinatın yuvarlama payı.
    """
    limit = rules.match_m + slack_m
    if when == now:
        return "ok" if distance_m(contact.location, point) <= limit else "mismatch"
    pos = position_at(contact.track_id, when) if contact.track_id else None
    if pos is None:
        return "unknown"
    return "ok" if distance_m(pos, point) <= limit else "mismatch"


def _evaluate_located(
    record: ClaimRecord,
    point: GeoPoint,
    contacts: list[ContactView],
    image_center: GeoPoint,
    now: time,
    rules: ReportRules,
    position_at: PositionAt,
    observe: Observe,
    in_frame: InFrame,
) -> ClaimEvaluation | None:
    claim, report = record.claim, record.report
    when = format_hhmm(report.time)

    # Az ondalıklı koordinat (ör. "39.944N") gerçek noktadan onlarca metre sapabilir.
    slack = rounding_error_m(report.text, point)
    near = [
        (d, c) for c in contacts if (d := distance_m(c.location, point)) <= rules.bind_now_m + slack
    ]
    if distance_m(image_center, point) > rules.relevance_m and not near:
        return None

    linked = min(near, key=lambda x: x[0])[1] if near else None
    track_id = linked.track_id if linked else None
    time_check = (
        _time_check(linked, point, report.time, now, rules, position_at, slack)
        if linked
        else "unknown"
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
        if in_frame(point):
            # Nokta karenin içinde ama orada ne tespit ne track var: görüntü iddiayı
            # desteklemiyor (s2: çelişkide tespit esas). Model araç kaçırmış olabilir: "olası".
            return result(
                "contradicts",
                "likely",
                "none",
                "iddianın noktası karenin içinde ama çekim anında orada araç yok; "
                "tespit esas alındı",
            )
        return result(
            "unverifiable",
            "unverified",
            "none",
            "çekim anında bu noktada bir temas yok; karşılaştırılamadı",
        )

    who = track_id or "kayıt dışı temas"
    needs_visual = bool(claim.color) or claim.cargo is not None
    visual = observe(track_id) if needs_visual and track_id else None
    seen = len(
        {id(c) for c in contacts if distance_m(c.location, point) <= rules.count_radius_m}
        | {id(linked)}
    )
    behavior, behavior_note = _behavior_check(
        claim.behavior,
        stop_minutes_claimed(claim.time_reference, rules.long_stop_minutes),
        linked.motion,
    )
    checks = {
        "tip": _type_check(claim.vehicle_type, linked.label),
        "hareket": behavior,
        "sayı": _count_check(claim.vehicle_count, seen, rules),
        "renk": _color_check(claim.color, visual),
        "yük": _cargo_check(claim.cargo, visual),
    }
    mismatched = [name for name, v in checks.items() if v == "mismatch"]
    unverified = [name for name, v in checks.items() if v == "unverified"]
    friendly = claim.claim_type == "friendly_claim"
    official = report.source == ReportSource.OFFICIAL
    time_note = TIME_NOTE[time_check]

    if mismatched:
        # Yalnızca VLM'in ya da tespit sayısının dayanağı olan çelişki "olası"; tip ve hareket
        # çelişkisi kesin. Çelişki seviyeyi değiştirmez: tespit esas alınır.
        notes = [behavior_note] if behavior == "mismatch" else []
        if checks["sayı"] == "mismatch":
            notes.append(f"iddia {claim.vehicle_count} araç diyor, çevrede {seen} araç görülüyor")
        return result(
            "contradicts",
            "likely" if set(mismatched) <= DETECTOR_CHECKS else "certain",
            "none",
            f"{who} iddianın konumunda ama {', '.join(mismatched)} uyuşmuyor"
            + (f" ({'; '.join(notes)})" if notes else "")
            + time_note
            + "; tespit esas alındı",
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
