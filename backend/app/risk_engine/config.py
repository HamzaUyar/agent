"""Risk motoru parametreleri; `app/core/risk_engine.toml` dosyasından okunur."""

import tomllib
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "core" / "risk_engine.toml"


@dataclass(frozen=True)
class Evaluation:
    history_minutes: float
    move_step_m: float


@dataclass(frozen=True)
class Trend:
    a30_m: float
    a60_m: float
    g15_m: float


@dataclass(frozen=True)
class Critical:
    perimeter_m: float
    perimeter_moving_only: bool
    perimeter_recede_guard_m: float
    approach_m: float
    heavy_approach_m: float
    heavy_min_confidence: float
    eta_minutes: float
    dash_enabled: bool
    dash_max_age_min: float
    dash_min_close_m: float
    dash_max_cpa_m: float
    dash_max_distance_m: float


@dataclass(frozen=True)
class High:
    approach_m: float
    near_m: float
    probe_dmin_m: float
    probe_min_retreat_m: float
    orbit_radius_m: float
    patrol_reversal_enabled: bool
    patrol_reversal_radius_m: float
    arrived_close_m: float
    arrived_max_distance_m: float
    creep_max_distance_m: float
    creep_min_drop_m: float


@dataclass(frozen=True)
class Medium:
    orbit_radius_m: float
    inner_presence_dmin_m: float


@dataclass(frozen=True)
class Orbit:
    min_path_m: float
    min_sweep_deg: float
    max_radial_frac: float
    max_radius_cv: float


@dataclass(frozen=True)
class Patrol:
    window_minutes: float
    min_move_steps: int
    min_sweep_deg: float
    max_radial_frac: float
    max_range_frac: float
    reversal_run_deg: float
    no_reversal_sweep_deg: float


@dataclass(frozen=True)
class Exit:
    distance_add_m: float
    closing_sub_m: float
    a30_m: float
    a60_m: float
    g15_m: float
    eta_minutes: float


@dataclass(frozen=True)
class Events:
    hold_critical_min: float
    hold_high_min: float
    hold_medium_min: float
    confirm_steps_medium: int
    sticky_perimeter_m: float
    sticky_minutes: float
    static_stop_min: float
    static_max_distance_m: float
    deepen_m: float
    rebreach_out_m: float
    rebreach_out_min: float

    def hold(self, level: int) -> float:
        return {3: self.hold_critical_min, 2: self.hold_high_min, 1: self.hold_medium_min}[level]


@dataclass(frozen=True)
class Unregistered:
    min_confidence: float
    high_m: float
    medium_m: float


@dataclass(frozen=True)
class Priority:
    closing_ref_mps: float
    dwell_ref_min: float
    dwell_radius_m: float
    new_entry_min: float
    held_factor: float
    w_closing: float
    w_behavior: float
    w_heavy: float
    w_new: float


@dataclass(frozen=True)
class EngineConfig:
    evaluation: Evaluation
    trend: Trend
    critical: Critical
    high: High
    medium: Medium
    orbit: Orbit
    patrol: Patrol
    exit: Exit
    events: Events
    unregistered: Unregistered
    priority: Priority


_T = TypeVar("_T")


def _section(cls: type[_T], raw: dict[str, Any], name: str) -> _T:
    """Bölümü dataclass'a çevirir; eksik ya da fazla anahtar hata verir."""
    data = raw.get(name)
    if not isinstance(data, dict):
        raise ValueError(f"risk_engine.toml: [{name}] bölümü yok")
    expected = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    extra, missing = set(data) - expected, expected - set(data)
    if extra or missing:
        raise ValueError(
            f"risk_engine.toml [{name}]: fazla {sorted(extra)}, eksik {sorted(missing)}"
        )
    return cls(**data)


def load_config(path: Path | None = None) -> EngineConfig:
    with (path or DEFAULT_PATH).open("rb") as f:
        raw = tomllib.load(f)
    return EngineConfig(
        evaluation=_section(Evaluation, raw, "evaluation"),
        trend=_section(Trend, raw, "trend"),
        critical=_section(Critical, raw, "critical"),
        high=_section(High, raw, "high"),
        medium=_section(Medium, raw, "medium"),
        orbit=_section(Orbit, raw, "orbit"),
        patrol=_section(Patrol, raw, "patrol"),
        exit=_section(Exit, raw, "exit"),
        events=_section(Events, raw, "events"),
        unregistered=_section(Unregistered, raw, "unregistered"),
        priority=_section(Priority, raw, "priority"),
    )


@lru_cache
def default_config() -> EngineConfig:
    return load_config()
