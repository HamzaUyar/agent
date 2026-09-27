"""Nedensel hareket özellikleri: bir izin k. gözleminde yalnız 0..k noktaları kullanılır.

Konumlar üsse göre yerel düzlemde metre (x doğu, y kuzey). Noktalar arasında interpolasyon
yapılmaz: 5 dakikada çember üzerinde 70-120° yol alınabildiği için doğrusal ara nokta üsse
yapay bir yakınlık üretir.
"""

import math
import statistics
from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, radians

from app.risk_engine.config import EngineConfig
from app.schemas.domain import GeoPoint

INF = 1e9
_EPS = 1e-6
_KY = 110_574.0


@dataclass(frozen=True)
class Point:
    """İzin bir gözlemi: gün içindeki dakika ve üsse göre konum (m)."""

    t: float
    x: float
    y: float


def to_local(point: GeoPoint, base: GeoPoint) -> tuple[float, float]:
    """Enlem/boylamı üs merkezli düzleme çevirir (küçük alan için eşdikdörtgen yaklaşım)."""
    kx = 111_320.0 * cos(radians(base.lat))
    return (point.lon - base.lon) * kx, (point.lat - base.lat) * _KY


@dataclass(frozen=True)
class Features:
    d: float
    """Üsse mesafe (m)."""
    age: float
    """Pencerenin ilk gözleminden bu yana geçen süre (dk)."""
    dd15: float
    dd30: float
    dd60: float
    """ddW: W dakika önceki mesafe - şimdiki mesafe (+ = yaklaşma)."""
    drop120: float
    """Son 120 dk'daki en büyük mesafe - şimdiki mesafe."""
    dmin120: float
    c120: float
    """Pencerenin ilk mesafesi - şimdiki mesafe."""
    eta: float
    """Tahmini varış süresi (dk); yaklaşma hızı 3 m/dk altındaysa INF."""
    last_move_age: float
    last_step_close: float
    cpa_last: float
    """Son sürüş adımının doğrultusu üssün ne kadar yakınından geçiyor (m)."""
    orb_path: float
    orb_sweep: float
    orb_rf: float
    orb_cv: float
    orb_r: float
    pat: bool
    pat_rev: bool
    pat_r: float
    loop_net30: float
    we_pause: float
    we_close: float
    stop_now: float
    """Son noktanın `move_step_m` içinde kalınan kesintisiz süre (dk)."""
    bearing: float
    """Üsten araca kerteriz, kuzeyden saat yönünde (derece)."""


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _d_before(t: list[float], d: list[float], now: float, window: float) -> float:
    """Zamanı <= now - window olan son gözlemin mesafesi; yoksa pencerenin ilk mesafesi."""
    value = d[0]
    for ti, di in zip(t, d, strict=True):
        if ti <= now - window + _EPS:
            value = di
        else:
            break
    return value


