"""2. aşama veri paketini Supabase'e yükler ve tutarlılık raporu basar.

Tekrar çalıştırılabilir: kayıtlar doğal anahtarlarıyla güncellenir, çoğaltılmaz.
`--replace` kaynak tabloları önce boşaltır; bu, bağlı bütün değerlendirmeleri de siler.
"""

import argparse
from collections import defaultdict
from datetime import time
from pathlib import Path

import psycopg

from app.core.config import get_settings
from app.data_package import IMAGES_DIR, check_consistency, read_package
from app.db.session import connect
from app.pipelines.geo import nearest_zone
from app.schemas.domain import DataPackage, GeoPoint

SOURCE_TABLES = ("field_reports", "track_points", "tracks", "images", "zones", "bases")

POINT_SQL = "extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography"


def _polygon_wkt(ring: list[GeoPoint]) -> str:
    coords = ", ".join(f"{p.lon} {p.lat}" for p in ring)
    return f"SRID=4326;POLYGON(({coords}))"


def load(conn: psycopg.Connection, package: DataPackage, *, replace: bool = False) -> None:
    """Paketi tek bir transaction içinde yazar."""
    with conn.transaction(), conn.cursor() as cur:
        if replace:
            cur.execute(f"truncate {', '.join(f'public.{t}' for t in SOURCE_TABLES)} cascade")

        base = package.base
        cur.execute(
            f"""insert into public.bases (name, location) values (%s, {POINT_SQL})
                on conflict (name) do update set location = excluded.location""",
            (base.name, base.location.lon, base.location.lat),
        )

        zone_ids: dict[str, int] = {}
        for zone in package.zones:
            cur.execute(
                f"""insert into public.zones (name, center) values (%s, {POINT_SQL})
                    on conflict (name) do update set center = excluded.center
                    returning id""",
                (zone.name, zone.center.lon, zone.center.lat),
            )
            row = cur.fetchone()
            assert row is not None
            zone_ids[zone.name] = row[0]

        for m in package.images:
            c, center = m.corners, m.corners.center
            zone = nearest_zone(center, package.zones)
            cur.execute(
                f"""insert into public.images (
                        id, file_path, width_px, height_px, capture_time,
                        tl_lat, tl_lon, tr_lat, tr_lon, bl_lat, bl_lon, br_lat, br_lon,
                        footprint, center, zone_id)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            extensions.st_geogfromtext(%s), {POINT_SQL}, %s)
                    on conflict (id) do update set
                        file_path = excluded.file_path, width_px = excluded.width_px,
                        height_px = excluded.height_px, capture_time = excluded.capture_time,
                        tl_lat = excluded.tl_lat, tl_lon = excluded.tl_lon,
                        tr_lat = excluded.tr_lat, tr_lon = excluded.tr_lon,
                        bl_lat = excluded.bl_lat, bl_lon = excluded.bl_lon,
                        br_lat = excluded.br_lat, br_lon = excluded.br_lon,
                        footprint = excluded.footprint, center = excluded.center,
                        zone_id = excluded.zone_id""",
                (
                    m.image_id,
                    f"{IMAGES_DIR}/{m.image_id}.jpg",
                    m.width_px,
                    m.height_px,
                    m.capture_time,
                    c.top_left.lat,
                    c.top_left.lon,
                    c.top_right.lat,
                    c.top_right.lon,
                    c.bottom_left.lat,
                    c.bottom_left.lon,
                    c.bottom_right.lat,
                    c.bottom_right.lon,
                    _polygon_wkt(c.as_ring()),
                    center.lon,
                    center.lat,
                    zone_ids[zone.name],
                ),
            )

        times: dict[str, list[time]] = defaultdict(list)
        for p in package.track_points:
            times[p.track_id].append(p.time)
        cur.executemany(
            """insert into public.tracks (id, first_seen, last_seen) values (%s, %s, %s)
               on conflict (id) do update set
                   first_seen = excluded.first_seen, last_seen = excluded.last_seen""",
            [(tid, min(ts), max(ts)) for tid, ts in times.items()],
        )
        cur.executemany(
            f"""insert into public.track_points (track_id, time, location)
                values (%s, %s, {POINT_SQL})
                on conflict (track_id, time) do update set location = excluded.location""",
            [(p.track_id, p.time, p.location.lon, p.location.lat) for p in package.track_points],
        )

        # Doğal anahtar dosyadaki sıra: birebir aynı iki rapor da korunur (migration 08).
        cur.executemany(
            """insert into public.field_reports (seq, time, source, text) values (%s, %s, %s, %s)
               on conflict (seq) do update set
                   time = excluded.time, source = excluded.source, text = excluded.text""",
            [(i, r.time, r.source.value, r.text) for i, r in enumerate(package.reports)],
        )


def table_counts(conn: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in reversed(SOURCE_TABLES):
            cur.execute(f"select count(*) from public.{table}")
            row = cur.fetchone()
            counts[table] = row[0] if row else 0
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "path", type=Path, nargs="?", help="Veri paketi klasörü (varsayılan: DATA_DIR)"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Önce kaynak tabloları boşalt (değerlendirmeler de silinir)",
    )
    parser.add_argument(
        "--check-only", action="store_true", help="Sadece tutarlılık raporunu bas, yükleme yapma"
    )
    args = parser.parse_args()

    root = args.path or get_settings().resolved_data_dir
    package = read_package(root)
    print(f"Veri paketi: {root}")
    print(check_consistency(package).render())
    if args.check_only:
        return

    with connect() as conn:
        load(conn, package, replace=args.replace)
        counts = table_counts(conn)
    print("Yüklendi · " + " · ".join(f"{t}: {n}" for t, n in counts.items()))


if __name__ == "__main__":
    main()
