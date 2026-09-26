"""Kaggle eğitim görüntülerinden sentetik bir 2. aşama paketi ve etiketleri üretir.

Gerçek veri gelmeden bütün pipeline'ı (yükleme → rapor ayrıştırma → değerlendirme →
değerlendirme seti) ölçekte sınamak için. Görüntüler ve araç kutuları gerçektir (Kaggle
etiketleri); konumlar, track'ler ve raporlar uydurmadır.

Her görüntüye bir senaryo atanır: bir **odak araç** ve onun davranışı (yaklaşan ağır ya da
hafif araç, üsse yakın park, kayıt dışı, kaçırılmış temas, sakin trafik). Diğer araçlar arka
plandır: yerinde gidip gelen yerel trafik ya da park halinde. Bazı görüntülere odak araçla
ilgili raporlar eklenir; bir kısmı bilerek yanlıştır (konum/saat çelişkisi, yanlış tip,
üçüncü taraf sahte dostluk).

Beklenen etiketler senaryonun **gerçek** değerlerinden (gerçek konum, tasarlanan davranış,
tasarlanan rapor) spec'teki kural tablosuyla hesaplanır. Pipeline ise bunları piksellerden,
track noktalarından ve rapor metinlerinden çıkarmak zorundadır; ölçülen, bu çıkarımın
doğruluğudur. Eşikleri ayarlamak için değil, pipeline'ı sınamak içindir.

Çıktılar (`--out`, varsayılan `synthetic/`):
  package/          organizatör biçiminde veri paketi (görüntüler dahil)
  detections.json   sahte detektör için tespitler (DETECTOR_MOCK_PATH)
  claims.json       raporların ideal ayrıştırması (LLM'siz çalıştırma için)
  labels.toml       değerlendirme seti etiketleri
"""

import argparse
import csv
import json
import math
import random
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Literal

from PIL import Image

from app.core.rules import RiskRules, default_rules
from app.data_package import (
    TRACK_STEP_MINUTES,
    check_consistency,
    dump_claims,
    format_hhmm,
    from_minutes,
    to_minutes,
    write_package,
)
from app.pipelines.detection import MIN_CONFIDENCE, STRONG_CONFIDENCE, dump_mock_detections
from app.pipelines.geo import distance_m, in_footprint, nearest_zone, pixel_to_geo
from app.pipelines.risk import LEVELS, base_level
from app.schemas.claims import ClaimRecord, ClaimVehicleType, ReportClaim
from app.schemas.domain import (
    HEAVY_CLASSES,
    Corners,
    DataPackage,
    Detection,
    FieldReport,
    GeoPoint,
    ImageMeta,
    ReportSource,
    RiskLevel,
    TrackPoint,
    VehicleClass,
)
from scripts.make_mock_data import BASE, ZONES

BACKEND_DIR = Path(__file__).resolve().parents[1]
KAGGLE_DIR = BACKEND_DIR.parents[1] / "train"
DEFAULT_OUT = BACKEND_DIR / "synthetic"

M_PER_DEG_LAT = 111_320.0
CAR_LENGTH_M = 4.5
TRACK_BEFORE_MIN = 120
TRACK_AFTER_MIN = 20  # çekim anından sonraki noktalar: ADR-0001 sınamak için

# Yaklaşan araç: son 35 dk üsse doğru 2,5 m/s; öncesinde uzakta park halinde.
APPROACH_MIN = 35
APPROACH_SPEED_MPS = 2.5
# Yerel trafik: çekim noktası çevresinde teğet doğrultuda ±300 m gidip gelir.
LOCAL_AMPLITUDE_M = 300.0
LOCAL_PERIOD_MIN = 40.0
# İddia, çekim anında noktasına en yakın temasa bağlanır (risk_rules [reports] bind_now_m).
# Başka bir araç iddia noktasına odak araçtan bu pay kadar yakın olmamalı (yuvarlama payı).
BIND_MARGIN_M = 2.0
# Sayı iddiasında sayılan yarıçap (risk_rules [reports] count_radius_m).
COUNT_RADIUS_M = 30.0
# Eşleşme eşiği (15 m) + pay.
STEAL_RADIUS_M = 20.0

