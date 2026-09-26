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

from app.agent.service import EvaluationService
from app.core.config import get_settings
from app.data_package import read_package
from app.db.models import fetch_claims, fetch_package
from app.db.repositories import InMemoryRepository
from app.db.session import connect
from app.eval_set import LabelError, load_labels, run_eval_set
from app.llm.client import build_router
from app.pipelines.detection import Detector, MockDetector, build_detector, load_mock_detections
from app.pipelines.vision import VlmVerifier
from scripts.make_synthetic_data import load_claims

DEFAULT_LABELS = Path(__file__).resolve().parents[1] / "eval" / "labels.toml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "labels", nargs="?", type=Path, default=DEFAULT_LABELS, help="Etiket dosyası (TOML)"
    )
    parser.add_argument(
        "--no-llm", action="store_true", help="LLM ve VLM olmadan, yalnızca kod kurallarıyla"
    )
    parser.add_argument("--json", type=Path, help="Sonuçları ayrıca bu JSON dosyasına yaz")
    parser.add_argument("--package", type=Path, help="Supabase yerine yerel veri paketi")
    parser.add_argument("--claims", type=Path, help="--package ile: iddialar (claims.json)")
    parser.add_argument("--detections", type=Path, help="Sahte tespitler (detections.json)")
    args = parser.parse_args()

    try:
        labels = load_labels(args.labels)
    except LabelError as exc:
        sys.exit(f"Etiketler okunamadı: {exc}")

    settings = get_settings()
    if args.package:
        claims = load_claims(args.claims) if args.claims else []
        repo = InMemoryRepository(read_package(args.package), claims=claims)
        images_dir = args.package / "images"
    else:
        with connect() as conn:
            repo = InMemoryRepository(fetch_package(conn), claims=fetch_claims(conn))
        images_dir = settings.resolved_data_dir / "images"
    router = None if args.no_llm else build_router(settings)
    verifier = None if router is None else VlmVerifier(router, images_dir)
    detector: Detector = (
        MockDetector(load_mock_detections(args.detections))
        if args.detections
        else build_detector(settings)
    )
    service = EvaluationService(repo, detector, router=router, verifier=verifier)

    mode = "yalnızca kurallar" if router is None else "LLM + VLM"
    print(f"{len(labels.images)} görüntü · tespit: {detector.version} · {mode}\n")
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
