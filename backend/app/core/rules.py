"""Risk ve hareket eşikleri; `risk_rules.toml` dosyasından okunur."""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_RULES_PATH = Path(__file__).with_name("risk_rules.toml")


@dataclass(frozen=True)
class DetectionRules:
    min_confidence: float
    strong_confidence: float


@dataclass(frozen=True)
class MatchingRules:
    threshold_m: float
    score_tiebreak: float


@dataclass(frozen=True)
class TrendRules:
    window_minutes: int
    threshold_m: float
    stationary_displacement_m: float


@dataclass(frozen=True)
class MotionRules:
    history_minutes: int
    recent_window_minutes: int
    stop_displacement_m: float
    stop_min_minutes: int


@dataclass(frozen=True)
class BriefRules:
    timeout_s: float
    max_tokens: int


@dataclass(frozen=True)
class LevelRules:
    critical_m: float
    critical_heavy_m: float
    high_approach_m: float
    unregistered_alert_m: float
    loiter_minutes: int
    loiter_m: float
    circle_band_m: float
    circle_min_path_m: float
    circle_min_extent_m: float


@dataclass(frozen=True)
class RiskRules:
    detection: DetectionRules
    matching: MatchingRules
    trend: TrendRules
    motion: MotionRules
    brief: BriefRules
    levels: LevelRules


def load_rules(path: Path | None = None) -> RiskRules:
    """Eşik dosyasını okur; eksik ya da fazla anahtar hata verir."""
    with (path or DEFAULT_RULES_PATH).open("rb") as f:
        raw = tomllib.load(f)
    return RiskRules(
        detection=DetectionRules(**raw["detection"]),
        matching=MatchingRules(**raw["matching"]),
        trend=TrendRules(**raw["trend"]),
        motion=MotionRules(**raw["motion"]),
        brief=BriefRules(**raw["brief"]),
        levels=LevelRules(**raw["levels"]),
    )


@lru_cache
def default_rules() -> RiskRules:
    return load_rules()