Behavior = Literal["approach", "local", "parked"]
Archetype = Literal[
    "heavy_approach", "light_approach", "loiter", "unregistered", "quiet", "missed_approach"
]
ReportKind = Literal[
    "consistent",
    "threat",
    "friendly_official",
    "friendly_third_party",
    "friendly_time_mismatch",
    "type_contradiction",
    "behavior_contradiction",
    "count_contradiction",
    "after_capture",
    "irrelevant",
    "zone",
]

# 10 görüntülük desen; paket bunu tekrarlar.
PATTERN: list[tuple[Archetype, ReportKind | None]] = [
    ("heavy_approach", "consistent"),
    ("light_approach", "threat"),
    ("loiter", "behavior_contradiction"),
    ("unregistered", "count_contradiction"),
    ("quiet", "irrelevant"),
    ("missed_approach", None),
    ("heavy_approach", "friendly_official"),
    ("light_approach", "friendly_time_mismatch"),
    ("heavy_approach", "type_contradiction"),
    ("light_approach", "friendly_third_party"),
]
# Her üç desende bir, bazı raporlar farklı türle değiştirilir.
ALTERNATES: dict[ReportKind, ReportKind] = {"consistent": "after_capture", "irrelevant": "zone"}

TYPE_TR = {
    VehicleClass.CAR: "binek arac",
    VehicleClass.VAN: "minibus",
    VehicleClass.TRUCK: "kamyon",
    VehicleClass.BUS: "otobus",
}


class GenerationError(RuntimeError):
    """Senaryo tutarlı kurulamadı (ör. bir track başka bir karenin içine düştü)."""


# --- geometri ----------------------------------------------------------------------


def offset(p: GeoPoint, north_m: float, east_m: float) -> GeoPoint:
    return GeoPoint(
        p.lat + north_m / M_PER_DEG_LAT,
        p.lon + east_m / (M_PER_DEG_LAT * math.cos(math.radians(p.lat))),
    )


def to_enu(origin: GeoPoint, p: GeoPoint) -> tuple[float, float]:
    """`origin`'e göre (kuzey, doğu) metre."""
    return (
        (p.lat - origin.lat) * M_PER_DEG_LAT,
        (p.lon - origin.lon) * M_PER_DEG_LAT * math.cos(math.radians(origin.lat)),
    )


def unit(n: float, e: float) -> tuple[float, float]:
    norm = math.hypot(n, e) or 1.0
    return n / norm, e / norm


# --- kaynak görüntüler ---------------------------------------------------------------


@dataclass(frozen=True)
class Box:
    label: VehicleClass
    x: float
    y: float
    w: float
    h: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


@dataclass(frozen=True)
class SourceImage:
    image_id: str
    path: Path
    boxes: tuple[Box, ...]

    @property
    def has_heavy(self) -> bool:
        return any(b.label in HEAVY_CLASSES for b in self.boxes)


def read_annotations(kaggle_dir: Path) -> list[SourceImage]:
    """Kaggle `annotations.csv` + `images/`; dosyası olmayan görüntüler atlanır."""
    boxes: dict[str, list[Box]] = defaultdict(list)
    with (kaggle_dir / "annotations.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            boxes[row["image_id"]].append(
                Box(
                    VehicleClass(row["label"]),
                    float(row["x"]),
                    float(row["y"]),
                    float(row["w"]),
                    float(row["h"]),
                )
            )
    images_dir = kaggle_dir / "images"
    sources = []
    for image_id, items in sorted(boxes.items()):
        path = next(images_dir.glob(f"{image_id}.*"), None)
        if path is not None:
            sources.append(SourceImage(image_id, path, tuple(items)))
    return sources


