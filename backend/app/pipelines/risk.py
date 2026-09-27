"""Kod tabanlı temel risk seviyesi (ADR-0002: karar hibrit, temeli kurallar verir).

Seviyeyi zaman boyutlu risk motoru (`app.risk_engine`) verir: iz, ilk noktasından itibaren her
gözlem adımında değerlendirilir ve çekim anındaki yayınlanan seviye temasın temel seviyesidir.
"""

from dataclasses import dataclass

from app.core.rules import LevelRules
from app.formatting import km as fmt_km
from app.risk_engine import RULE_TEXT, EngineConfig, Step, unregistered_level
from app.schemas.api import AttentionReason, MotionFinding
from app.schemas.domain import RiskLevel

LEVELS: tuple[RiskLevel, ...] = ("low", "medium", "high", "critical")

# Motorun kural kodu -> karar LLM'inin doğrulayabildiği dikkat nedeni.
_BASIS: dict[str, AttentionReason] = {
    "C1_perimeter": "yaklasma",
    "C2_approach_inner": "yaklasma",
    "C3_heavy_approach": "yaklasma",
    "C4_eta": "yaklasma",
    "C5_aimed_dash": "yaklasma",
    "H1_approach": "yaklasma",
    "H5_arrived": "yaklasma",
    "H6_creep": "yaklasma",
    "M1_approach": "yaklasma",
    "H3_probe": "dolasma",
    "H4_orbit": "dolasma",
    "H4r_patrol_rev": "dolasma",
    "M2_orbit": "dolasma",
    "H2_near": "uzun_duraklama",
    "M3_inner_presence": "uzun_duraklama",
}

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
    basis: AttentionReason | None = None
    """Seviyeyi belirleyen satırın dikkat nedeni; yaklaşma yoksa ve kayıtlıysa yok."""


def rule_of(code: str) -> str:
    """Yayın kodundan kural kodu: "HOLD<H2_near" ve "X_H2_near" -> "H2_near"."""
    return code.split("<", 1)[-1].removeprefix("X_")


def engine_decision(step: Step, distance_to_base_m: float) -> LevelDecision:
    """Motorun çekim anındaki adımından temel seviye ve gerekçe."""
    level = LEVELS[step.level]
    km = fmt_km(distance_to_base_m)
    rule = rule_of(step.code)
    reasons = [f"{RULE_TEXT.get(rule, rule)}, {km}"]
    if step.held:
        now = RULE_TEXT.get(step.code_raw, step.code_raw)
        reasons.append(f"koşul kalktı ({now}); seviye iniş beklemesinde")
    if step.crit_static:
        reasons.append(f"üsse yakın park halinde, {step.features.stop_now:.0f} dk duruyor")
    elif step.dwell_min >= 30:
        reasons.append(f"son 2 saatte üs yakınında {step.dwell_min:.0f} dk bekledi")
    if step.tags:
        reasons.append("kalıp: " + ", ".join(step.tags))
    return LevelDecision(level, reasons, _BASIS.get(rule))


def unregistered_decision(distance_to_base_m: float, cfg: EngineConfig) -> LevelDecision:
    """İzi olmayan tespit: kendi başına risk değildir, yalnız üsse yakınsa (ADR-0003)."""
    km = fmt_km(distance_to_base_m)
    level = LEVELS[unregistered_level(distance_to_base_m, cfg)]
    if level == "low":
        # Görev tanımı: park halindeki araçların hareket kaydı olmayabilir (ADR-0003).
        reason = f"kayıt dışı temas: hareket kaydı yok, park halinde olabilir, {km}"
    else:
        reason = f"kayıt dışı temas üssün yakınında, hareket geçmişi bilinmiyor, {km}"
    return LevelDecision(level, [reason], "kayit_disi")


def highest(levels: list[RiskLevel]) -> RiskLevel:
    """Görüntü seviyesi: temasların en yükseği; temas yoksa düşük."""
    return max(levels, key=LEVELS.index, default="low")


def recommended_action(level: RiskLevel, *, zone: str, contact: str | None) -> str:
    return ACTIONS[level].format(zone=zone, contact=contact or "en riskli")


def loiter_minutes(motion: MotionFinding | None, rules: LevelRules) -> int:
    """Üsse `loiter_m`'den yakın en uzun duraklamanın süresi."""
    if motion is None:
        return 0
    return max(
        (s.minutes for s in motion.stops if s.distance_to_base_m < rules.loiter_m), default=0
    )


def circling_path_m(motion: MotionFinding | None, rules: LevelRules) -> float:
    """Üssün çevresinde dar bir mesafe bandında kalarak gidilen yol; dolaşmıyorsa 0.

    Görev tanımı s3: araçlar üs çevresinde dolaşır. Üsse mesafesi kayıt boyunca
    `circle_band_m` içinde kalan, `loiter_m`'den yakın ve en az `circle_min_extent_m`
    genişliğinde bir yay çizen araç dolaşıyordur; yerinde gidip gelen yerel trafik değil.
    """
    if (
        motion is None
        or motion.base_distance_max_m >= rules.loiter_m
        or motion.base_distance_max_m - motion.base_distance_min_m > rules.circle_band_m
        or motion.extent_m < rules.circle_min_extent_m
    ):
        return 0.0
    return motion.total_distance_m
