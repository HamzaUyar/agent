"""Değerlendirme setini çalıştırır: seviye, eşleşme ve rapor kararı doğruluğu.

Veri ve iddialar Supabase'ten okunur; tespit bileşeni `.env` ayarına göre seçilir
(`DETECTOR_MODE`). Her görüntü baştan değerlendirilir, önbellek kullanılmaz.
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.agent.service import EvaluationService
from app.core.config import get_settings
from app.db.models import fetch_claims, fetch_package
from app.db.repositories import InMemoryRepository
from app.db.session import connect
from app.eval_set import LabelError, load_labels, run_eval_set
from app.llm.client import build_router
from app.pipelines.detection import build_detector
from app.pipelines.vision import VlmVerifier

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
    args = parser.parse_args()

    try:
        labels = load_labels(args.labels)
    except LabelError as exc:
        sys.exit(f"Etiketler okunamadı: {exc}")

    settings = get_settings()
    with connect() as conn:
        repo = InMemoryRepository(fetch_package(conn), claims=fetch_claims(conn))
    router = None if args.no_llm else build_router(settings)
    verifier = (
        None if router is None else VlmVerifier(router, settings.resolved_data_dir / "images")
    )
    detector = build_detector(settings)
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
