"""Rapor doğrulama için kanıt dosyası: her rapor için kodla hesaplanmış sayılar.

Üç yaklaşım (kurallar, tek LLM, çok ajanlı ekip) aynı kanıtı kullanır; LLM sayı hesaplamaz.
Koordinatlı rapor, noktasını içeren görüntünün çekim anındaki temaslara bağlanır (rapor
koordinatları çekim anındaki konumu gösterir); aracın rapor saatindeki durumu ayrıca verilir.
Bölge raporu, raporun saatinde o bölgedeki bütün track'lerle karşılaştırılır.
"""

import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageStat

from app.data_package import format_hhmm, from_minutes, read_package, to_minutes
from app.pipelines.geo import distance_m, in_footprint, nearest_zone
from app.schemas.domain import DataPackage, GeoPoint, ImageMeta, TrackPoint

COORD = re.compile(r"(\d+\.(\d+))N (\d+\.\d+)E")
HEAVY = {"truck", "bus"}
MATCH_M = 5.0
"""Tespit kutusu merkezi ile track noktası arasında eşleşme sınırı (çekim anında)."""
POINT_M = 80.0
"""Rapor noktasının çevresinde temas aranan yarıçap."""
COUNT_M = 75.0
"""Sayı ve tip iddiaları için noktanın çevresinde sayım yarıçapı."""
ZONE_WINDOW_MIN = 10
APPROACH_M = 300.0
NOT_DETECTED = "tespit edilemedi"
"""Kanıt dosyasında tespit modelinin görmediği aracın tipi (kaçırılmış temas)."""
NEARBY_M = 8.0
"""Kaçırılmış temasın bu kadar yakınındaki eşleşmemiş tespit "olası aynı araç" diye gösterilir.
Eğik görüntüde doğrusal dönüşüm track noktasını aracın birkaç metre yanına düşürüyor; gerçek
veride T0073'ün kamyonu 5,1 m ötede kaldı ve 5 m eşleşme eşiğini kıl payı geçti. Eşleşme
eşiği risk motorunu da etkilediği için gevşetilmedi; yalnızca rapor kanıtında gösteriliyor."""


@dataclass
class Contact:
    track_id: str | None
    label: str | None
    confidence: float | None
    location: GeoPoint
    box: tuple[float, float, float, float] | None = None
    """Tespit kutusu (x, y, w, h; piksel); track'ten gelen temasta yok."""