def features_at(points: list[Point], k: int, cfg: EngineConfig) -> Features:
    """`points` zamana göre sıralı; yalnız 0..k kullanılır."""
    now = points[k].t
    horizon = now - cfg.evaluation.history_minutes - _EPS
    win = [p for p in points[: k + 1] if p.t >= horizon]
    t = [p.t for p in win]
    x = [p.x for p in win]
    y = [p.y for p in win]
    d = [hypot(a, b) for a, b in zip(x, y, strict=True)]
    n = len(win)
    dn = d[-1]
    move = cfg.evaluation.move_step_m

    dd = {w: _d_before(t, d, now, w) - dn for w in (15, 30, 60)}
    drop120 = max(di for ti, di in zip(t, d, strict=True) if ti >= now - 120 - _EPS) - dn
    v = max(dd[30] / 30, dd[60] / 60)
    eta = dn / v if v >= 3.0 else INF

    steps = [hypot(x[i + 1] - x[i], y[i + 1] - y[i]) for i in range(n - 1)]
    moving = [s > move for s in steps]
    move_idx = [i for i, m in enumerate(moving) if m]
    if move_idx:
        j = move_idx[-1]
        vx, vy = x[j + 1] - x[j], y[j + 1] - y[j]
        length = hypot(vx, vy)
        toward = -(x[j + 1] * vx + y[j + 1] * vy) > 0
        last_move_age = now - t[j + 1]
        last_step_close = d[j] - d[j + 1]
        cpa_last = abs(x[j + 1] * vy - y[j + 1] * vx) / length if toward else d[j + 1]
    else:
        last_move_age, last_step_close, cpa_last = INF, 0.0, dn

    # Çember: son 120 dk'nın sürüş adımları
    theta = [atan2(b, a) for a, b in zip(x, y, strict=True)]
    dtheta = [_wrap(theta[i + 1] - theta[i]) for i in range(n - 1)]
    ddist = [abs(d[i + 1] - d[i]) for i in range(n - 1)]
    path = sum(s for s, m in zip(steps, moving, strict=True) if m)
    orb_sweep = degrees(sum(abs(a) for a, m in zip(dtheta, moving, strict=True) if m))
    orb_rf = sum(a for a, m in zip(ddist, moving, strict=True) if m) / path if path > 0 else 1.0
    orb_cv = statistics.pstdev(d) / statistics.fmean(d)
    orb_r = statistics.median(d)

    # Yay devriyesi: son `window_minutes` dakikanın sürüş adımları
    pc = cfg.patrol
    pw = [moving[i] and t[i + 1] > now - pc.window_minutes - _EPS for i in range(n - 1)]
    iw = [i for i, m in enumerate(pw) if m]
    pat, pat_rev, pat_r = False, False, INF
    if len(iw) >= pc.min_move_steps:
        ends = sorted(set(iw) | {i + 1 for i in iw})
        de = [d[i] for i in ends]
        r = statistics.median(de)
        rng = (max(de) - min(de)) / r
        rf = sum(ddist[i] for i in iw) / sum(steps[i] for i in iw)
        sweep = degrees(sum(abs(dtheta[i]) for i in iw))
        runs: list[float] = []
        cur, prev = 0.0, -2
        for q in iw:
            if prev >= 0 and q != prev + 1:
                runs.append(cur)
                cur = 0.0
            cur += degrees(dtheta[q])
            prev = q
        runs.append(cur)
        runs = [a for a in runs if abs(a) >= pc.reversal_run_deg]
        pat_rev = any((a > 0) != (b > 0) for a, b in zip(runs[:-1], runs[1:], strict=True))
        pat_r = r
        pat = (
            sweep >= pc.min_sweep_deg
            and rf <= pc.max_radial_frac
            and rng <= pc.max_range_frac
            and (pat_rev or sweep >= pc.no_reversal_sweep_deg)
        )

    # Etiket için: son 30 dk'da üssün 1,5 km yakınında net dönüş
    loop_net30 = abs(
        degrees(
            sum(
                dtheta[i]
                for i in range(n - 1)
                if moving[i] and t[i + 1] > now - 30 - _EPS and max(d[i], d[i + 1]) <= 1500
            )
        )
    )
    we_pause = we_close = 0.0
    if n > 1 and moving[-1]:
        j = len(moving) - 1
        while j > 0 and moving[j - 1]:
            j -= 1
        q = j
        while q > 0 and not moving[q - 1]:
            q -= 1
        we_pause = t[j] - t[q]
        we_close = d[j] - dn

    i = n - 1
    while i > 0 and hypot(x[i - 1] - x[-1], y[i - 1] - y[-1]) <= move:
        i -= 1

    return Features(
        d=dn,
        age=now - t[0],
        dd15=dd[15],
        dd30=dd[30],
        dd60=dd[60],
        drop120=drop120,
        dmin120=min(d),
        c120=d[0] - dn,
        eta=eta,
        last_move_age=last_move_age,
        last_step_close=last_step_close,
        cpa_last=cpa_last,
        orb_path=path,
        orb_sweep=orb_sweep,
        orb_rf=orb_rf,
        orb_cv=orb_cv,
        orb_r=orb_r,
        pat=pat,
        pat_rev=pat_rev,
        pat_r=pat_r,
        loop_net30=loop_net30,
        we_pause=we_pause,
        we_close=we_close,
        stop_now=now - t[i],
        bearing=degrees(atan2(x[-1], y[-1])) % 360,
    )
