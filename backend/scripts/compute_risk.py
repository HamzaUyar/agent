"""Risk motorunu günün tamamı için çalıştırır ve sonuçları Supabase'e yazar.

Her görüntünün aday track'leri, ilk noktalarından çekim anına kadar her adımda
değerlendirilir; zaman çizelgesi, olaylar, bildirimler ve görüntü özetleri yeni bir koşu
olarak `risk_engine_runs` / `risk_timeline` / `risk_events` / `risk_notices` / `image_risk`
tablolarına yazılır. En son koşu `*_latest` görünümlerinden okunur.

    python -m scripts.compute_risk            # hesapla ve yaz
    python -m scripts.compute_risk --dry-run  # yalnızca özet
"""

import argparse
from collections import Counter

from app.agent.risk_day import compute_day
from app.core.config import get_settings
from app.core.rules import default_rules
from app.data_package import read_package
from app.db.models import fetch_package
from app.db.repositories import InMemoryRepository
from app.db.risk_store import save_day
from app.db.session import connect
from app.pipelines.detection import build_detector
from app.risk_engine import LEVEL_NAMES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="veritabanına yazma")
    args = parser.parse_args()

    settings = get_settings()
    rules = default_rules()
    if settings.data_source == "package":
        package = read_package(settings.resolved_data_dir)
    else:
        with connect(settings) as conn:
            package = fetch_package(conn)
    detector = build_detector(settings)
    day = compute_day(InMemoryRepository(package), detector, rules)

    current = Counter(LEVEL_NAMES[r.current.level] for r in day.tracks.values())
    peak = Counter(LEVEL_NAMES[max(s.level for s in r.steps)] for r in day.tracks.values())
    images = Counter(LEVEL_NAMES[i.level] for i in day.images)
    print(f"Track: {len(day.tracks)} · adım: {day.step_count} · görüntü: {len(day.images)}")
    print(f"  çekim anı seviyesi: {dict(current)}")
    print(f"  iz boyunca tepe:    {dict(peak)}")
    print(f"  görüntü seviyesi:   {dict(images)}")
    if args.dry_run:
        return
    source = settings.detections_source if settings.use_inference == "DEMO" else None
    with connect(settings) as conn:
        run_id = save_day(conn, day, rules.engine, source)
    print(f"Yazıldı: koşu {run_id} (image_risk_latest, risk_timeline_latest, risk_events_latest)")


if __name__ == "__main__":
    main()
