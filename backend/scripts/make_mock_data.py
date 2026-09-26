"""Brief'teki uçtan uca örnekten (img_000860, T0122) sahte bir 2. aşama veri paketi üretir.

Organizatör örneğinden gelen değerler: üs, Kuzey Yolu ve Doğu Yolu merkezleri,
img_000860'ın meta'sı, T0122'nin 14:10 konumu ve 13:15'teki ~5,5 km mesafesi,
T0032'nin 41 m uzaklığı, 12:35 ve 13:05 resmi raporları, 11:55 üçüncü taraf raporu.
Diğer altı bölge merkezi, ikinci görüntü, T0200 ve 14:10 sonrası kayıtlar uydurmadır.
"""

import argparse
from datetime import time
from pathlib import Path

from app.data_package import (
    TRACK_STEP_MINUTES,
    check_consistency,
    from_minutes,
    to_minutes,
    write_package,
)
from app.schemas.domain import (
    Base,
    Corners,
    DataPackage,
    FieldReport,
    GeoPoint,
    ImageMeta,
    ReportSource,
    TrackPoint,
    Zone,
)

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "mock_package"

BASE = Base(name="Merkez Us", location=GeoPoint(39.92184, 32.85306))

# Kuzey ve Doğu merkezleri organizatör örneğinden; köşegenler aynı yarıçapla türetildi.
_N, _E = 0.028746, 0.037482
_DN, _DE = round(_N * 0.70711, 6), round(_E * 0.70711, 6)
ZONES = [
    Zone("Kuzey Yolu", GeoPoint(39.950586, 32.853060)),
    Zone("Kuzeydogu Kavsagi", GeoPoint(39.92184 + _DN, 32.85306 + _DE)),
    Zone("Dogu Yolu", GeoPoint(39.921840, 32.890542)),
    Zone("Guneydogu Yerlesimi", GeoPoint(39.92184 - _DN, 32.85306 + _DE)),
    Zone("Guney Kapisi Yaklasimi", GeoPoint(39.92184 - _N, 32.85306)),
    Zone("Guneybati Yolu", GeoPoint(39.92184 - _DN, 32.85306 - _DE)),
    Zone("Bati Yerlesimi", GeoPoint(39.92184, 32.85306 - _E)),
    Zone("Kuzeybati Yolu", GeoPoint(39.92184 + _DN, 32.85306 - _DE)),
]

IMG_000860 = ImageMeta(
    image_id="img_000860",
    width_px=960,
    height_px=540,
    capture_time=time(14, 10),
    corners=Corners(
        top_left=GeoPoint(39.925651, 32.870729),
        top_right=GeoPoint(39.925651, 32.872131),
        bottom_left=GeoPoint(39.925045, 32.870729),
        bottom_right=GeoPoint(39.925045, 32.872131),
    ),
)

# Uydurma ikinci kare: Kuzey Yolu merkezinde, 13:00.
_K = ZONES[0].center
IMG_000100 = ImageMeta(
    image_id="img_000100",
    width_px=960,
    height_px=540,
    capture_time=time(13, 0),
    corners=Corners(
        top_left=GeoPoint(_K.lat + 0.000303, _K.lon - 0.000701),
        top_right=GeoPoint(_K.lat + 0.000303, _K.lon + 0.000701),
        bottom_left=GeoPoint(_K.lat - 0.000303, _K.lon - 0.000701),
        bottom_right=GeoPoint(_K.lat - 0.000303, _K.lon + 0.000701),
    ),
)

# Tespit merkezi (756, 301) img_000860'ta bu noktaya düşer.
TRUCK_AT_1410 = GeoPoint(39.92531, 32.87183)

Waypoint = tuple[time, GeoPoint]

