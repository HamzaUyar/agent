"""Tespit modeli: EVREN bağdaştırıcısı, `USE_INFERENCE=REAL` ile kurulumu ve dışa aktarma.

EVREN istemcisi sahte bir nesnedir; `evren_sdk`'nin sonuç biçimi taklit edilir. Kutuların
`Detection`'a çevrilmesi, sınıf eşlemesi, önbellek ve değerlendirme servisiyle birlikte
çalışması gerçek kodla sınanır.
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.pipelines.detection import (
    EvrenDetector,
    ImageFileMissingError,
    RecordedDetector,
    load_detections_json,
)
from app.schemas.domain import VehicleClass
from scripts.export_detections import export_detections

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
IMG_000860 = next(m for m in PACKAGE.images if m.image_id == "img_000860")


@pytest.fixture
def images_dir(tmp_path: Path) -> Path:
    for meta in PACKAGE.images:
        Image.new("RGB", (meta.width_px, meta.height_px)).save(tmp_path / f"{meta.image_id}.jpg")
    return tmp_path


# --- EVREN model platformu (evren_sdk) ----------------------------------------------


class FakePrediction:
    def __init__(self, class_name: str, confidence: float, bbox: list[float]) -> None:
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox


class FakeEvrenResult:
    def __init__(self, predictions: list[FakePrediction], width: int, height: int) -> None:
        self.predictions = predictions
        self.image_width = width
        self.image_height = height


class FakeEvrenClient:
    """EVREN'in cevabı: kutular görüntü boyutuna normalize [x1, y1, x2, y2]."""

    def __init__(self, predictions: dict[str, list[FakePrediction]]) -> None:
        self.predictions = predictions
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def predict(self, model: str, image: Path, **kwargs: Any) -> FakeEvrenResult:
        self.calls.append((model, Path(image).name, kwargs))
        return FakeEvrenResult(self.predictions.get(Path(image).stem, []), 960, 540)


# img_000860'taki truck (727, 284, 58, 34), 960×540'a normalize.
TRUCK_NORMALIZED = FakePrediction(
    "truck", 0.91, [727 / 960, 284 / 540, (727 + 58) / 960, (284 + 34) / 540]
)
MODEL_ID = "ekip/d2-y26l"


def evren(client: FakeEvrenClient, images_dir: Path, **kwargs: Any) -> EvrenDetector:
    return EvrenDetector(MODEL_ID, images_dir, client=client, **kwargs)


def test_evren_normalized_boxes_become_pixel_detections(images_dir: Path) -> None:
    client = FakeEvrenClient({"img_000860": [TRUCK_NORMALIZED]})

    [d] = evren(client, images_dir).detect(IMG_000860)

    assert d.label == VehicleClass.TRUCK
    assert d.confidence == 0.91
    assert (d.x, d.y, d.w, d.h) == pytest.approx((727, 284, 58, 34))


def test_evren_pixel_boxes_are_accepted_as_they_are(images_dir: Path) -> None:
    client = FakeEvrenClient({"img_000860": [FakePrediction("car", 0.8, [10, 20, 50, 40])]})

    [d] = evren(client, images_dir).detect(IMG_000860)

    assert (d.x, d.y, d.w, d.h) == (10, 20, 40, 20)


def test_evren_request_uses_the_model_image_size_and_ignore_threshold(images_dir: Path) -> None:
    client = FakeEvrenClient({})

    evren(client, images_dir).detect(IMG_000860)

    [(model, name, kwargs)] = client.calls
    assert (model, name) == (MODEL_ID, "img_000860.jpg")
    assert kwargs == {"confidence": 0.20, "image_size": 1280}


def test_evren_unknown_classes_are_skipped_and_each_image_is_sent_once(images_dir: Path) -> None:
    client = FakeEvrenClient(
        {"img_000860": [TRUCK_NORMALIZED, FakePrediction("person", 0.9, [0.1, 0.1, 0.2, 0.2])]}
    )
    detector = evren(client, images_dir)

    first = detector.detect(IMG_000860)
    second = detector.detect(IMG_000860)

    assert [d.label for d in first] == [VehicleClass.TRUCK]
    assert first == second
    assert len(client.calls) == 1


def test_evren_missing_image_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ImageFileMissingError, match="img_000860"):
        evren(FakeEvrenClient({}), tmp_path).detect(IMG_000860)


def test_every_stage1_class_and_turkish_names_are_mapped(images_dir: Path) -> None:
    box = [0.1, 0.1, 0.2, 0.2]
    names = ["car", "van", "truck", "bus", "Minibus", "kamyon", "otomobil", "otobus"]
    client = FakeEvrenClient({"img_000860": [FakePrediction(n, 0.9, box) for n in names]})

    labels = [d.label for d in evren(client, images_dir).detect(IMG_000860)]

    assert labels == [
        VehicleClass.CAR,
        VehicleClass.VAN,
        VehicleClass.TRUCK,
        VehicleClass.BUS,
        VehicleClass.VAN,
        VehicleClass.TRUCK,
        VehicleClass.CAR,
        VehicleClass.BUS,
    ]


def test_evren_version_names_the_model(images_dir: Path) -> None:
    assert evren(FakeEvrenClient({}), images_dir).version == f"evren:{MODEL_ID}"


def test_reference_example_with_the_evren_detector(images_dir: Path) -> None:
    client = FakeEvrenClient({"img_000860": [TRUCK_NORMALIZED]})
    service = EvaluationService(InMemoryRepository(PACKAGE), evren(client, images_dir))

    brief = service.run("img_000860")

    [truck] = [c for c in brief.contacts if c.kind == "matched"]
    assert truck.track_id == "T0122"
    assert brief.risk_level == "critical"


def test_missing_file_of_an_earlier_frame_only_skips_its_type_history(images_dir: Path) -> None:
    (images_dir / "img_000100.jpg").unlink()  # 14:10'dan önceki kare
    client = FakeEvrenClient({"img_000860": [TRUCK_NORMALIZED]})
    service = EvaluationService(InMemoryRepository(PACKAGE), evren(client, images_dir))

    brief = service.run("img_000860")

    assert brief.risk_level == "critical"


# --- Tespitlerin dosyaya aktarılması (değerlendirme seti için) --------------------


def test_exported_detections_are_served_from_the_file(images_dir: Path, tmp_path: Path) -> None:
    client = FakeEvrenClient({"img_000860": [TRUCK_NORMALIZED]})
    out = tmp_path / "detections_stage2.json"

    export_detections(evren(client, images_dir), PACKAGE.images, out)
    served = RecordedDetector(load_detections_json(out), version="dosya:detections_stage2.json")

    assert served.detect(IMG_000860) == evren(client, images_dir).detect(IMG_000860)
    assert len(client.calls) == len(PACKAGE.images) + 1  # dışa aktarma + karşılaştırma
