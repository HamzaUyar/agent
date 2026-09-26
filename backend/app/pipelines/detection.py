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

    def __init__(
        self, detections: dict[str, list[Detection]] | None = None, *, version: str = "mock-1"
    ) -> None:
        self._detections = MOCK_DETECTIONS if detections is None else detections
        self.version = version

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


class _FileModelDetector:
    """Görüntü dosyasını bir modele veren detektörlerin ortak kısmı.

    Görüntüler statik olduğu için her görüntü bir kez çalıştırılıp sonucu saklanır; tip
    geçmişi için önceki karelerin tekrar tespiti böylece ucuzdur. Değerlendirmeler thread
    havuzunda paralel yürüyebildiği için çıkarım bir kilitle sıraya alınır.
    """

    def __init__(self, images_dir: Path) -> None:
        self.images_dir = images_dir
        self._cache: dict[str, list[Detection]] = {}
        self._lock = threading.Lock()

    def detect(self, image: ImageMeta) -> list[Detection]:
        with self._lock:
            if image.image_id not in self._cache:
                path = find_image_file(self.images_dir, image.image_id)
                if path is None:
                    raise ImageFileMissingError(
                        f"{image.image_id}: {self.images_dir} içinde dosya yok"
                    )
                self._cache[image.image_id] = self._infer(image, path)
            return list(self._cache[image.image_id])

    def _infer(self, image: ImageMeta, path: Path) -> list[Detection]:
        raise NotImplementedError

    @staticmethod
    def _detection(
        image: ImageMeta, name: str, conf: float, box: tuple[float, float, float, float]
    ) -> Detection | None:
        """Sınıf adı tanınmıyorsa `None`; kutu piksel cinsinden (x1, y1, x2, y2)."""
        label = CLASS_ALIASES.get(name.strip().lower())
        if label is None:
            logger.warning("%s: tanınmayan sınıf atlandı (%r)", image.image_id, name)
            return None
        x1, y1, x2, y2 = box
        return Detection(label=label, confidence=conf, x=x1, y=y1, w=x2 - x1, h=y2 - y1)


class UltralyticsDetector(_FileModelDetector):
    """1. aşama modeli, yerel ağırlık dosyasından (Ultralytics YOLO). İlk tespitte yüklenir."""

    def __init__(
        self,
        weights: Path,
        images_dir: Path,
        *,
        imgsz: int | None = None,
        model_factory: ModelFactory = _load_yolo,
    ) -> None:
        super().__init__(images_dir)
        self.weights = weights
        self.imgsz = imgsz
        self._factory = model_factory
        self._model: Any = None

    @property
    def version(self) -> str:
        return f"yolo:{self.weights.name}"

    def _infer(self, image: ImageMeta, path: Path) -> list[Detection]:
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
                name = str(result.names.get(int(cls), ""))
                if (d := self._detection(image, name, conf, (x1, y1, x2, y2))) is not None:
                    detections.append(d)
        return detections


EVREN_IMAGE_SIZE = 1280
"""Ekibin modelinin eğitildiği çıkarım boyutu (EVREN model sayfası: imgsz 1280)."""


def _evren_client(api_key: str) -> Any:
    # evren_sdk yalnızca EVREN modunda gerekir.
    return importlib.import_module("evren_sdk").EvrenClient(api_key=api_key)


class EvrenDetector(_FileModelDetector):
    """1. aşama modeli, EVREN model platformunda (evren_sdk). Görüntü EVREN'e gönderilir.

    EVREN kutuları görüntü boyutuna normalize [x1, y1, x2, y2] olarak döndürür; piksele
    çevrilir. Değerler 1'den büyükse zaten pikseldir.
    """

    def __init__(
        self,
        model: str,
        images_dir: Path,
        *,
        client: Any = None,
        api_key: str = "",
        image_size: int = EVREN_IMAGE_SIZE,
    ) -> None:
        super().__init__(images_dir)
        self.model = model
        self.image_size = image_size
        self._client = client
        self._api_key = api_key

    @property
    def version(self) -> str:
        return f"evren:{self.model}"

    def _infer(self, image: ImageMeta, path: Path) -> list[Detection]:
        if self._client is None:
            self._client = _evren_client(self._api_key)
        result = self._client.predict(
            self.model, path, confidence=MIN_CONFIDENCE, image_size=self.image_size
        )
        width = result.image_width or image.width_px
        height = result.image_height or image.height_px
        detections: list[Detection] = []
        for p in result.predictions:
            if len(p.bbox) < 4:
                continue
            x1, y1, x2, y2 = (float(v) for v in p.bbox[:4])
            if max(x1, y1, x2, y2) <= 1.0:
                x1, x2, y1, y2 = x1 * width, x2 * width, y1 * height, y2 * height
            if d := self._detection(image, p.class_name, float(p.confidence), (x1, y1, x2, y2)):
                detections.append(d)
        return detections


def build_detector(settings: Settings) -> Detector:
    """Ayara göre tespit bileşeni: mock, evren (EVREN model platformu) ya da model (yerel YOLO).

    Kimlik bilgisi ve ağırlık dosyası açılışta doğrulanır.
    """
    if settings.detector_mode == "mock":
        mock_path = settings.resolved_mock_path
        if mock_path is not None:
            # Sürüm dosyayı taşır: farklı tespit dosyalarının kayıtları önbellekte karışmasın.
            return MockDetector(load_mock_detections(mock_path), version=f"file:{mock_path.name}")
        return MockDetector()
    images_dir = settings.resolved_data_dir / "images"
    if settings.detector_mode == "evren":
        key = settings.evren_model_api_key.get_secret_value()
        if not key:
            raise ValueError("DETECTOR_MODE=evren için EVREN_MODEL_API_KEY tanımlanmalı")
        return EvrenDetector(
            settings.evren_detector_model,
            images_dir,
            api_key=key,
            image_size=settings.detector_imgsz or EVREN_IMAGE_SIZE,
        )
    weights = settings.resolved_weights_path
    if weights is None:
        raise ValueError("DETECTOR_MODE=model için DETECTOR_WEIGHTS_PATH tanımlanmalı")
    if not weights.is_file():
        raise ValueError(f"Model ağırlıkları bulunamadı: {weights}")
    return UltralyticsDetector(weights, images_dir, imgsz=settings.detector_imgsz)
