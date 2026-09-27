"""Olay kayıtları (seviye koşuları) ve görüntü özeti (çekim anı durumu + son 2 saatin tepesi)."""

from dataclasses import dataclass

from app.risk_engine.rules import LEVEL_NAMES, RULE_TEXT
from app.risk_engine.state import TrackRisk


def hhmm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def _rule(code: str) -> str:
    return code.split("<", 1)[-1].removeprefix("X_")


@dataclass(frozen=True)
class RiskEvent:
    track_id: str
    level: int
    """Olayın eşiği: bu seviye ve üstünde kalınan kesintisiz koşu."""
    t_in: float
    t_out: float | None
    """Olayın bittiği adım; çekim anında sürüyorsa None."""
    dur_min: float
    censored_start: bool
    """Olay izin ilk adımında zaten açıktı (gözlem başlamadan önce başlamış olabilir)."""
    entry_code: str
    d_in: float
    dmin: float
    t_dmin: float
    codes: list[str]
    tags: list[str]
    crit_static_min: float
    exit_to: int | None
    exit_code: str | None

    @property
    def open_at_capture(self) -> bool:
        return self.t_out is None

    def reason(self) -> str:
        state = "çekimde sürüyor" if self.open_at_capture else f"{hhmm(self.t_out or 0)} bitti"
        extra = f"; etiket {'/'.join(self.tags)}" if self.tags else ""
        return (
            f"{self.track_id} {hhmm(self.t_in)} itibarıyla {LEVEL_NAMES[self.level]} "
            f"({RULE_TEXT.get(self.entry_code, self.entry_code)}, {self.d_in:.0f} m); {state}; "
            f"en yakın {self.dmin:.0f} m ({hhmm(self.t_dmin)}){extra}"
        )


def events(track: TrackRisk, min_level: int) -> list[RiskEvent]:
    steps = track.steps
    out: list[RiskEvent] = []
    j = 0
    while j < len(steps):
        if steps[j].level < min_level:
            j += 1
            continue
        k = j
        while k + 1 < len(steps) and steps[k + 1].level >= min_level:
            k += 1
        seg = steps[j : k + 1]
        closest = min(seg, key=lambda s: s.features.d)
        is_open = k == len(steps) - 1
        codes = list(dict.fromkeys(s.code for s in seg if not s.code.startswith(("HOLD", "X_"))))
        tags = sorted({t for s in seg for t in s.tags})
        nxt = None if is_open else steps[k + 1]
        out.append(
            RiskEvent(
                track_id=track.track_id,
                level=min_level,
                t_in=seg[0].t,
                t_out=None if nxt is None else nxt.t,
                dur_min=(seg[-1].t - seg[0].t + 5) if nxt is None else (nxt.t - seg[0].t),
                censored_start=j == 0,
                entry_code=seg[0].code,
                d_in=seg[0].features.d,
                dmin=closest.features.d,
                t_dmin=closest.t,
                codes=codes,
                tags=tags,
                crit_static_min=5.0 * sum(1 for s in seg if s.crit_static),
                exit_to=None if nxt is None else nxt.level,
                exit_code=None if nxt is None else nxt.code,
            )
        )
        j = k + 1
    return out


@dataclass(frozen=True)
class Peak:
    level: int
    track_id: str
    code: str
    start: float
    end: float | None
    """Tepe bölümünün bittiği an; çekimde sürüyorsa None."""


@dataclass(frozen=True)
class ImageRisk:
    image_id: str
    capture: float
    level: int
    """Resmi seviye: çekim anında izlerin ve izsiz tespitlerin en yükseği."""
    level_raw: int
    held: bool
    top_track: str | None
    top_code: str | None
    top_score: float | None
    top_distance_m: float | None
    n_tracks: int
    n_critical: int
    n_critical_active: int
    n_high_plus: int
    unregistered_level: int
    peak_120: Peak | None
    n_critical_events_120: int
    recent_critical: bool
    """Çekimde kritik değil ama son 30 dk içinde kapanmış bir kritik olay var."""

    def brief_line(self) -> str:
        head = LEVEL_NAMES[self.level].upper()
        if self.peak_120 is None:
            return f"{head} | son 2 sa olay yok"
        p = self.peak_120
        end = "açık" if p.end is None else hhmm(p.end)
        return (
            f"{head} | son 2 sa tepe {LEVEL_NAMES[p.level].upper()} {p.track_id} "
            f"{_rule(p.code)} {hhmm(p.start)}-{end} | 2 sa kritik olay {self.n_critical_events_120}"
        )


def _peak(tracks: list[TrackRisk], since: float, capture: float) -> Peak | None:
    best: tuple[int, float, str] | None = None
    for tr in tracks:
        for s in tr.steps:
            if s.t >= since and (best is None or (s.level, s.t) > best[:2]):
                best = (s.level, s.t, tr.track_id)
    if best is None:
        return None
    level, t_last, tid = best
    steps = next(tr.steps for tr in tracks if tr.track_id == tid)
    k = next(i for i, s in enumerate(steps) if s.t == t_last)
    j = k
    while j > 0 and steps[j - 1].level >= level:
        j -= 1
    ended = steps[k].t < capture
    return Peak(level, tid, steps[j].code, steps[j].t, steps[k].t + 5 if ended else None)


def image_summary(
    image_id: str,
    capture: float,
    tracks: list[TrackRisk],
    unregistered_level: int = 0,
    window_min: float = 120,
) -> ImageRisk:
    """`tracks`: bu görüntünün çekim anında biten izler."""
    now = [(tr, tr.current) for tr in tracks if tr.steps and tr.current.t == capture]
    top = max(now, key=lambda p: (p[1].level, p[1].score), default=None)
    level = max([s.level for _, s in now] + [unregistered_level])
    level_raw = max([s.level_raw for _, s in now] + [unregistered_level])
    crit_events = [e for tr in tracks for e in events(tr, 3) if e.t_in >= capture - window_min]
    closed = [e for e in crit_events if e.t_out is not None]
    recent = level != 3 and any(capture - (e.t_out or 0) <= 30 for e in closed)
    return ImageRisk(
        image_id=image_id,
        capture=capture,
        level=level,
        level_raw=level_raw,
        held=level > level_raw,
        top_track=top[0].track_id if top else None,
        top_code=top[1].code if top else None,
        top_score=round(top[1].score, 2) if top else None,
        top_distance_m=round(top[1].features.d) if top else None,
        n_tracks=len(now),
        n_critical=sum(1 for _, s in now if s.level == 3),
        n_critical_active=sum(1 for _, s in now if s.level == 3 and not s.crit_static),
        n_high_plus=sum(1 for _, s in now if s.level >= 2),
        unregistered_level=unregistered_level,
        peak_120=_peak(tracks, capture - window_min, capture),
        n_critical_events_120=len(crit_events),
        recent_critical=recent,
    )
