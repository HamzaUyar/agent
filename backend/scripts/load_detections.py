"""Modelin önceden alınmış çıktısını (CSV) Supabase `model_detections` tablosuna yükler.

`USE_INFERENCE=DEMO` + `DATA_SOURCE=supabase` bu tablodan okur. Tekrar çalıştırılabilir:
aynı kaynağın (`--source`, varsayılan dosya adı) satırları silinip baştan yazılır. Bütün
satırlar yüklenir (düşük skorlular dahil); eşik okuma sırasında uygulanır.

    python -m scripts.load_detections ../../stage2/detections_all.csv
"""

import argparse
from pathlib import Path

from app.core.config import get_settings
from app.db.models import replace_model_detections
from app.db.session import connect
from app.pipelines.detection import read_detections_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "path", type=Path, nargs="?", help="CSV dosyası (varsayılan: DETECTIONS_CSV_PATH)"
    )
    parser.add_argument("--source", help="model_detections.source (varsayılan: dosya adı)")
    args = parser.parse_args()

    settings = get_settings()
    path: Path = args.path or settings.resolved_detections_csv_path
    source: str = args.source or path.name
    detections = read_detections_csv(path, min_confidence=0.0)
    with connect(settings) as conn:
        count = replace_model_detections(conn, source, detections)
    print(f"Yüklendi: {count} tespit, {len(detections)} görüntü · kaynak: {source}")
    if source != settings.detections_source:
        print(f"Not: DEMO bu kaynağı okuması için .env'de DETECTIONS_SOURCE={source}")


if __name__ == "__main__":
    main()
