"""Risk ve hareket eşikleri; `risk_rules.toml` dosyasından okunur.

Temel seviyeyi veren risk motorunun parametreleri ayrı dosyadadır (`risk_engine.toml`,
`app.risk_engine.config`); `RiskRules.engine` ikisini tek nesnede taşır.
"""

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from app.risk_engine.config import EngineConfig, default_config

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
    """Karar LLM'inin dikkat nedenlerini doğrularken kullandığı kanıt eşikleri."""

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
    engine: EngineConfig = field(default_factory=default_config)
    """Temel seviyeyi veren risk motorunun parametreleri."""


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


def rules_version(rules: RiskRules) -> str:
    """Eşiklerin ve risk motoru parametrelerinin özeti; biri değişirse değişir.

    Kayıtlı değerlendirmeler bu sürümle etiketlenir; önbellek ve harita yalnızca güncel
    sürümle yapılmış kayıtları kullanır (eski kurallarla yazılmış brief tekrar oynatılmaz).
    """
    blob = json.dumps(asdict(rules), sort_keys=True, ensure_ascii=False)
    return "r-" + hashlib.sha256(blob.encode()).hexdigest()[:12]
