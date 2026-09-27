"""Durum makinesi: bir izin her gözlem adımında yayınlanan seviye, olaylar ve bildirimler.

- Yükselme anında: hedef seviye mevcut seviyenin üstündeyse aynı adımda çıkılır. Düşükten
  ortaya çıkmak için `confirm_steps_medium` ardışık gözlem gerekir (izin ilk adımı hariç).
- İniş beklemeli: çıkış tablosu da koşulun kalktığını gösterdiği sürece sayaç işler; bekleme
  süresi dolunca doğrudan destek seviyesine inilir.
- Kalıcı taban (isteğe bağlı): üssün `sticky_perimeter_m` içinde görülen iz belirli süre
  en az yüksek kalır.
İz 2 saatten kısa olduğu için her çağrıda baştan hesaplanır; ayrıca durum saklanmaz.
"""

from dataclasses import dataclass, field

from app.risk_engine.config import EngineConfig
from app.risk_engine.features import Features, Point, features_at
from app.risk_engine.priority import ScoreParts, priority_score, score_parts
from app.risk_engine.rules import LEVEL_NAMES, evaluate, tags

_NEG_INF = -1e9


@dataclass(frozen=True)
class Step:
    t: float
    features: Features
    level_raw: int
    code_raw: str
    level: int
    """Yayınlanan seviye (durum makinesinden sonra)."""
    code: str
    """Yayınlanan seviyenin kodu; tutulan seviyede "HOLD<...", inişte "X_..." önekli."""
    held: bool
    crit_static: bool
    """Kritik ama park etmiş ve üsse yakın: operatör listesinde arkaya sıralanır."""
    score: float
    parts: ScoreParts
    tags: list[str]
    dwell_min: float


@dataclass(frozen=True)
class Notice:
    t: float
    kind: str
    """ENTER, BREACH, BREACH_AT_BIRTH, DEEPEN, RETRIGGER"""
    change: str
    code: str
    d: float


@dataclass(frozen=True)
class TrackRisk:
    track_id: str
    label: str | None
    confidence: float | None
    steps: list[Step]
    notices: list[Notice] = field(default_factory=list)

    @property
    def current(self) -> Step:
        return self.steps[-1]


def _dwell(points: list[Point], radius_m: float, move_m: float) -> list[float]:
    """Her adımda son 120 dk içinde üsse `radius_m` yakınında durulan süre (dk)."""
    near_dt: list[float] = [0.0]
    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        still = ((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** 0.5 < move_m
        close = (b.x**2 + b.y**2) ** 0.5 <= radius_m
        near_dt.append(b.t - a.t if (still and close) else 0.0)
    out: list[float] = []
    for k, p in enumerate(points):
        # Pencereye ilk giren gözlemin kendi aralığı (bir önceki gözlemden) pencere dışında kalır.
        j = next(i for i, q in enumerate(points) if q.t >= p.t - 120)
        out.append(sum(near_dt[j + 1 if j > 0 else 0 : k + 1]))
    return out


def run_track(
    track_id: str,
    points: list[Point],
    label: str | None,
    confidence: float | None,
    cfg: EngineConfig,
) -> TrackRisk:
    """`points` zamana göre sıralı, çekim anına kadar (dahil)."""
    ev = cfg.events
    dwell = _dwell(points, cfg.priority.dwell_radius_m, cfg.evaluation.move_step_m)
    steps: list[Step] = []
    notices: list[Notice] = []

    cur, timer, last_breach, pend = 0, 0.0, _NEG_INF, 0
    entry_t = points[0].t if points else 0.0
    ep_dmin, low_run, out_since, armed = 1e9, 0, None, True
    had_breach, seen_out = False, False
    prev_level = 0
    for k, p in enumerate(points):
        f = features_at(points, k, cfg)
        lr, cr = evaluate(f, label, confidence, cfg)
        lx, cx = evaluate(f, label, confidence, cfg, exit=True)
        lx = max(lx, lr)
        dt = p.t - points[k - 1].t if k > 0 else 0.0
        if f.d <= ev.sticky_perimeter_m:
            last_breach = p.t
        floor = 2 if p.t - last_breach <= ev.sticky_minutes else 0
        target = max(lr, floor)
        prev = cur
        if target == 1 and cur == 0 and ev.confirm_steps_medium > 1:
            pend += 1
            if pend < ev.confirm_steps_medium and k > 0:
                target = 0
        elif target != 1:
            pend = 0

        if target > cur:
            cur, timer = target, 0.0
            code = cr if lr >= floor else "S_sticky_breach"
        elif target == cur:
            timer = 0.0
            code = cr if lr == cur else (steps[-1].code if steps else cr)
        else:
            support = max(lx, floor)
            timer = 0.0 if support >= cur else timer + dt
            if timer >= ev.hold(cur):
                cur, timer = max(target, support), 0.0
                code = cr if lr >= cur else ("S_sticky_breach" if floor >= cur else f"X_{cx}")
            else:
                code = f"HOLD<{cr}"
        if cur != prev_level or k == 0:
            entry_t = p.t
        prev_level = cur

        held = cur > lr
        parts = score_parts(f, label, dwell[k], p.t - entry_t, cfg)
        steps.append(
            Step(
                t=p.t,
                features=f,
                level_raw=lr,
                code_raw=cr,
                level=cur,
                code=code,
                held=held,
                crit_static=cur == 3
                and f.stop_now >= ev.static_stop_min
                and f.d <= ev.static_max_distance_m,
                score=priority_score(cur, parts, held, cfg),
                parts=parts,
                tags=tags(f, cfg),
                dwell_min=dwell[k],
            )
        )

        # Bildirimler (seviye değişmese de)
        if k > 0 and cur > prev and cur >= 2 and (prev < 2 or cur == 3):
            change = f"{LEVEL_NAMES[prev]}->{LEVEL_NAMES[cur]}"
            notices.append(Notice(p.t, "ENTER", change, cr, f.d))
        if f.d > ev.rebreach_out_m:
            out_since = p.t if out_since is None else out_since
            if not armed and p.t - out_since >= ev.rebreach_out_min:
                armed = True
        else:
            out_since = None
        rebreach = False
        if f.d > ev.rebreach_out_m and had_breach:
            seen_out = True
        if f.d <= cfg.critical.perimeter_m:
            if armed:
                notices.append(Notice(p.t, "BREACH" if k > 0 else "BREACH_AT_BIRTH", "", cr, f.d))
                armed = False
            elif seen_out:
                rebreach = True
            had_breach, seen_out = True, False
        if cur == 3:
            if prev == 3 and f.d <= ep_dmin - ev.deepen_m:
                notices.append(Notice(p.t, "DEEPEN", "", cr, f.d))
            if prev == 3 and ((lr == 3 and low_run >= 2) or rebreach):
                notices.append(Notice(p.t, "RETRIGGER", "", cr, f.d))
            ep_dmin = min(ep_dmin, f.d) if prev == 3 else f.d
            low_run = low_run + 1 if lr < 3 else 0
        else:
            ep_dmin, low_run = 1e9, 0
    return TrackRisk(track_id, label, confidence, steps, notices)