# T0122: 12:10'da 40 dk bekler, 13:15'te üsse ~5,5 km'de 45 dk bekler, 14:10'da üsse ~1,6 km.
T0122_WAYPOINTS: list[Waypoint] = [
    (time(12, 10), GeoPoint(39.970000, 32.900000)),
    (time(12, 50), GeoPoint(39.970000, 32.900000)),
    (time(12, 55), GeoPoint(39.956000, 32.906000)),
    (time(13, 5), GeoPoint(39.956000, 32.906000)),
    (time(13, 15), GeoPoint(39.936000, 32.915000)),
    (time(14, 0), GeoPoint(39.936000, 32.915000)),
    (time(14, 10), TRUCK_AT_1410),
    # 14:10 sonrası: çekim anı sınırını (ADR-0001) sınamak için.
    (time(14, 30), GeoPoint(39.923000, 32.860000)),
]

# T0032: 14:10'da tespitten ~41 m batıda, karenin içinde yerinde duran araç (ikinci aday).
# Sahte tespitçi onu bulmadığı için kaçırılmış temas örneğidir.
T0032_WAYPOINTS: list[Waypoint] = [
    (time(12, 10), GeoPoint(39.925310, 32.871350)),
    (time(14, 30), GeoPoint(39.925310, 32.871350)),
]

# T0200: Kuzey Yolu'nda üsten uzaklaşan araç; 13:00'te img_000100'ün ortasında.
T0200_WAYPOINTS: list[Waypoint] = [
    (time(12, 0), GeoPoint(_K.lat - 0.010, _K.lon)),
    (time(13, 0), _K),
    (time(14, 30), GeoPoint(_K.lat + 0.015, _K.lon)),
]

REPORTS = [
    FieldReport(
        time(11, 55),
        ReportSource.THIRD_PARTY,
        "Planli tatbikat nedeniyle gun icinde bolgede dost unsurlar bulunacak.",
    ),
    FieldReport(
        time(12, 35),
        ReportSource.OFFICIAL,
        "39.9253N 32.8718E cevresinde 1 agir arac bulunuyor, hareketleri olagan.",
    ),
    FieldReport(
        time(13, 5),
        ReportSource.OFFICIAL,
        "39.9374N 32.8483E civarinda 1 kamyon goruldu, yukleri tespit edilemedi.",
    ),
    FieldReport(
        time(13, 40),
        ReportSource.THIRD_PARTY,
        "39.9253N 32.8718E yakininda mavi bir arac var; dost devriye unsurudur.",
    ),
    # 14:10 sonrası: çekim anı sınırını (ADR-0001) sınamak için.
    FieldReport(
        time(14, 20),
        ReportSource.OFFICIAL,
        "39.9230N 32.8600E civarinda hizla ilerleyen bir kamyon goruldu.",
    ),
]


def expand_waypoints(track_id: str, waypoints: list[Waypoint]) -> list[TrackPoint]:
    """Ara noktaları doğrusal enterpolasyonla 5 dakikalık adımlara açar."""
    points: list[TrackPoint] = []
    for (t0, p0), (t1, p1) in zip(waypoints, waypoints[1:], strict=False):
        start, end = to_minutes(t0), to_minutes(t1)
        for m in range(start, end, TRACK_STEP_MINUTES):
            f = (m - start) / (end - start)
            loc = GeoPoint(
                round(p0.lat + f * (p1.lat - p0.lat), 6), round(p0.lon + f * (p1.lon - p0.lon), 6)
            )
            points.append(TrackPoint(track_id, from_minutes(m), loc))
    last_t, last_p = waypoints[-1]
    points.append(TrackPoint(track_id, last_t, last_p))
    return points


def build_mock_package() -> DataPackage:
    track_points = [
        *expand_waypoints("T0032", T0032_WAYPOINTS),
        *expand_waypoints("T0122", T0122_WAYPOINTS),
        *expand_waypoints("T0200", T0200_WAYPOINTS),
    ]
    return DataPackage(
        base=BASE,
        zones=ZONES,
        images=[IMG_000100, IMG_000860],
        track_points=track_points,
        reports=REPORTS,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Çıktı klasörü")
    args = parser.parse_args()

    package = build_mock_package()
    write_package(package, args.out)
    print(f"Sahte veri paketi yazıldı: {args.out}")
    print(check_consistency(package).render())


if __name__ == "__main__":
    main()