def ground_sample_m(boxes: tuple[Box, ...]) -> float:
    """Piksel başına metre: otomobil kutusunun uzun kenarı ~4,5 m kabulüyle."""
    cars = sorted(max(b.w, b.h) for b in boxes if b.label == VehicleClass.CAR)
    sides = cars or sorted(max(b.w, b.h) for b in boxes)
    return min(max(CAR_LENGTH_M / sides[len(sides) // 2], 0.03), 0.4)


# --- senaryo ------------------------------------------------------------------------


@dataclass
class Vehicle:
    box: Box
    position: GeoPoint
    """Çekim anındaki gerçek konum (kutu merkezi)."""
    behavior: Behavior | None
    """None: track'i yok (kayıt dışı)."""
    detected: bool
    confidence: float
    outward: tuple[float, float]
    """Üsten dışarı birim vektör (kuzey, doğu)."""
    track_id: str | None = None
    focus: bool = False

    def at(self, rel_min: float) -> GeoPoint:
        """Çekim anına göre `rel_min` dakikadaki konum."""
        if self.behavior == "local":
            s = LOCAL_AMPLITUDE_M * math.sin(2 * math.pi * rel_min / LOCAL_PERIOD_MIN)
            tn, te = -self.outward[1], self.outward[0]
            return offset(self.position, tn * s, te * s)
        if self.behavior == "approach":
            out_m = -max(rel_min, -APPROACH_MIN) * 60 * APPROACH_SPEED_MPS
            out_m = max(out_m, -(distance_m(self.position, BASE.location) - 200))
            return offset(self.position, self.outward[0] * out_m, self.outward[1] * out_m)
        return self.position


@dataclass
class ReportPlan:
    kind: ReportKind
    report: FieldReport
    claim: ReportClaim
    expected: str
    """Beklenen rapor kararı (etiket biçiminde)."""
    effect: Literal["raises_one", "lowers", "none"]


@dataclass
class Scene:
    source: SourceImage
    meta: ImageMeta
    zone: str
    archetype: Archetype
    vehicles: list[Vehicle]
    report: ReportPlan | None = None
    false_positive: Detection | None = None

    @property
    def focus(self) -> Vehicle:
        return next(v for v in self.vehicles if v.focus)


@dataclass
class SyntheticPackage:
    package: DataPackage
    detections: dict[str, list[Detection]]
    claims: list[ClaimRecord]
    scenes: list[Scene]
    sources: dict[str, Path] = field(default_factory=dict)


def _capture_times(n: int, rng: random.Random) -> list[time]:
    """11:30'dan başlayarak yayılmış çekim saatleri; birkaçı 5 dk adımına denk gelmez."""
    step = max(5, (16 * 60 + 50 - (11 * 60 + 30)) // max(n, 1))
    minutes = [11 * 60 + 30 + 5 * round(i * step / 5) for i in range(n)]
    for i in rng.sample(range(n), k=min(3, n)):
        minutes[i] += 2
    return [from_minutes(m) for m in minutes]


def _distance_km(archetype: Archetype, rng: random.Random, rules: RiskRules) -> float:
    """Görüntünün üsse mesafesi; seviye eşiklerine 60 m'den yakın değerler atlanır."""
    lo, hi = (1.0, 2.8) if archetype == "loiter" else (0.9, 4.5)
    edges = [rules.levels.critical_m, rules.levels.critical_heavy_m, rules.levels.loiter_m]
    edges += [rules.levels.high_approach_m, rules.levels.unregistered_alert_m]
    while True:
        d = rng.uniform(lo, hi)
        if all(abs(d * 1000 - e) > 60 for e in edges):
            return d


def _pick_source(
    pool: list[SourceImage], archetype: Archetype, kind: ReportKind | None, rng: random.Random
) -> SourceImage:
    candidates = [s for s in pool if s.has_heavy] if archetype == "heavy_approach" else pool
    if not candidates:
        raise GenerationError(f"'{archetype}' için uygun görüntü kalmadı")
    choice = rng.choice(candidates)
    pool.remove(choice)
    return choice


def _build_scene(
    source: SourceImage,
    image_id: str,
    capture: time,
    zone_index: int,
    archetype: Archetype,
    kind: ReportKind | None,
    rng: random.Random,
    rules: RiskRules,
    weak_rate: float,
    coverage: float,
) -> Scene:
    with Image.open(source.path) as img:
        width, height = img.size
    zone = ZONES[zone_index % len(ZONES)]
    zn, ze = to_enu(BASE.location, zone.center)
    bearing = math.atan2(ze, zn) + math.radians(rng.uniform(-12, 12))
    d_m = _distance_km(archetype, rng, rules) * 1000
    center = offset(BASE.location, d_m * math.cos(bearing), d_m * math.sin(bearing))
    gsd = ground_sample_m(source.boxes)
    half_n, half_e = height * gsd / 2, width * gsd / 2
    meta = ImageMeta(
        image_id,
        width,
        height,
        capture,
        Corners(
            top_left=offset(center, half_n, -half_e),
            top_right=offset(center, half_n, half_e),
            bottom_left=offset(center, -half_n, -half_e),
            bottom_right=offset(center, -half_n, half_e),
        ),
    )
    off_step = to_minutes(capture) % TRACK_STEP_MINUTES != 0

    heavy = [i for i, b in enumerate(source.boxes) if b.label in HEAVY_CLASSES]
    light = [i for i, b in enumerate(source.boxes) if b.label not in HEAVY_CLASSES]
    if archetype == "heavy_approach":
        focus_i = rng.choice(heavy)
    elif archetype == "light_approach" and light:
        focus_i = rng.choice(light)
    else:
        focus_i = rng.randrange(len(source.boxes))

    vehicles = []
    for i, box in enumerate(source.boxes):
        position = pixel_to_geo(meta, *box.center)
        outward = unit(*to_enu(BASE.location, position))
        focus = i == focus_i
        if focus:
            behavior: Behavior | None = {
                "heavy_approach": "approach",
                "light_approach": "approach",
                "missed_approach": "approach",
                "loiter": "parked",
                "unregistered": None,
                "quiet": "parked" if off_step else "local",
            }[archetype]
        elif rng.random() >= coverage:
            behavior = None  # park halinde, track'siz
        else:
            # 5 dk adımına denk gelmeyen karede ileri kestirim ancak doğrusal hareketi bilir.
            behavior = "parked" if off_step or rng.random() < 0.25 else "local"
        detected = not (focus and archetype == "missed_approach")
        weak = behavior is not None and not focus and rng.random() < weak_rate
        confidence = (
            rng.uniform(MIN_CONFIDENCE + 0.05, STRONG_CONFIDENCE - 0.02)
            if weak
            else rng.uniform(0.6, 0.97)
        )
        vehicles.append(
            Vehicle(box, position, behavior, detected, round(confidence, 2), outward, focus=focus)
        )

    # Eşleştirme en yakın çift önce ve güçlü kutular önce yapıldığı için track'siz güçlü bir
    # kutu, 15 m içindeki zayıf ya da kaçırılmış aracın track'ini kapar. Senaryo bunu kurmaz.
    # Kaçırılmış aracın yakınındaki komşulara track verilir; zayıf kutular güçlendirilir.
    missed = [v for v in vehicles if v.behavior is not None and not v.detected]
    for v in vehicles:
        near_missed = any(distance_m(v.position, m.position) <= STEAL_RADIUS_M for m in missed)
        if v.behavior is None and v.detected and near_missed and not v.focus:
            v.behavior = "parked" if off_step else "local"
    untracked = [v for v in vehicles if v.behavior is None and v.detected]
    for v in vehicles:
        crowded = any(distance_m(v.position, u.position) <= STEAL_RADIUS_M for u in untracked)
        if crowded and v.confidence < STRONG_CONFIDENCE:
            v.confidence = round(rng.uniform(0.6, 0.97), 2)
        if crowded and v.behavior is not None and not v.detected:
            raise GenerationError(f"{image_id}: kaçırılmış odak araç track'siz bir araca çok yakın")

    scene = Scene(source, meta, nearest_zone(center, ZONES).name, archetype, vehicles)
    if rng.random() < 0.3:
        scene.false_positive = _false_positive(scene, rng)
    return scene


def _false_positive(scene: Scene, rng: random.Random) -> Detection | None:
    """Hiçbir aracın 25 m yakınında olmayan zayıf, sahte bir kutu (eşleşmeyip düşmeli)."""
    meta = scene.meta
    for _ in range(50):
        x, y = rng.uniform(0, meta.width_px - 30), rng.uniform(0, meta.height_px - 30)
        point = pixel_to_geo(meta, x + 15, y + 15)
        if all(distance_m(point, v.position) > 25 for v in scene.vehicles):
            return Detection(VehicleClass.CAR, 0.3, x, y, 30, 30)
    return None


# --- raporlar ------------------------------------------------------------------------


def _coord_text(p: GeoPoint) -> str:
    return f"{p.lat:.5f}N {p.lon:.5f}E"


def _rounded(p: GeoPoint) -> GeoPoint:
    return GeoPoint(round(p.lat, 5), round(p.lon, 5))


def _claim(**fields: object) -> ReportClaim:
    base: dict[str, object] = {
        "location_type": "coordinate",
        "lat": None,
        "lon": None,
        "zone": None,
        "vehicle_type": None,
        "vehicle_count": 1,
        "color": None,
        "behavior": None,
        "claim_type": "observation",
        "time_reference": None,
        "is_verifiable": True,
    }
    return ReportClaim.model_validate(base | fields)


def _claim_type_of(label: VehicleClass) -> ClaimVehicleType:
    return label.value  # car/van/truck/bus iddia tiplerinde de var


def _plan_report(scene: Scene, kind: ReportKind, rng: random.Random) -> ReportPlan:
    capture = to_minutes(scene.meta.capture_time)
    focus = scene.focus
    label = focus.box.label
    tr_name = TYPE_TR[label]
    # Gerçek verideki gibi rapor koordinatı odak aracın çekim anındaki konumu; rapor saati
    # ise aracın hâlâ uzakta olduğu bir an (yaklaşma çekimden 35 dk önce başlar).
    rel = -5 * rng.randint(9, 20)
    when = from_minutes(capture + rel)
    now = from_minutes(capture)
    here = _rounded(focus.position)

    def plan(
        text: str,
        source: ReportSource,
        claim: ReportClaim,
        expected: str,
        effect: Literal["raises_one", "lowers", "none"] = "none",
        at: time = when,
    ) -> ReportPlan:
        return ReportPlan(kind, FieldReport(at, source, text), claim, expected, effect)

    coord = {"lat": here.lat, "lon": here.lon}
    if kind == "consistent":
        return plan(
            f"{_coord_text(here)} cevresinde 1 {tr_name} bulunuyor, hareketleri olagan.",
            ReportSource.OFFICIAL,
            _claim(**coord, vehicle_type=_claim_type_of(label), behavior="normal_traffic"),
            "consistent",
        )
    if kind == "threat":
        return plan(
            f"{_coord_text(here)} civarinda supheli bir {tr_name} goruldu, dikkatli olunmali.",
            ReportSource.OFFICIAL,
            _claim(**coord, vehicle_type=_claim_type_of(label), claim_type="threat_warning"),
            "consistent",
            "raises_one",
        )
    if kind in ("friendly_official", "friendly_third_party"):
        # Rapor çekim anında: saat de tutar, resmi olan riski düşürür.
        official = kind == "friendly_official"
        text = (
            f"{_coord_text(here)} civarindaki {tr_name} dost birliklere aittir, "
            "kimlik teyit edildi."
            if official
            else f"{_coord_text(here)} yakininda bir {tr_name} var; dost devriye unsurudur."
        )
        return plan(
            text,
            ReportSource.OFFICIAL if official else ReportSource.THIRD_PARTY,
            _claim(**coord, vehicle_type=_claim_type_of(label), claim_type="friendly_claim"),
            "consistent",
            "lowers" if official else "none",
            at=now,
        )
    if kind == "type_contradiction":
        wrong = VehicleClass.CAR if label in HEAVY_CLASSES else VehicleClass.TRUCK
        return plan(
            f"{_coord_text(here)} civarinda 1 {TYPE_TR[wrong]} goruldu.",
            ReportSource.OFFICIAL,
            _claim(**coord, vehicle_type=_claim_type_of(wrong)),
            "contradicts",  # tespit esas alınır: seviye değişmez
        )
    if kind == "behavior_contradiction":
        # Odak araç üsse yakın park halinde; rapor onu üsse doğru ilerliyor gösteriyor.
        return plan(
            f"{_coord_text(here)} konumundan usse dogru ilerleyen bir {tr_name} goruldu.",
            ReportSource.OFFICIAL,
            _claim(**coord, behavior="approaching"),
            "contradicts",  # track esas alınır: seviye değişmez
        )
    if kind == "count_contradiction":
        # Çevrede görülenin iki katından fazlası: sayı uyuşmaz.
        seen = sum(
            1
            for v in scene.vehicles
            if v.detected and distance_m(v.position, here) <= COUNT_RADIUS_M
        )
        return plan(
            f"{_coord_text(here)} yakininda {2 * seen + 2} aracin durdugu bildirildi.",
            ReportSource.OFFICIAL,
            _claim(**coord, vehicle_count=2 * seen + 2),
            "contradicts",
        )
    if kind == "friendly_time_mismatch":
        # Araç rapor saatinde orada değildi: resmi dostluk iddiası riski düşüremez.
        return plan(
            f"{_coord_text(here)} konumundan usse dogru ilerleyen {tr_name} planli ikmal "
            "aracidir, kimlik teyidi yapilmistir.",
            ReportSource.OFFICIAL,
            _claim(**coord, vehicle_type=_claim_type_of(label), claim_type="friendly_claim"),
            "unverifiable",
        )
    if kind == "after_capture":
        later = _rounded(focus.at(10))
        return plan(
            f"{_coord_text(later)} civarinda hizla ilerleyen 1 {tr_name} goruldu.",
            ReportSource.OFFICIAL,
            _claim(
                lat=later.lat, lon=later.lon, vehicle_type=_claim_type_of(label), behavior="moving"
            ),
            "ignored",
            at=from_minutes(capture + 10),
        )
    if kind == "irrelevant":
        spot = _rounded(scene.meta.corners.center)
        return plan(
            f"{_coord_text(spot)} civarinda yol calismasi nedeniyle trafik yavas ilerliyor.",
            ReportSource.THIRD_PARTY,
            _claim(lat=spot.lat, lon=spot.lon, vehicle_count=None, claim_type="irrelevant"),
            "irrelevant",
        )
    # zone
    return plan(
        f"{scene.zone} uzerinde trafik akisi normal seyrediyor.",
        ReportSource.OFFICIAL,
        _claim(
            location_type="zone", zone=scene.zone, vehicle_count=None, behavior="normal_traffic"
        ),
        "unverifiable",
    )


# --- beklenen değerler ------------------------------------------------------------------


def contact_level(v: Vehicle, rules: RiskRules) -> RiskLevel:
    """Aracın, gerçek değerleriyle kural tablosuna göre temel seviyesi."""
    dist = distance_m(v.position, BASE.location)
    trend = {"approach": "approaching", "local": "passing", "parked": "stationary", None: None}[
        v.behavior
    ]
    loiter = TRACK_BEFORE_MIN if v.behavior == "parked" and dist < rules.levels.loiter_m else 0
    return base_level(
        v.box.label if v.detected else None,
        dist,
        trend,  # type: ignore[arg-type]  # tablo değerleri Trend
        registered=v.behavior is not None,
        loiter_minutes_near_base=loiter,
        rules=rules.levels,
    ).level


def expected_level(scene: Scene, rules: RiskRules) -> RiskLevel:
    levels: list[RiskLevel] = []
    for v in scene.vehicles:
        if not v.detected and v.behavior is None:
            continue
        level = contact_level(v, rules)
        if v.focus and scene.report is not None:
            effect = scene.report.effect
            if effect == "raises_one":
                level = LEVELS[min(LEVELS.index(level) + 1, len(LEVELS) - 1)]
            elif effect == "lowers":
                level = "low"
        levels.append(level)
    return max(levels, key=LEVELS.index, default="low")


# --- üretim ----------------------------------------------------------------------------


def generate(
    sources: list[SourceImage],
    *,
    n_images: int = 40,
    seed: int = 7,
    max_vehicles: int = 30,
    weak_rate: float = 0.1,
    coverage: float = 1.0,
    rules: RiskRules | None = None,
) -> SyntheticPackage:
    """Senaryoları kurar ve tutarlılığını doğrular; tutarsızsa `GenerationError`."""
    rules = rules or default_rules()
    rng = random.Random(seed)
    pool = [s for s in sources if 1 <= len(s.boxes) <= max_vehicles]
    if len(pool) < n_images:
        raise GenerationError(f"yeterli kaynak görüntü yok ({len(pool)} < {n_images})")
    times = _capture_times(n_images, rng)

    scenes: list[Scene] = []
    for i in range(n_images):
        archetype, kind = PATTERN[i % len(PATTERN)]
        if kind in ALTERNATES and (i // len(PATTERN)) % 3 == 2:
            kind = ALTERNATES[kind]
        source = _pick_source(pool, archetype, kind, rng)
        scene = _build_scene(
            source, source.image_id, times[i], i, archetype, kind, rng, rules, weak_rate, coverage
        )
        if kind is not None:
            scene.report = _plan_report(scene, kind, rng)
        scenes.append(scene)

    track_no = 0
    for scene in scenes:
        for v in scene.vehicles:
            if v.behavior is not None:
                track_no += 1
                v.track_id = f"T{track_no:04d}"

    points = _track_points(scenes)
    _validate(scenes, points)

    detections = {
        s.meta.image_id: [
            Detection(v.box.label, v.confidence, v.box.x, v.box.y, v.box.w, v.box.h)
            for v in s.vehicles
            if v.detected
        ]
        + ([s.false_positive] if s.false_positive else [])
        for s in scenes
    }
    planned = sorted((s.report for s in scenes if s.report), key=lambda r: r.report.time)
    claims = [ClaimRecord(i + 1, p.report, p.claim) for i, p in enumerate(planned)]
    package = DataPackage(
        base=BASE,
        zones=ZONES,
        images=[s.meta for s in scenes],
        track_points=points,
        reports=[p.report for p in planned],
        image_files={s.meta.image_id for s in scenes},
    )
    return SyntheticPackage(
        package, detections, claims, scenes, {s.meta.image_id: s.source.path for s in scenes}
    )


def _track_points(scenes: list[Scene]) -> list[TrackPoint]:
    points = []
    for scene in scenes:
        capture = to_minutes(scene.meta.capture_time)
        first = -(-(capture - TRACK_BEFORE_MIN) // TRACK_STEP_MINUTES) * TRACK_STEP_MINUTES
        last = (capture + TRACK_AFTER_MIN) // TRACK_STEP_MINUTES * TRACK_STEP_MINUTES
        for v in scene.vehicles:
            if v.track_id is None:
                continue
            for minute in range(first, last + 1, TRACK_STEP_MINUTES):
                points.append(TrackPoint(v.track_id, from_minutes(minute), v.at(minute - capture)))
    return sorted(points, key=lambda p: (p.time, p.track_id))


def _validate(scenes: list[Scene], points: list[TrackPoint]) -> None:
    """Başka bir görüntünün track'i bir karenin içine düşmemeli; raporlar doğru araca bağlanmalı."""
    by_time: dict[time, list[TrackPoint]] = defaultdict(list)
    for p in points:
        by_time[p.time].append(p)
    owner = {v.track_id: s.meta.image_id for s in scenes for v in s.vehicles if v.track_id}
    for scene in scenes:
        capture = to_minutes(scene.meta.capture_time)
        for minute in range(capture - 2 * TRACK_STEP_MINUTES, capture + 1):
            for p in by_time.get(from_minutes(minute), []):
                if owner[p.track_id] != scene.meta.image_id and in_footprint(
                    scene.meta, p.location
                ):
                    raise GenerationError(
                        f"{p.track_id} ({owner[p.track_id]}) {scene.meta.image_id} karesine düşüyor"
                    )
        plan = scene.report
        if plan is None or plan.claim.lat is None or plan.expected == "ignored":
            continue
        claim_at = GeoPoint(plan.claim.lat, plan.claim.lon or 0.0)
        focus_d = distance_m(scene.focus.position, claim_at)
        others = [
            v
            for v in scene.vehicles
            if v is not scene.focus and distance_m(v.position, claim_at) <= focus_d + BIND_MARGIN_M
        ]
        if others and plan.kind != "irrelevant":
            raise GenerationError(
                f"{scene.meta.image_id} raporu ({plan.kind}) başka bir araca bağlanabilir: "
                + ", ".join(str(v.track_id) for v in others[:3])
            )


def generate_with_retries(
    sources: list[SourceImage], *, seed: int, **kwargs: object
) -> SyntheticPackage:
    """Tutarsız senaryoda sonraki tohumla yeniden dener."""
    errors = []
    for attempt in range(20):
        try:
            return generate(sources, seed=seed + attempt, **kwargs)  # type: ignore[arg-type]
        except GenerationError as exc:
            errors.append(str(exc))
    raise GenerationError("20 denemede tutarlı paket kurulamadı: " + "; ".join(errors[-3:]))


# --- çıktılar -----------------------------------------------------------------------------


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def labels_toml(result: SyntheticPackage, rules: RiskRules | None = None) -> str:
    rules = rules or default_rules()
    lines = [
        "# Sentetik paketin değerlendirme seti etiketleri (scripts/make_synthetic_data.py üretti).",
        "# Beklenen değerler senaryonun gerçek konum, davranış ve raporlarından kural tablosuyla",
        "# hesaplandı. Biçim: eval/mock_labels.toml.",
    ]
    for scene in sorted(result.scenes, key=lambda s: s.meta.capture_time):
        f = scene.focus
        dist = distance_m(f.position, BASE.location) / 1000
        note = (
            f"{scene.archetype} · odak {f.track_id or 'track yok'} {f.box.label.value} · "
            f"üsse {dist:.1f} km · {len(scene.vehicles)} araç"
        )
        if scene.report:
            note += f" · rapor: {scene.report.kind}"
        matched = sorted(
            str(v.track_id) for v in scene.vehicles if v.detected and v.track_id is not None
        )
        lines += [
            "",
            "[[images]]",
            f"image_id = {_toml_str(scene.meta.image_id)}",
            f"note = {_toml_str(note)}",
            f"level = {_toml_str(expected_level(scene, rules))}",
            f"matched_tracks = [{', '.join(_toml_str(t) for t in matched)}]",
        ]
        if scene.report:
            r = scene.report
            lines += [
                "",
                "  [[images.reports]]",
                f"  time = {_toml_str(format_hhmm(r.report.time))}",
                f"  source = {_toml_str(r.report.source.value)}",
                f"  verdict = {_toml_str(r.expected)}",
            ]
    return "\n".join(lines) + "\n"


def write_outputs(result: SyntheticPackage, out: Path, *, copy_images: bool = True) -> None:
    package_dir = out / "package"
    write_package(result.package, package_dir)
    if copy_images:
        for image_id, src in result.sources.items():
            shutil.copyfile(src, package_dir / "images" / f"{image_id}{src.suffix.lower()}")
    dump_mock_detections(result.detections, out / "detections.json")
    dump_claims(result.claims, out / "claims.json")
    (out / "labels.toml").write_text(labels_toml(result), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kaggle", type=Path, default=KAGGLE_DIR, help="Kaggle eğitim klasörü")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--images", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-vehicles", type=int, default=30)
    parser.add_argument(
        "--coverage",
        type=float,
        default=1.0,
        help="Arka plan araçlarından track'i olanların oranı (<1: kayıt dışı temas seli, R12)",
    )
    args = parser.parse_args()

    sources = read_annotations(args.kaggle)
    result = generate_with_retries(
        sources,
        seed=args.seed,
        n_images=args.images,
        max_vehicles=args.max_vehicles,
        coverage=args.coverage,
    )
    if args.out.exists():
        shutil.rmtree(args.out)
    write_outputs(result, args.out)

    print(check_consistency(result.package).render())
    kinds: dict[str, int] = defaultdict(int)
    for s in result.scenes:
        kinds[s.archetype] += 1
    vehicles = sum(len(s.vehicles) for s in result.scenes)
    print(f"\nSenaryolar: {dict(kinds)}")
    print(f"Araç: {vehicles} · rapor: {len(result.claims)} · çıktı: {args.out}")


if __name__ == "__main__":
    main()
