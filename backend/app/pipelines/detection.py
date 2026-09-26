"""KOL A: tespit arayüzü, sahte gerçekleştirimi ve 1. aşama modeli (Ultralytics YOLO).

Hangisinin kullanılacağı ayarla seçilir (`DETECTOR_MODE`: mock / model). İkisi de aynı
`Detector` arayüzünü gerçekleştirir: görüntü → sınıf, güven ve piksel kutusu.
"""

import importlib
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.data_package import find_image_file
from app.schemas.domain import Detection, ImageMeta, VehicleClass

logger = logging.getLogger(__name__)

# Güven eşikleri: altı yok sayılır; arası zayıf tespittir (yalnızca track'le eşleşirse temas).
MIN_CONFIDENCE = 0.25
STRONG_CONFIDENCE = 0.50


def is_weak(detection: Detection) -> bool:
    return detection.confidence < STRONG_CONFIDENCE


class Detector(Protocol):
    @property
    def version(self) -> str:
        """Kayıtlara yazılan tespit bileşeni sürümü."""
        ...

    def detect(self, image: ImageMeta) -> list[Detection]: ...


class ImageFileMissingError(FileNotFoundError):
    """Görüntünün dosyası yok; model çalıştırılamaz (boş kare sayılmaz)."""


# Organizatör örneğindeki tespit: img_000860'ta kutu (727, 284, 58, 34), truck.
MOCK_DETECTIONS: dict[str, list[Detection]] = {
    "img_000860": [
        Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34),
    ],
}


def load_mock_detections(path: Path) -> dict[str, list[Detection]]:
    """`{image_id: [{label, confidence, x, y, w, h}, ...]}` biçimindeki JSON dosyasını okur."""
    raw: dict[str, list[dict[str, float | str]]] = json.loads(path.read_text(encoding="utf-8"))
    return {
        image_id: [
            Detection(
                label=VehicleClass(str(d["label"])),
                confidence=float(d["confidence"]),
                x=float(d["x"]),
                y=float(d["y"]),
                w=float(d["w"]),
                h=float(d["h"]),
            )
            for d in items
        ]
        for image_id, items in raw.items()
    }


def dump_mock_detections(detections: dict[str, list[Detection]], path: Path) -> None:
    payload = {
        image_id: [
            {
                "label": d.label.value,
                "confidence": d.confidence,
                "x": d.x,
                "y": d.y,
                "w": d.w,
                "h": d.h,
            }
            for d in items
        ]
        for image_id, items in detections.items()
    }
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


class MockDetector:
    """Görüntü kimliğine göre sabit tespitler döndürür; model hazır olana kadar kullanılır."""

    version = "mock-1"

    def __init__(self, detections: dict[str, list[Detection]] | None = None) -> None:
        self._detections = MOCK_DETECTIONS if detections is None else detections

    def detect(self, image: ImageMeta) -> list[Detection]:
        return list(self._detections.get(image.image_id, []))


# Modelin sınıf adları → alan sınıfları. Eğitimde Türkçe ad kullanılmış olabilir.
CLASS_ALIASES: dict[str, VehicleClass] = {
    "car": VehicleClass.CAR,
    "otomobil": VehicleClass.CAR,
    "van": VehicleClass.VAN,
    "minibus": VehicleClass.VAN,
    "truck": VehicleClass.TRUCK,
    "kamyon": VehicleClass.TRUCK,
    "bus": VehicleClass.BUS,
    "otobus": VehicleClass.BUS,
}

ModelFactory = Callable[[Path], Any]
"""Ağırlık dosyasından `predict(source, **kwargs)` veren bir model yükler."""


def _load_yolo(weights: Path) -> Any:
    # Ultralytics (torch ile) isteğe bağlı bağımlılık: yalnızca model modunda gerekir.
    ultralytics = importlib.import_module("ultralytics")
    return ultralytics.YOLO(str(weights))


class UltralyticsDetector:
    """1. aşama modeli. Görüntüler statik olduğu için her görüntü bir kez çalıştırılır.

    Model ilk tespitte yüklenir. Değerlendirmeler thread havuzunda paralel yürüyebildiği
    için yükleme ve çıkarım bir kilitle sıraya alınır.
    """

    def __init__(
        self,
        weights: Path,
        images_dir: Path,
        *,
        imgsz: int | None = None,
        model_factory: ModelFactory = _load_yolo,
    ) -> None:
        self.weights = weights
        self.images_dir = images_dir
        self.imgsz = imgsz
        self._factory = model_factory
        self._model: Any = None
        self._cache: dict[str, list[Detection]] = {}
        self._lock = threading.Lock()

    @property
    def version(self) -> str:
        return f"yolo:{self.weights.name}"

    def detect(self, image: ImageMeta) -> list[Detection]:
        with self._lock:
            if image.image_id not in self._cache:
                self._cache[image.image_id] = self._predict(image)
            return list(self._cache[image.image_id])

    def _predict(self, image: ImageMeta) -> list[Detection]:
        path = find_image_file(self.images_dir, image.image_id)
        if path is None:
            raise ImageFileMissingError(f"{image.image_id}: {self.images_dir} içinde dosya yok")
        if self._model is None:
            self._model = self._factory(self.weights)
        options: dict[str, Any] = {"conf": MIN_CONFIDENCE, "verbose": False}
        if self.imgsz is not None:
            options["imgsz"] = self.imgsz
        detections: list[Detection] = []
        for result in self._model.predict(str(path), **options):
            boxes = result.boxes
            for (x1, y1, x2, y2), conf, cls in zip(
                boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), strict=True
            ):
                name = str(result.names.get(int(cls), "")).strip().lower()
                label = CLASS_ALIASES.get(name)
                if label is None:
                    logger.warning("%s: tanınmayan sınıf atlandı (%r)", image.image_id, name)
                    continue
                detections.append(
                    Detection(label=label, confidence=conf, x=x1, y=y1, w=x2 - x1, h=y2 - y1)
                )
        return detections


def build_detector(settings: Settings) -> Detector:
    """Ayara göre tespit bileşeni. Model modunda ağırlık dosyası açılışta doğrulanır."""
    if settings.detector_mode == "mock":
        mock_path = settings.resolved_mock_path
        if mock_path is not None:
            return MockDetector(load_mock_detections(mock_path))
        return MockDetector()
    weights = settings.resolved_weights_path
    if weights is None:
        raise ValueError("DETECTOR_MODE=model için DETECTOR_WEIGHTS_PATH tanımlanmalı")
    if not weights.is_file():
        raise ValueError(f"Model ağırlıkları bulunamadı: {weights}")
    return UltralyticsDetector(
        weights, settings.resolved_data_dir / "images", imgsz=settings.detector_imgsz
    )
