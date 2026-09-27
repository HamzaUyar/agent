"""Öncelik skoru (0-100): aynı seviyedeki temasları operatör listesinde sıralar.

skor = seviye bandı (düşük 0, orta 25, yüksek 50, kritik 75) + 24,99 × bant içi puan.
Bant içi puan yaklaşma hızı, davranış (çember, yay devriyesi, sokulup geri çekilme, üs
yakınında bekleme), ağır araç ve seviyeye yeni giriş bileşenlerinin ağırlıklı toplamıdır.
Seviye iniş beklemesinde tutuluyorsa puan `held_factor` ile çarpılır. Skor seviyeyi
hiçbir zaman değiştirmez; referanslar TOML'da sabittir.
"""

from dataclasses import dataclass

from app.risk_engine.config import EngineConfig
from app.risk_engine.features import Features
from app.risk_engine.rules import HEAVY_LABELS, is_orbit, is_probe

BANDS = (0.0, 25.0, 50.0, 75.0)
BAND_WIDTH = 24.99


@dataclass(frozen=True)
class ScoreParts:
    closing: float
    behavior: float
    heavy: float
    new_entry: float


def _clip01(v: float) -> float:
    return min(max(v, 0.0), 1.0)


def score_parts(
    f: Features, label: str | None, dwell_min: float, entry_age_min: float, cfg: EngineConfig
) -> ScoreParts:
    p = cfg.priority
    closing = _clip01(max(f.dd30 / 1800, f.dd60 / 3600) / p.closing_ref_mps)
    behavior = max(
        1.0 if is_orbit(f, cfg) else 0.0,
        0.8 if f.pat else 0.0,
        0.8 if is_probe(f, cfg) else 0.0,
        _clip01(dwell_min / p.dwell_ref_min),
    )
    heavy = 1.0 if label in HEAVY_LABELS else 0.0
    new_entry = _clip01(1 - entry_age_min / p.new_entry_min)
    return ScoreParts(closing=closing, behavior=behavior, heavy=heavy, new_entry=new_entry)


def priority_score(level: int, parts: ScoreParts, held: bool, cfg: EngineConfig) -> float:
    p = cfg.priority
    w = (
        p.w_closing * parts.closing
        + p.w_behavior * parts.behavior
        + p.w_heavy * parts.heavy
        + p.w_new * parts.new_entry
    )
    if held:
        w *= p.held_factor
    return BANDS[level] + BAND_WIDTH * w
