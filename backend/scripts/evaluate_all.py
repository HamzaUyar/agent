"""Bütün görüntüleri baştan değerlendirir ve kaydeder (`analysis_runs`, `agent_steps`).

Kurallar ya da risk motoru değiştiğinde çalıştırılır: önbellek yalnızca güncel kural
sürümüyle (`rules_version`) yapılmış kayıtları oynattığı için, bu komuttan sonra arayüz ve
harita yeni kayıtları kullanır. Tespitler `.env`'e göre (DEMO: Supabase `model_detections`),
rapor doğrulamaları ortak önbellekten gelir. Görüntüler sırayla değerlendirilir.
Ardından hiçbir görüntüde olmayan track'ler değerlendirilir (scripts.assess_tracks) ve her
track'in bir değerlendirmede yer aldığı veritabanından kontrol edilir.

    python -m scripts.evaluate_all                 # hepsi
    python -m scripts.evaluate_all img_000860      # yalnızca verilenler
    python -m scripts.evaluate_all --missing       # güncel sürümde kaydı olmayanlar
    python -m scripts.evaluate_all --skip-tracks   # görüntüsüz track'ler olmadan
"""

import argparse
import time
from collections import Counter

from app.agent.runner import EvaluationRunner
from app.api.stores import DatabaseStores
from app.core.rules import rules_version
from app.db.risk_store import track_coverage
from app.db.session import connect
from app.schemas.api import Brief
from scripts.assess_tracks import assess_unframed
from scripts.common import add_source_args, build_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("images", nargs="*", help="Görüntü kimlikleri (varsayılan: hepsi)")
    parser.add_argument(
        "--missing", action="store_true", help="güncel kural sürümüyle kaydı olanları atla"
    )
    parser.add_argument(
        "--skip-tracks", action="store_true", help="görüntüsüz track değerlendirmesini atla"
    )
    add_source_args(parser)
    args = parser.parse_args()
    if args.package:
        parser.error("Kayıtlar Supabase'e yazılır; --package desteklenmiyor")

    service = build_service(args)
    version = rules_version(service.rules)
    ids = args.images or sorted(m.image_id for m in service.repository.list_images())
    print(f"Kural sürümü {version} · tespit {service.detector_version} · {len(ids)} görüntü")

    stores = DatabaseStores()
    levels: Counter[str] = Counter()
    fallbacks, failures = 0, []
    for i, image_id in enumerate(ids, 1):
        with stores.open() as (runs, _):
            runner = EvaluationRunner(service, runs, detector_version=service.detector_version)
            if args.missing and runs.latest_cached(image_id, service.detector_version, version):
                print(f"[{i:2}/{len(ids)}] {image_id} atlandı (kayıt var)")
                continue
            started = time.monotonic()
            brief: Brief | None = None
            for kind, payload in runner.stream(image_id, recompute=True):
                if kind == "brief":
                    brief = Brief.model_validate(payload)
                elif kind == "error":
                    failures.append(image_id)
        took = time.monotonic() - started
        if brief is None:
            print(f"[{i:2}/{len(ids)}] {image_id} BAŞARISIZ ({took:.0f} sn)")
            continue
        levels[brief.risk_level] += 1
        fallbacks += brief.is_fallback
        note = " · otomatik özet" if brief.is_fallback else ""
        print(f"[{i:2}/{len(ids)}] {image_id} {brief.risk_level} ({took:.0f} sn){note}")

    print(f"Seviyeler: {dict(levels)} · otomatik özet: {fallbacks} · başarısız: {failures}")

    if not args.skip_tracks:
        assess_unframed(service.repository, service.detector, service.rules, service.router)
    with connect() as conn:
        total, in_images, unframed, missing = track_coverage(conn, version)
    print(
        f"Kapsama: {total} track · görüntü değerlendirmesinde {in_images} · "
        f"görüntüsüz değerlendirmede {unframed} · eksik {len(missing)} {missing or ''}"
    )


if __name__ == "__main__":
    main()
