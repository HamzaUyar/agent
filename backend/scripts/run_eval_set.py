"""Değerlendirme setini çalıştırır: seviye, eşleşme ve rapor kararı doğruluğu.

Veri ve iddialar varsayılan olarak Supabase'ten okunur; `--package` ile yerel bir paket
(ve `--claims` ile iddialar) kullanılır. Tespit bileşeni `.env` ayarına göre seçilir
(`DETECTOR_MODE`); `--detections` sahte tespitleri bir dosyadan verir. Her görüntü baştan
değerlendirilir, önbellek kullanılmaz.

Sentetik paket, Supabase'e yüklemeden:
    python -m scripts.run_eval_set synthetic/labels.toml --package synthetic/package \
        --claims synthetic/claims.json --detections synthetic/detections.json --no-llm
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.eval_set import LabelError, load_labels, run_eval_set
from scripts.common import add_source_args, build_service

DEFAULT_LABELS = Path(__file__).resolve().parents[1] / "eval" / "labels.toml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "labels", nargs="?", type=Path, default=DEFAULT_LABELS, help="Etiket dosyası (TOML)"
    )
    add_source_args(parser)
    parser.add_argument("--json", type=Path, help="Sonuçları ayrıca bu JSON dosyasına yaz")
    args = parser.parse_args()

    try:
        labels = load_labels(args.labels)
    except LabelError as exc:
        sys.exit(f"Etiketler okunamadı: {exc}")

    service = build_service(args)

    mode = "yalnızca kurallar" if args.no_llm else "LLM + VLM"
    print(f"{len(labels.images)} görüntü · {mode}\n")
    result = run_eval_set(service, labels)
    print(result.render())
    if args.json:
        args.json.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON: {args.json}")
    if result.summary.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
