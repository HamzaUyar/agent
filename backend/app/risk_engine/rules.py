"""Seviye tablosu: her gözlem adımında uygulanır, ilk uyan satır geçerli.

Seviyeler 0..3 = low / medium / high / critical. Aynı tablonun `exit=True` hali çıkış (kalış)
tablosudur: mesafe eşikleri `distance_add_m` kadar gevşer, kapanış büyüklükleri `closing_sub_m`
kadar düşer; bir seviyeden inmek için koşulun çıkış tablosunda da kalkmış olması gerekir.
"""

from app.risk_engine.config import EngineConfig
from app.risk_engine.features import Features

LEVEL_NAMES = ("low", "medium", "high", "critical")
HEAVY_LABELS = frozenset({"truck", "bus"})

RULE_TEXT: dict[str, str] = {
    "C1_perimeter": "üssün 1 km içinde hareket ediyor",
    "C2_approach_inner": "üsse yaklaşıyor ve 1,5 km içinde",
    "C3_heavy_approach": "ağır araç üsse yaklaşıyor ve 2 km içinde",
    "C4_eta": "tahmini varış süresi 10 dk altında",
    "C5_aimed_dash": "son 5 dk'da üsse yönelik hızlı atılım",
    "H1_approach": "üsse yaklaşıyor ve 3 km içinde",
    "H2_near": "üssün 1,4 km içinde",
    "H3_probe": "son 2 saatte üsse sokulup geri çekilmiş",
    "H4_orbit": "üs etrafında çember çiziyor",
    "H4r_patrol_rev": "üs etrafında yön değiştirerek yay devriyesi",
    "H5_arrived": "son 2 saatte 1 km'den fazla yaklaşıp durmuş",
    "H6_creep": "iç halkaya sürünerek sızmış",
    "M1_approach": "üsse yaklaşıyor",
    "M2_orbit": "üs çevresinde dolaşıyor",
    "M3_inner_presence": "son 2 saatte üssün 2 km içinde bulunmuş",
    "L0_none": "belirgin risk davranışı yok",
}


def is_heavy(label: str | None, confidence: float | None, min_confidence: float) -> bool:
    conf = 1.0 if confidence is None else confidence
    return label in HEAVY_LABELS and conf >= min_confidence


def is_orbit(f: Features, cfg: EngineConfig) -> bool:
    o = cfg.orbit
    return (
        f.orb_path >= o.min_path_m
        and f.orb_sweep >= o.min_sweep_deg
        and f.orb_rf <= o.max_radial_frac
        and f.orb_cv <= o.max_radius_cv
    )


def is_probe(f: Features, cfg: EngineConfig) -> bool:
    h = cfg.high
    return f.dmin120 <= h.probe_dmin_m and f.d - f.dmin120 >= h.probe_min_retreat_m


def evaluate(
    f: Features,
    label: str | None,
    confidence: float | None,
    cfg: EngineConfig,
    *,
    exit: bool = False,
) -> tuple[int, str]:
    """(seviye, kural kodu). `exit=True` çıkış tablosu."""
    c, h, m, x = cfg.critical, cfg.high, cfg.medium, cfg.exit
    a = x.distance_add_m if exit else 0.0
    cs = x.closing_sub_m if exit else 0.0
    tr = cfg.trend
    a30, a60, g15 = (x.a30_m, x.a60_m, x.g15_m) if exit else (tr.a30_m, tr.a60_m, tr.g15_m)
    eta_max = x.eta_minutes if exit else c.eta_minutes
    d = f.d

    approaching = (f.dd30 >= a30 or f.dd60 >= a60) and f.dd15 >= g15
    heavy = is_heavy(label, confidence, c.heavy_min_confidence)
    orbit = is_orbit(f, cfg)
    parked = f.stop_now >= min(30.0, f.age)
    inside_core = d <= a  # yalnız çıkış tablosunda anlamlı (park ya da uzaklaşma istisnası)
    perimeter = (
        d <= c.perimeter_m + a
        and (not (parked and c.perimeter_moving_only) or inside_core)
        and (f.dd15 >= c.perimeter_recede_guard_m or inside_core)
    )

    rows: list[tuple[int, str, bool]] = [
        (3, "C1_perimeter", perimeter),
        (3, "C2_approach_inner", approaching and d <= c.approach_m + a),
        (3, "C3_heavy_approach", approaching and heavy and d <= c.heavy_approach_m + a),
        (3, "C4_eta", approaching and f.eta <= eta_max),
        (
            3,
            "C5_aimed_dash",
            c.dash_enabled
            and f.last_move_age <= c.dash_max_age_min
            and f.last_step_close >= c.dash_min_close_m - cs
            and f.cpa_last <= c.dash_max_cpa_m + a
            and d <= c.dash_max_distance_m + a,
        ),
        (2, "H1_approach", approaching and d <= h.approach_m + a),
        (2, "H2_near", d <= h.near_m + a),
        (
            2,
            "H3_probe",
            f.dmin120 <= h.probe_dmin_m + a and d - f.dmin120 >= h.probe_min_retreat_m - cs,
        ),
        (2, "H4_orbit", orbit and f.orb_r <= h.orbit_radius_m + a),
        (
            2,
            "H4r_patrol_rev",
            h.patrol_reversal_enabled
            and f.pat
            and f.pat_rev
            and f.pat_r <= h.patrol_reversal_radius_m + a,
        ),
        (2, "H5_arrived", f.c120 >= h.arrived_close_m - cs and d <= h.arrived_max_distance_m + a),
        (2, "H6_creep", d <= h.creep_max_distance_m + a and f.drop120 >= h.creep_min_drop_m - cs),
        (1, "M1_approach", approaching),
        (
            1,
            "M2_orbit",
            (orbit and f.orb_r <= m.orbit_radius_m + a)
            or (f.pat and f.pat_r <= m.orbit_radius_m + a),
        ),
        (1, "M3_inner_presence", f.dmin120 <= m.inner_presence_dmin_m + a),
    ]
    for level, code, hit in rows:
        if hit:
            return level, code
    return 0, "L0_none"


def tags(f: Features, cfg: EngineConfig) -> list[str]:
    """Seviyeyi değiştirmeyen kalıp etiketleri (gerekçe ve olay kaydı için)."""
    out: list[str] = []
    if f.loop_net30 >= 180 and f.d <= 1500:
        out.append("LOOP")
    if f.we_pause >= 30 and f.we_close >= 300:
        out.append("WAIT_ENTRY")
    if is_probe(f, cfg):
        out.append("PROBE")
    if f.pat:
        out.append("PATROL")
    return out


def unregistered_level(distance_m: float, cfg: EngineConfig) -> int:
    """İzi olmayan tespit: yalnız üsse yakınsa (ADR-0003)."""
    u = cfg.unregistered
    return 2 if distance_m <= u.high_m else (1 if distance_m <= u.medium_m else 0)
