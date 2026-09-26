"""KOL B: bir track'in çekim anına kadarki hareketinin özeti."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import time

from app.core.rules import MotionRules, TrendRules
from app.data_package import TRACK_STEP_MINUTES, to_minutes
from app.pipelines.geo import bearing_deg, distance_m, nearest_zone
from app.schemas.domain import GeoPoint, TrackPoint, Trend, Zone


@dataclass(frozen=True)
class Position:
    track_id: str
    location: GeoPoint
    estimated: bool
    """Çekim anında kayıt yok; son iki noktadan ileri kestirildi."""


def positions_at(points: list[TrackPoint], now: time) -> list[Position]:
    """Her track'in `now` anındaki konumu.

    `points` yalnızca `now` ve öncesini içermelidir (ADR-0001). Çekim anı 5 dakikalık
    adıma denk gelmiyorsa konum, son iki noktanın hızıyla ileri kestirilir; sonraki
    noktayı kullanan bir interpolasyon çekim anından sonrasını görmek olurdu.
    Son kaydı bir adımdan eski olan track o anda sahada sayılmaz.
    """
    by_track: dict[str, list[TrackPoint]] = defaultdict(list)
    for p in sorted(points, key=lambda p: p.time):
        if p.time <= now:
            by_track[p.track_id].append(p)

    now_m = to_minutes(now)
    positions: list[Position] = []
    for track_id, history in by_track.items():
        last = history[-1]
        gap = now_m - to_minutes(last.time)
        if gap == 0:
            positions.append(Position(track_id, last.location, estimated=False))
        elif gap < TRACK_STEP_MINUTES:
            positions.append(Position(track_id, _extrapolate(history, gap), estimated=True))
    return positions


def _extrapolate(history: list[TrackPoint], minutes_ahead: int) -> GeoPoint:
    last = history[-1]
    # Aynı saatte tekrarlı noktalar olabilir; hız için daha önceki bir zaman gerekir.
    prev = next((p for p in reversed(history) if p.time < last.time), None)
    if prev is None:
        return last.location
    span = to_minutes(last.time) - to_minutes(prev.time)
    f = minutes_ahead / span
    return GeoPoint(
        last.location.lat + f * (last.location.lat - prev.location.lat),
        last.location.lon + f * (last.location.lon - prev.location.lon),
    )


@dataclass(frozen=True)
class Stop:
    start: time
    end: time
    location: GeoPoint
    zone: str

    @property
    def minutes(self) -> int:
        return to_minutes(self.end) - to_minutes(self.start)


@dataclass(frozen=True)
class Motion:
    distance_to_base_m: float
    distance_to_base_window_ago_m: float | None
    trend: Trend
    route: list[TrackPoint]
    """Çekim anına kadarki kayıtlı noktalar (saatleriyle); ileri kestirim içermez."""
    total_distance_m: float
    avg_speed_mps: float
    recent_speed_mps: float
    heading_deg: float | None
    """Son pencerede gidilen yön (kuzey = 0°, saat yönünde); yerinde duruyorsa yok."""
    stops: list[Stop]
    zones_passed: list[str]


def _path_length(points: list[TrackPoint]) -> float:
    return sum(distance_m(a.location, b.location) for a, b in zip(points, points[1:], strict=False))


def _elapsed_s(points: list[TrackPoint]) -> int:
    return (to_minutes(points[-1].time) - to_minutes(points[0].time)) * 60


def _since(history: list[TrackPoint], now: time, minutes: int) -> list[TrackPoint]:
    start = to_minutes(now) - minutes
    return [p for p in history if to_minutes(p.time) >= start]


def _stops(history: list[TrackPoint], zones: list[Zone], rules: MotionRules) -> list[Stop]:
    """İlk noktasından `stop_displacement_m` içinde kalan ardışık nokta dizileri."""
    stops: list[Stop] = []
    i = 0
    while i < len(history):
        anchor = history[i]
        j = i
        while (
            j + 1 < len(history)
            and distance_m(anchor.location, history[j + 1].location) <= rules.stop_displacement_m
        ):
            j += 1
        if to_minutes(history[j].time) - to_minutes(anchor.time) >= rules.stop_min_minutes:
            zone = nearest_zone(anchor.location, zones).name if zones else ""
            stops.append(Stop(anchor.time, history[j].time, anchor.location, zone))
        i = j + 1
    return stops


def _zones_passed(history: list[TrackPoint], zones: list[Zone]) -> list[str]:
    passed: list[str] = []
    for p in history:
        name = nearest_zone(p.location, zones).name
        if not passed or passed[-1] != name:
            passed.append(name)
    return passed


def _trend(
    history: list[TrackPoint], base: GeoPoint, now: time, rules: TrendRules
) -> tuple[Trend, float | None]:
    current = history[-1]
    window = _since(history, now, rules.window_minutes)
    earlier = window[0] if window else None
    if earlier is None or earlier is current:
        return "unknown", None
    then_dist = distance_m(earlier.location, base)
    change = distance_m(current.location, base) - then_dist
    if change < -rules.threshold_m:
        return "approaching", then_dist
    if change > rules.threshold_m:
        return "receding", then_dist
    if distance_m(earlier.location, current.location) < rules.stationary_displacement_m:
        return "stationary", then_dist
    return "passing", then_dist


def analyze_motion(
    history: list[TrackPoint],
    base: GeoPoint,
    now: time,
    zones: list[Zone],
    trend_rules: TrendRules,
    motion_rules: MotionRules,
) -> Motion:
    """`history` çekim anına kadarki (dahil) noktalardır, zamana göre sıralı."""
    if not history:
        raise ValueError("Hareket analizi için track noktası yok")
    current = history[-1]
    trend, then_dist = _trend(history, base, now, trend_rules)

    total = _path_length(history)
    elapsed = _elapsed_s(history)
    recent = _since(history, now, motion_rules.recent_window_minutes)
    recent_elapsed = _elapsed_s(recent) if recent else 0
    recent_speed = _path_length(recent) / recent_elapsed if recent_elapsed else 0.0

    heading: float | None = None
    if recent and distance_m(recent[0].location, current.location) >= (
        trend_rules.stationary_displacement_m
    ):
        heading = bearing_deg(recent[0].location, current.location)

    return Motion(
        distance_to_base_m=distance_m(current.location, base),
        distance_to_base_window_ago_m=then_dist,
        trend=trend,
        route=list(history),
        total_distance_m=total,
        avg_speed_mps=total / elapsed if elapsed else 0.0,
        recent_speed_mps=recent_speed,
        heading_deg=heading,
        stops=_stops(history, zones, motion_rules),
        zones_passed=_zones_passed(history, zones) if zones else [],
    )
