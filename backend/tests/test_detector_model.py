"""Gerçek tespit modeli: Ultralytics YOLO bağdaştırıcısı ve ayarla geçiş (ticket 11).

YOLO modeli sahte bir nesnedir; Ultralytics'in sonuç biçimi (xyxy, conf, cls, names)
taklit edilir. Kutuların `Detection`'a çevrilmesi, sınıf eşlemesi, önbellek ve
değerlendirme servisiyle birlikte çalışması gerçek kodla sınanır.
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.agent.service import EvaluationService
from app.core.config import Settings
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.pipelines.detection import (
    EvrenDetector,
    ImageFileMissingError,
    MockDetector,
    UltralyticsDetector,
    build_detector,
)
from app.schemas.domain import Detection, VehicleClass
from scripts.export_detections import export_detections

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
IMG_000860 = next(m for m in PACKAGE.images if m.image_id == "img_000860")
YOLO_NAMES = {0: "car", 1: "van", 2: "truck", 3: "bus"}


class Tensor:
    """`.tolist()` veren en küçük tensör taklidi."""

    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def tolist(self) -> list[Any]:
        return self._values


class Boxes:
    def __init__(self, rows: list[tuple[float, float, float, float, float, int]]) -> None:
        self.xyxy = Tensor([list(r[:4]) for r in rows])
        self.conf = Tensor([r[4] for r in rows])
        self.cls = Tensor([float(r[5]) for r in rows])


class Result:
    def __init__(
        self, rows: list[tuple[float, float, float, float, float, int]], names: dict[int, str]
    ) -> None:
        self.boxes = Boxes(rows)
        self.names = names


class FakeYolo:
    """Görüntü dosyasının adına göre sabit kutular döndürür; çağrıları kaydeder."""

    def __init__(
        self,
        boxes: dict[str, list[tuple[float, float, float, float, float, int]]],
        names: dict[int, str] = YOLO_NAMES,
    ) -> None:
        self.boxes = boxes
        self.names = names
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def predict(self, source: str, **kwargs: Any) -> list[Result]:
        self.calls.append((Path(source).name, kwargs))
        return [Result(self.boxes.get(Path(source).stem, []), self.names)]


# img_000860'taki truck: kutu (727, 284, 58, 34) → xyxy (727, 284, 785, 318).
TRUCK_XYXY = (727.0, 284.0, 785.0, 318.0, 0.91, 2)


@pytest.fixture
def images_dir(tmp_path: Path) -> Path:
    for meta in PACKAGE.images:
        Image.new("RGB", (meta.width_px, meta.height_px)).save(tmp_path / f"{meta.image_id}.jpg")
    return tmp_path


def detector(model: FakeYolo, images_dir: Path, **kwargs: Any) -> UltralyticsDetector:
    return UltralyticsDetector(
        Path("stage1.pt"), images_dir, model_factory=lambda _path: model, **kwargs
    )


# --- Aynı tespit arayüzü -----------------------------------------------------------


def test_yolo_boxes_become_detections_in_xywh(images_dir: Path) -> None:
    model = FakeYolo({"img_000860": [TRUCK_XYXY]})

    [d] = detector(model, images_dir).detect(IMG_000860)

    assert d == Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)


def test_every_stage1_class_is_mapped_and_unknown_classes_are_skipped(images_dir: Path) -> None:
    model = FakeYolo(
        {
            "img_000860": [
                (0, 0, 20, 20, 0.9, 0),
                (0, 0, 20, 20, 0.9, 1),
                (0, 0, 20, 20, 0.9, 2),
                (0, 0, 20, 20, 0.9, 3),
                (0, 0, 20, 20, 0.9, 7),  # modelde tanımlı olmayan sınıf
            ]
        }
    )

    labels = [d.label for d in detector(model, images_dir).detect(IMG_000860)]

    assert labels == [VehicleClass.CAR, VehicleClass.VAN, VehicleClass.TRUCK, VehicleClass.BUS]


def test_turkish_class_names_are_mapped(images_dir: Path) -> None:
    model = FakeYolo(
        {"img_000860": [(0, 0, 20, 20, 0.9, 0), (0, 0, 20, 20, 0.9, 1)]},
        names={0: "Minibus", 1: "kamyon"},
    )

    labels = [d.label for d in detector(model, images_dir).detect(IMG_000860)]

    assert labels == [VehicleClass.VAN, VehicleClass.TRUCK]


def test_model_is_asked_for_boxes_down_to_the_ignore_threshold(images_dir: Path) -> None:
    model = FakeYolo({})

    detector(model, images_dir, imgsz=1280).detect(IMG_000860)

    [(name, kwargs)] = model.calls
    assert name == "img_000860.jpg"
    assert kwargs["conf"] == 0.25
    assert kwargs["imgsz"] == 1280
    assert kwargs["verbose"] is False


def test_each_image_is_run_through_the_model_once(images_dir: Path) -> None:
    model = FakeYolo({"img_000860": [TRUCK_XYXY]})
    yolo = detector(model, images_dir)

    first = yolo.detect(IMG_000860)
    second = yolo.detect(IMG_000860)

    assert first == second
    assert len(model.calls) == 1


def test_model_is_loaded_lazily_and_once(images_dir: Path) -> None:
    loads: list[Path] = []
    model = FakeYolo({})

    def factory(path: Path) -> FakeYolo:
        loads.append(path)
        return model

    yolo = UltralyticsDetector(Path("stage1.pt"), images_dir, model_factory=factory)
    assert loads == []

    for meta in PACKAGE.images:
        yolo.detect(meta)

    assert loads == [Path("stage1.pt")]


def test_missing_image_file_is_an_error_not_an_empty_frame(tmp_path: Path) -> None:
    yolo = detector(FakeYolo({}), tmp_path)

    with pytest.raises(ImageFileMissingError, match="img_000860"):
        yolo.detect(IMG_000860)


def test_version_names_the_weights_file(images_dir: Path) -> None:
    assert detector(FakeYolo({}), images_dir).version == "yolo:stage1.pt"


# --- Değerlendirme servisiyle ------------------------------------------------------


def test_reference_example_with_the_model_detector(images_dir: Path) -> None:
    model = FakeYolo({"img_000860": [TRUCK_XYXY]})
    service = EvaluationService(InMemoryRepository(PACKAGE), detector(model, images_dir))

    brief = service.run("img_000860")

    [truck] = [c for c in brief.contacts if c.kind == "matched"]
    assert truck.track_id == "T0122"
    assert truck.label == "truck"
    assert (truck.location.lat, truck.location.lon) == pytest.approx((39.92531, 32.87183), abs=1e-5)
    assert brief.risk_level == "critical"


# --- Ayarla geçiş ------------------------------------------------------------------


def test_mock_mode_builds_the_mock_detector() -> None:
    assert isinstance(build_detector(Settings(_env_file=None, detector_mode="mock")), MockDetector)


def test_model_mode_builds_the_yolo_detector_with_resolved_paths(tmp_path: Path) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"")
    settings = Settings(
        _env_file=None,
        detector_mode="model",
        detector_weights_path=str(weights),
        data_dir=tmp_path / "data",
        detector_imgsz=1024,
    )

    built = build_detector(settings)

    assert isinstance(built, UltralyticsDetector)
    assert built.version == "yolo:best.pt"
    assert built.images_dir == tmp_path / "data" / "images"
    assert built.imgsz == 1024


def test_model_mode_without_weights_fails_at_startup(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="DETECTOR_WEIGHTS_PATH"):
        build_detector(Settings(_env_file=None, detector_mode="model"))
    with pytest.raises(ValueError, match="bulunamadı"):
        build_detector(
            Settings(
                _env_file=None,
                detector_mode="model",
                detector_weights_path=str(tmp_path / "yok.pt"),
            )
        )


def test_missing_file_of_an_earlier_frame_only_skips_its_type_history(images_dir: Path) -> None:
    (images_dir / "img_000100.jpg").unlink()  # 14:10'dan önceki kare
    model = FakeYolo({"img_000860": [TRUCK_XYXY]})
    service = EvaluationService(InMemoryRepository(PACKAGE), detector(model, images_dir))

    brief = service.run("img_000860")

    assert brief.risk_level == "critical"


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
    assert kwargs == {"confidence": 0.25, "image_size": 1280}


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


def test_evren_version_names_the_model(images_dir: Path) -> None:
    assert evren(FakeEvrenClient({}), images_dir).version == f"evren:{MODEL_ID}"


def test_reference_example_with_the_evren_detector(images_dir: Path) -> None:
    client = FakeEvrenClient({"img_000860": [TRUCK_NORMALIZED]})
    service = EvaluationService(InMemoryRepository(PACKAGE), evren(client, images_dir))

    brief = service.run("img_000860")

    [truck] = [c for c in brief.contacts if c.kind == "matched"]
    assert truck.track_id == "T0122"
    assert brief.risk_level == "critical"


def test_evren_mode_builds_the_evren_detector(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        detector_mode="evren",
        evren_model_api_key="gizli",
        evren_detector_model=MODEL_ID,
        data_dir=tmp_path / "data",
    )

    built = build_detector(settings)

    assert isinstance(built, EvrenDetector)
    assert built.version == f"evren:{MODEL_ID}"
    assert built.images_dir == tmp_path / "data" / "images"
    assert built.image_size == 1280


def test_evren_mode_without_a_key_fails_at_startup() -> None:
    with pytest.raises(ValueError, match="EVREN_MODEL_API_KEY"):
        build_detector(Settings(_env_file=None, detector_mode="evren"))


# --- Tespitlerin dosyaya aktarılması (demo için) ----------------------------------


def test_exported_detections_are_served_from_the_file_with_their_own_version(
    images_dir: Path, tmp_path: Path
) -> None:
    client = FakeEvrenClient({"img_000860": [TRUCK_NORMALIZED]})
    out = tmp_path / "detections_stage2.json"

    export_detections(evren(client, images_dir), PACKAGE.images, out)
    settings = Settings(_env_file=None, detector_mode="mock", detector_mock_path=str(out))
    served = build_detector(settings)

    assert served.version == "model çıktısı dosyadan: detections_stage2.json"
    assert served.detect(IMG_000860) == evren(client, images_dir).detect(IMG_000860)
    assert len(client.calls) == len(PACKAGE.images) + 1  # dışa aktarma + karşılaştırma
