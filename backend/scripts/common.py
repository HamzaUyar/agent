"""Komut satırı araçlarının ortak kurulumu: veri kaynağı, detektör, LLM ve VLM."""

import argparse
from pathlib import Path

from app.agent.service import EvaluationService
from app.core.config import get_settings
from app.data_package import load_claims, read_package
from app.db.models import fetch_claims, fetch_package
from app.db.repositories import InMemoryRepository
from app.db.session import connect
from app.llm.client import build_router
from app.pipelines.detection import Detector, MockDetector, build_detector, load_mock_detections
from app.pipelines.vision import VlmVerifier
from app.storage import build_storage


def add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-llm", action="store_true", help="LLM ve VLM olmadan, yalnızca kod kurallarıyla"
    )
    parser.add_argument("--package", type=Path, help="Supabase yerine yerel veri paketi")
    parser.add_argument("--claims", type=Path, help="--package ile: iddialar (claims.json)")
    parser.add_argument("--detections", type=Path, help="Sahte tespitler (detections.json)")


def images_dir(args: argparse.Namespace) -> Path:
    if args.package:
        return Path(args.package) / "images"
    return get_settings().resolved_data_dir / "images"


def build_service(args: argparse.Namespace) -> EvaluationService:
    """Veri Supabase'ten ya da `--package`'tan; tespit `.env`'den ya da `--detections`'tan."""
    settings = get_settings()
    if args.package:
        # Detektör de görüntüleri paketin klasöründen okusun.
        settings = settings.model_copy(update={"data_dir": Path(args.package).resolve()})
        claims = load_claims(args.claims) if args.claims else []
        repo = InMemoryRepository(read_package(args.package), claims=claims)
    else:
        with connect() as conn:
            repo = InMemoryRepository(fetch_package(conn), claims=fetch_claims(conn))
    router = None if args.no_llm else build_router(settings, check_budget=True)
    verifier = (
        None
        if router is None
        else VlmVerifier(router, images_dir(args), storage=build_storage(settings))
    )
    detector: Detector = (
        MockDetector(load_mock_detections(args.detections))
        if args.detections
        else build_detector(settings)
    )
    return EvaluationService(repo, detector, router=router, verifier=verifier)