@dataclass
class Data:
    package: DataPackage
    detections: dict[str, list[dict[str, Any]]]
    images_dir: Path
    tracks: dict[str, list[TrackPoint]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        by: dict[str, list[TrackPoint]] = {}
        for p in self.package.track_points:
            by.setdefault(p.track_id, []).append(p)
        self.tracks = {k: sorted(v, key=lambda p: to_minutes(p.time)) for k, v in by.items()}

    @property
    def base(self) -> GeoPoint:
        return self.package.base.location


def load(package_dir: Path, detections_path: Path) -> Data:
    return Data(
        read_package(package_dir),
        json.loads(detections_path.read_text(encoding="utf-8")),
        package_dir / "images",
    )


def _pixel_to_geo(img: ImageMeta, x: float, y: float) -> GeoPoint:
    c = img.corners
    lon = c.top_left.lon + x / img.width_px * (c.top_right.lon - c.top_left.lon)
    lat = c.top_left.lat + y / img.height_px * (c.bottom_left.lat - c.top_left.lat)
    return GeoPoint(lat, lon)


def geo_to_pixel(img: ImageMeta, p: GeoPoint) -> tuple[float, float]:
    c = img.corners
    x = (p.lon - c.top_left.lon) / (c.top_right.lon - c.top_left.lon) * img.width_px
    y = (p.lat - c.top_left.lat) / (c.bottom_left.lat - c.top_left.lat) * img.height_px
    return x, y


def _at(points: list[TrackPoint], minute: int) -> TrackPoint | None:
    """`minute` anındaki ya da hemen önceki nokta."""
    before = [p for p in points if to_minutes(p.time) <= minute]
    return before[-1] if before else None


def motion(data: Data, track_id: str, minute: int) -> dict[str, Any]:
    """Track'in verilen andaki hareket özeti (yalnızca o ana kadarki noktalar)."""
    pts = [p for p in data.tracks[track_id] if to_minutes(p.time) <= minute]
    if not pts:
        return {"bilinmiyor": True}
    now = pts[-1]
    d_now = distance_m(now.location, data.base)

    def d_ago(minutes: int) -> float | None:
        p = _at(pts, minute - minutes)
        return None if p is None else distance_m(p.location, data.base)

    d30, d60, d15 = d_ago(30), d_ago(60), d_ago(15)
    stopped = 0
    for p in reversed(pts):
        if distance_m(p.location, now.location) <= 60:
            stopped = minute - to_minutes(p.time)
        else:
            break
    p30 = _at(pts, minute - 30)
    moved30 = None if p30 is None else distance_m(p30.location, now.location)
    if d30 is None:
        trend = "bilinmiyor"
    elif d30 - d_now > APPROACH_M or (d15 is not None and d15 - d_now > APPROACH_M):
        trend = "yaklaşıyor"
    elif d_now - d30 > APPROACH_M:
        trend = "uzaklaşıyor"
    elif moved30 is not None and moved30 < 100:
        trend = "duruyor"
    else:
        trend = "üsse yaklaşmadan hareket ediyor"
    dists = [distance_m(p.location, data.base) for p in pts]
    return {
        "trend_son_30dk": trend,
        "usse_mesafe_m": round(d_now),
        "usse_mesafe_15dk_once_m": None if d15 is None else round(d15),
        "usse_mesafe_30dk_once_m": None if d30 is None else round(d30),
        "usse_mesafe_60dk_once_m": None if d60 is None else round(d60),
        "ayni_yerde_dk": stopped,
        "kayit_baslangici": format_hhmm(pts[0].time),
        "kayitta_usse_en_yakin_m": round(min(dists)),
    }


def _box(d: dict[str, Any]) -> tuple[float, float, float, float]:
    return (float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"]))


def contacts_at_capture(data: Data, img: ImageMeta) -> list[Contact]:
    """Çekim anındaki temaslar: bu anda biten track'ler (tespitle eşleşmişse tipiyle) ve
    track'i olmayan tespitler."""
    cap = to_minutes(img.capture_time)
    # Çekim anındaki (ya da en fazla bir adım önceki) konumu karenin içinde olan track'ler.
    # Yarışma verisinde track'ler çekim anında biter; genel durumda sonrası da olabilir.
    track_pts: dict[str, GeoPoint] = {}
    for tid, pts in data.tracks.items():
        p = _at(pts, cap)
        if p is not None and cap - to_minutes(p.time) <= 5 and in_footprint(img, p.location):
            track_pts[tid] = p.location
    dets = [
        (d, _pixel_to_geo(img, d["x"] + d["w"] / 2, d["y"] + d["h"] / 2))
        for d in data.detections.get(img.image_id, [])
    ]
    pairs = sorted(
        (
            (distance_m(loc, tp), i, tid)
            for i, (_, loc) in enumerate(dets)
            for tid, tp in track_pts.items()
        ),
        key=lambda x: x[0],
    )
    used_d: set[int] = set()
    used_t: set[str] = set()
    out: list[Contact] = []
    for dist, i, tid in pairs:
        if dist > MATCH_M or i in used_d or tid in used_t:
            continue
        used_d.add(i)
        used_t.add(tid)
        d = dets[i][0]
        out.append(Contact(tid, str(d["label"]), float(d["confidence"]), track_pts[tid], _box(d)))
    for tid, loc in track_pts.items():
        if tid not in used_t:
            out.append(Contact(tid, None, None, loc))
    for i, (d, loc) in enumerate(dets):
        if i not in used_d:
            out.append(Contact(None, str(d["label"]), float(d["confidence"]), loc, _box(d)))
    return out


def image_quality(data: Data, img: ImageMeta) -> dict[str, Any]:
    path = data.images_dir / f"{img.image_id}.jpg"
    if not path.exists():
        return {"not": "görüntü dosyası yerelde yok; kalite bilinmiyor"}
    im = Image.open(path).convert("L").resize((480, 270))
    bright = ImageStat.Stat(im).mean[0]
    px = list(im.tobytes())
    w = im.width
    lap = [
        abs(4 * px[i] - px[i - 1] - px[i + 1] - px[i - w] - px[i + w])
        for i in range(w + 1, len(px) - w - 1, 7)
    ]
    sharp = sum(lap) / len(lap)
    return {
        "parlaklik": round(bright),
        "keskinlik": round(sharp, 1),
        "not": "karanlık" if bright < 60 else ("bulanık" if sharp < 6 else "net"),
    }


def crop(
    data: Data, img: ImageMeta, point: GeoPoint, radius_m: float = 40.0, size: int = 512
) -> bytes:
    """Rapor noktasının çevresi, nokta işaretli (VLM için)."""
    im = Image.open(data.images_dir / f"{img.image_id}.jpg").convert("RGB")
    c = img.corners
    mpp = distance_m(c.top_left, c.top_right) / img.width_px
    x, y = geo_to_pixel(img, point)
    r = max(24, int(radius_m / mpp))
    draw = ImageDraw.Draw(im)
    draw.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(255, 0, 255), width=3)
    box = (
        max(0, int(x) - r),
        max(0, int(y) - r),
        min(img.width_px, int(x) + r),
        min(img.height_px, int(y) + r),
    )
    out = im.crop(box).resize((size, size))
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


CROP_HALF_PX = 128
"""Görsel bakış kırpıntısının yarı kenarı (piksel). Gerçek veride denendi (27 Eylül, GLM, 2 rapor
× 3 koşu): halkalı 40 m, işaretsiz ±64 px ve artı işaretli ±128 px arasında en tutarlı cevap
işaretsiz ±128 px'te geldi. Eğik görüntüde track noktası aracın birkaç metre yanına düşebildiği
için daha dar kare aracı dışarıda bırakıyordu."""


def track_crop(data: Data, img: ImageMeta, track_id: str, path: Path, size: int = 512) -> bytes:
    """Kaçırılmış temasın çekim anındaki konumu kare ortasında (görsel bakış için), işaretsiz."""
    cap = to_minutes(img.capture_time)
    p = next(p for p in reversed(data.tracks[track_id]) if to_minutes(p.time) <= cap)
    x, y = geo_to_pixel(img, p.location)
    h = CROP_HALF_PX
    with Image.open(path) as im:
        # Kenara yakın noktada kare görüntünün dışına taşar; taşan kısım siyah kalır, nokta ortada.
        out = im.convert("RGB").crop((int(x) - h, int(y) - h, int(x) + h, int(y) + h))
    out = out.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


DUPLICATE_IOU = 0.5
"""Bu kadar örtüşen iki tespit kutusu aynı araçtır."""


def _iou(
    a: tuple[float, float, float, float] | None, b: tuple[float, float, float, float] | None
) -> float:
    if a is None or b is None:
        return 0.0
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    inter = max(0.0, w) * max(0.0, h)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def nearby_detection(c: Contact, contacts: list[Contact]) -> dict[str, Any] | None:
    """Tespiti olmayan bir track'e `NEARBY_M` içindeki en yakın eşleşmemiş tespit. Model aynı
    araca farklı sınıflarla üst üste kutular verebiliyor (T0073: truck 0,43, car ve van 0,12 aynı
    kutuda); örtüşen kutulardan güveni en yüksek olanı kalır, sonra en yakını seçilir. Başka bir
    track'e eşleşmiş tespitle örtüşen kutu o aracın yinelenmesidir, aday değildir: T0073'ün
    5 m yanındaki car/van 0,12 kutuları T0081'in kamyonuydu."""
    if c.track_id is None or c.label is not None:
        return None
    candidates = sorted(
        (
            o
            for o in contacts
            if o.track_id is None
            and o.label is not None
            and distance_m(o.location, c.location) <= NEARBY_M
        ),
        key=lambda o: -(o.confidence or 0.0),
    )
    tracked = [o.box for o in contacts if o.track_id is not None and o.box is not None]
    kept: list[Contact] = []
    for o in candidates:
        taken = [k.box for k in kept] + tracked
        if not any(_iou(o.box, b) > DUPLICATE_IOU for b in taken):
            kept.append(o)
    if not kept:
        return None
    o = min(kept, key=lambda o: distance_m(o.location, c.location))
    d = distance_m(o.location, c.location)
    return {
        "tip": o.label,
        "guven": None if o.confidence is None else round(o.confidence, 2),
        "track_noktasina_uzaklik_m": round(d, 1),
    }


def _image_of(data: Data, p: GeoPoint) -> ImageMeta | None:
    return next((i for i in data.package.images if in_footprint(i, p)), None)


def zone_activity(data: Data, zone: str, minute: int) -> dict[str, Any]:
    """Raporun saatinde (±10 dk) bölgedeki track'ler."""
    labels = track_labels(data)
    rows = []
    for tid, pts in data.tracks.items():
        near = [
            p
            for p in pts
            if abs(to_minutes(p.time) - minute) <= ZONE_WINDOW_MIN
            and nearest_zone(p.location, data.package.zones).name == zone
        ]
        if not near:
            continue
        last = near[-1]
        mv = motion(data, tid, to_minutes(last.time))
        window = [p for p in pts if abs(to_minutes(p.time) - minute) <= ZONE_WINDOW_MIN]
        steps = zip(window, window[1:], strict=False)
        moving = any(distance_m(a.location, b.location) > 100 for a, b in steps)
        rows.append((tid, labels.get(tid), mv, moving))
    app = [r for r in rows if r[2].get("trend_son_30dk") == "yaklaşıyor"]
    heavy_moving = [r for r in rows if r[1] in HEAVY and r[3]]
    return {
        "bolgedeki_arac": len(rows),
        "hareket_eden": sum(1 for r in rows if r[3]),
        "usse_yaklasan": [
            {"iz": r[0], "tip": r[1] or "bilinmiyor", "usse_mesafe_m": r[2]["usse_mesafe_m"]}
            for r in app
        ],
        "hareket_eden_agir_arac": [
            {
                "iz": r[0],
                "tip": r[1],
                "usse_mesafe_m": r[2]["usse_mesafe_m"],
                "trend": r[2]["trend_son_30dk"],
            }
            for r in heavy_moving
        ],
        "usse_3km_icinde": sum(1 for r in rows if r[2]["usse_mesafe_m"] < 3000),
    }


_LABELS: dict[int, dict[str, str]] = {}


def track_labels(data: Data) -> dict[str, str]:
    """Her track'in kendi görüntüsündeki tespit tipi (çekim anında eşleşmişse)."""
    key = id(data)
    if key not in _LABELS:
        labels: dict[str, str] = {}
        for img in data.package.images:
            for c in contacts_at_capture(data, img):
                if c.track_id and c.label:
                    labels[c.track_id] = c.label
        _LABELS[key] = labels
    return _LABELS[key]


def dossier(data: Data, report_id: int) -> dict[str, Any]:
    """Paketteki `report_id` sıradaki raporun kanıt dosyası (konum metinden okunur)."""
    rep = data.package.reports[report_id]
    m = COORD.search(rep.text)
    point = GeoPoint(float(m.group(1)), float(m.group(3))) if m else None
    zone = next((z.name for z in data.package.zones if z.name in rep.text), None)
    return dossier_for(
        data,
        rid=report_id,
        text=rep.text,
        minute=to_minutes(rep.time),
        official=rep.source.value == "official",
        point=point,
        decimals=len(m.group(2)) if m else None,
        zone=zone,
    )


def dossier_for(
    data: Data,
    *,
    rid: int,
    text: str,
    minute: int,
    official: bool,
    point: GeoPoint | None,
    decimals: int | None,
    zone: str | None,
) -> dict[str, Any]:
    """Bir raporun kanıt dosyası (JSON'a çevrilebilir). Konum ayrıştırılmış iddiadan da gelebilir;
    koordinatın ondalık sayısı bilinmiyorsa 5 kabul edilir (bağlama yarıçapı 15 m)."""
    out: dict[str, Any] = {
        "rapor_id": rid,
        "rapor_saati": format_hhmm(from_minutes(minute)),
        "kaynak": "resmi" if official else "üçüncü taraf",
        "metin": text,
    }
    if point is not None:
        decimals = decimals or 5
        img = _image_of(data, point)
        out["konum_turu"] = "koordinat"
        out["koordinat_ondalik"] = decimals
        out["koordinat_hassasiyeti_m"] = round(0.5 * 10 ** (-decimals) * 111000, 1)
        if img is None:
            out["gorsel"] = None
            return out
        cap = to_minutes(img.capture_time)
        out["gorsel"] = {
            "id": img.image_id,
            "cekim_saati": format_hhmm(img.capture_time),
            "rapor_cekimden_once_dk": cap - minute,
            "kalite": image_quality(data, img),
        }
        at_capture = contacts_at_capture(data, img)
        contacts = sorted(
            ((distance_m(c.location, point), c) for c in at_capture),
            key=lambda x: x[0],
        )
        near = [(d, c) for d, c in contacts if d <= POINT_M]
        out["noktadaki_temaslar_cekim_aninda"] = [
            {
                "iz": c.track_id or "track yok (park etmiş olabilir)",
                "noktaya_uzaklik_m": round(d, 1),
                "tespit_tipi": c.label or NOT_DETECTED,
                "tespit_guveni": None if c.confidence is None else round(c.confidence, 2),
                **(
                    {"yakindaki_eslesmemis_tespit": nb}
                    if (nb := nearby_detection(c, at_capture))
                    else {}
                ),
                **(
                    {
                        "hareket_cekim_aninda": motion(data, c.track_id, cap),
                        "rapor_saatinde_noktaya_uzaklik_m": (
                            round(distance_m(p.location, point))
                            if (p := _at(data.tracks[c.track_id], minute)) is not None
                            else None
                        ),
                        "hareket_rapor_saatinde": motion(data, c.track_id, minute),
                    }
                    if c.track_id
                    else {}
                ),
            }
            for d, c in near[:6]
        ]
        # Sayım yarıçapı koordinat hassasiyetine göre: 5 ondalık ~1 m (30 m), 4 ondalık
        # ~10 m (75 m).
        radius = COUNT_M if decimals <= 4 else 30.0
        within = [c for d, c in contacts if d <= radius]
        out["nokta_cevresi_75m"] = {
            "yaricap_m": radius,
            "arac_sayisi": len(within),
            "agir_arac_sayisi": sum(1 for c in within if c.label in HEAVY),
            "tipler": sorted(c.label or NOT_DETECTED for c in within),
        }
        out["en_yakin_arac_m"] = round(contacts[0][0], 1) if contacts else None
        out["gorselde_toplam_arac"] = len(contacts)
    elif zone:
        out["konum_turu"] = "bölge"
        out["bolge"] = zone
        out["bolge_rapor_saatinde"] = zone_activity(data, zone, minute)
    else:
        out["konum_turu"] = "yok"
    return out


def point_of(data: Data, report_id: int) -> tuple[ImageMeta, GeoPoint] | None:
    m = COORD.search(data.package.reports[report_id].text)
    if not m:
        return None
    p = GeoPoint(float(m.group(1)), float(m.group(3)))
    img = _image_of(data, p)
    return None if img is None else (img, p)


def linked_contact(d: dict[str, Any]) -> dict[str, Any] | None:
    """Rapor noktasına koordinat hassasiyeti içinde (5 ondalıkta 15 m, 4 ondalıkta 35 m) en yakın
    temas; koordinatlı ve görüntülü olmayan raporda `None`."""
    if d.get("konum_turu") != "koordinat" or not d.get("gorsel"):
        return None
    near: list[dict[str, Any]] = d["noktadaki_temaslar_cekim_aninda"]
    return next((c for c in near if c["noktaya_uzaklik_m"] <= bind_radius(d)), None)


def bind_radius(d: dict[str, Any]) -> float:
    return 15.0 if d["koordinat_ondalik"] >= 5 else 35.0


def compact(d: dict[str, Any]) -> dict[str, Any]:
    """LLM için kısa kanıt dosyası: bağlanan araç + sayım özeti.

    Bağlanan araç, koordinat hassasiyeti içinde (5 ondalıkta 15 m, 4 ondalıkta 35 m) noktaya
    en yakın temastır. Rapor saatindeki durumu yalnızca tek bir özet cümle olarak kalır
    (karar çekim anına göre verilir; cümle "bayat rapor" açıklaması içindir).
    """
    if d.get("konum_turu") != "koordinat" or not d.get("gorsel"):
        return d
    out = {
        k: d[k]
        for k in (
            "rapor_id",
            "rapor_saati",
            "kaynak",
            "metin",
            "konum_turu",
            "koordinat_ondalik",
            "gorsel",
        )
    }
    bind = bind_radius(d)
    near = d["noktadaki_temaslar_cekim_aninda"]
    linked = linked_contact(d)
    if linked is None:
        out["baglanan_arac"] = None
        out["noktada_arac_yok"] = {
            "baglama_yaricapi_m": bind,
            "en_yakin_araclar": [
                {"noktaya_uzaklik_m": c["noktaya_uzaklik_m"], "tespit_tipi": c["tespit_tipi"]}
                for c in near[:2]
            ],
        }
    else:
        mv = linked.get("hareket_cekim_aninda")
        car: dict[str, Any] = {
            "iz": linked["iz"],
            "noktaya_uzaklik_m": linked["noktaya_uzaklik_m"],
            "tespit_tipi": linked["tespit_tipi"],
            "tespit_guveni": linked["tespit_guveni"],
        }
        if mv:
            car["hareket_cekim_aninda"] = {
                k: mv[k]
                for k in (
                    "trend_son_30dk",
                    "usse_mesafe_m",
                    "usse_mesafe_30dk_once_m",
                    "usse_mesafe_60dk_once_m",
                    "ayni_yerde_dk",
                    "kayit_baslangici",
                    "kayitta_usse_en_yakin_m",
                )
                if k in mv
            }
            rt = linked.get("hareket_rapor_saatinde") or {}
            if rt and not rt.get("bilinmiyor"):
                car["rapor_saatinde_ozet"] = (
                    f"rapor saatinde {rt['trend_son_30dk']}, üsse {rt['usse_mesafe_m']} m, "
                    f"noktaya {linked.get('rapor_saatinde_noktaya_uzaklik_m')} m (çelişki sayılmaz)"
                )
        out["baglanan_arac"] = car
    out["nokta_cevresi_75m"] = d["nokta_cevresi_75m"]
    return out
