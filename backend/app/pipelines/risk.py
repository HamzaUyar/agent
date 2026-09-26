"""Kod tabanlı temel risk seviyesi (ADR-0002: karar hibrit, temeli kurallar verir)."""

from dataclasses import dataclass

from app.core.rules import LevelRules
from app.formatting import km as fmt_km
from app.schemas.domain import HEAVY_CLASSES, RiskLevel, Trend, VehicleClass

LEVELS: tuple[RiskLevel, ...] = ("low", "medium", "high", "critical")

ACTIONS: dict[RiskLevel, str] = {
    "low": "İzlemeye devam.",
    "medium": "Takibe al, sonraki karede doğrula.",
    "high": "{zone} bölgesine birim yönlendir.",
    "critical": "Üs alarm durumuna geç, {contact} temasını durdur.",
}


@dataclass(frozen=True)
class LevelDecision:
    level: RiskLevel
    reasons: list[str]


def base_level(
    label: VehicleClass | None,
    distance_to_base_m: float,
    trend: Trend | None,
    *,
    registered: bool,
    loiter_minutes_near_base: int,
    circling_path_m: float = 0.0,
    rules: LevelRules,
) -> LevelDecision:
    """Temel seviye tablosu; ilk uyan satır geçerli.

    `label` None ise tip bilinmiyor (kaçırılmış temas); `trend` None ise hareket kaydı yok.
    `loiter_minutes_near_base`: üsse `rules.loiter_m`'den yakın en uzun duraklamanın süresi.
    `circling_path_m`: üs çevresinde dar bir mesafe bandında kalarak gidilen yol (dolaşma).
    """
    t = rules
    km = fmt_km(distance_to_base_m)
    approaching = trend == "approaching"
    heavy = label in HEAVY_CLASSES

    if approaching and distance_to_base_m < t.critical_m:
        return LevelDecision("critical", [f"üsse yaklaşıyor, {km}"])
    if approaching and heavy and distance_to_base_m < t.critical_heavy_m:
        return LevelDecision("critical", [f"ağır araç ({label}) üsse yaklaşıyor, {km}"])
    if approaching and distance_to_base_m < t.high_approach_m:
        return LevelDecision("high", [f"üsse yaklaşıyor, {km}"])
    if not registered and distance_to_base_m < t.unregistered_alert_m:
        return LevelDecision(
            "medium", [f"kayıt dışı temas üssün hemen yakınında, hareket geçmişi bilinmiyor, {km}"]
        )
    if approaching:
        return LevelDecision("medium", [f"üsse yaklaşıyor, {km}"])
    if loiter_minutes_near_base >= t.loiter_minutes:
        return LevelDecision(
            "medium", [f"üsse yakın {loiter_minutes_near_base} dk duraklama, {km}"]
        )
    if circling_path_m >= t.circle_min_path_m:
        return LevelDecision(
            "medium",
            [f"üs çevresinde sabit mesafede dolaşıyor ({fmt_km(circling_path_m)} yol), {km}"],
        )
    if not registered:
        # Görev tanımı: park halindeki araçların hareket kaydı olmayabilir (ADR-0003).
        return LevelDecision(
            "low", [f"kayıt dışı temas: hareket kaydı yok, park halinde olabilir, {km}"]
        )
    return LevelDecision("low", [f"yaklaşma yok, {km}"])


def highest(levels: list[RiskLevel]) -> RiskLevel:
    """Görüntü seviyesi: temasların en yükseği; temas yoksa düşük."""
    return max(levels, key=LEVELS.index, default="low")


def recommended_action(level: RiskLevel, *, zone: str, contact: str | None) -> str:
    return ACTIONS[level].format(zone=zone, contact=contact or "en riskli")
