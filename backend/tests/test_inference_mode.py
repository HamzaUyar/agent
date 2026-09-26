"""USE_INFERENCE: DEMO kayıtlı model çıktısını, REAL EVREN'deki modeli kullanır."""

from pathlib import Path

import pytest

from app.agent.service import EvaluationService
from app.core.config import Settings
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.pipelines.detection import (
    EvrenDetector,
    RecordedDetector,
    build_detector,
    read_detections_csv,
)
from app.schemas.domain import Detection, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
IMG_000860 = next(m for m in PACKAGE.images if m.image_id == "img_000860")

CSV = """image_id,cls,score,x,y,w,h
img_000860,truck,0.91,727.0,284.0,58.0,34.0
img_000860,car,0.35,20.0,500.0,20.0,20.0
img_000860,van,0.12,431.7,469.6,47.5,61.2
img_000860,tank,0.80,1.0,1.0,5.0,5.0
"""


def write_csv(tmp_path: Path) -> Path:
    path = tmp_path / "detections_all.csv"
    path.write_text(CSV, encoding="utf-8")
    return path


def test_csv_rows_below_the_model_request_threshold_and_unknown_classes_are_dropped(
    tmp_path: Path,
) -> None:
    detections = read_detections_csv(write_csv(tmp_path))

    assert detections == {
        "img_000860": [
            Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34),
            Detection(label=VehicleClass.CAR, confidence=0.35, x=20, y=500, w=20, h=20),
        ]
    }


def test_demo_with_a_local_package_reads_the_csv(tmp_path: Path) -> None:
    path = write_csv(tmp_path)
    settings = Settings(
        _env_file=None,
        use_inference="DEMO",
        data_source="package",
        detections_csv_path=str(path),
    )

    built = build_detector(settings)

    assert isinstance(built, RecordedDetector)
    assert built.version == "demo:detections_all.csv"
    assert [d.label for d in built.detect(IMG_000860)] == [VehicleClass.TRUCK, VehicleClass.CAR]


def test_demo_without_the_csv_fails_at_startup(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        use_inference="DEMO",
        data_source="package",
        detections_csv_path=str(tmp_path / "yok.csv"),
    )

    with pytest.raises(ValueError, match="tespit dosyası bulunamadı"):
        build_detector(settings)


def test_real_sends_images_to_evren(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        use_inference="REAL",
        evren_model_api_key="gizli",
        evren_detector_model="ekip/d2-y26l",
        data_dir=tmp_path / "data",
    )

    built = build_detector(settings)

    assert isinstance(built, EvrenDetector)
    assert built.version == "evren:ekip/d2-y26l"
    assert built.images_dir == tmp_path / "data" / "images"
    assert built.image_size == 1280


def test_real_without_a_key_fails_at_startup() -> None:
    with pytest.raises(ValueError, match="EVREN_MODEL_API_KEY"):
        build_detector(Settings(_env_file=None, use_inference="REAL"))


def test_reference_example_from_the_demo_csv(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        use_inference="DEMO",
        data_source="package",
        detections_csv_path=str(write_csv(tmp_path)),
    )
    service = EvaluationService(InMemoryRepository(PACKAGE), build_detector(settings))

    brief = service.run("img_000860")

    [truck] = [c for c in brief.contacts if c.kind == "matched"]
    assert truck.track_id == "T0122"
    assert brief.risk_level == "critical"
