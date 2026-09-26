"""KOL A: tespit arayüzü ve gerçekleştirimleri.

Hangisinin kullanılacağı `USE_INFERENCE` ile seçilir: `DEMO` modelin önceden alınmış
çıktısını (Supabase `model_detections` ya da CSV), `REAL` EVREN'deki modeli kullanır. İkisi de
aynı `Detector` arayüzünü gerçekleştirir: görüntü → sınıf, güven ve piksel kutusu.
"""

import csv
import importlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.db.models import fetch_model_detections
from app.db.session import connect
from app.schemas.domain import Detection, ImageMeta, VehicleClass
from app.storage import SupabaseStorage, build_storage, resolve_image_file

logger = logging.getLogger(__name__)

# Modelden istenen en düşük güven. Değerlendirmedeki eşikler `risk_rules.toml` [detection];
# bu sabitler varsayılanlarıdır (sentetik üreteç ve tespit bileşenleri kullanır).
MIN_CONFIDENCE = 0.20
STRONG_CONFIDENCE = 0.50


class Detector(Protocol):
    @property
    def version(self) -> str:
        """Kayıtlara yazılan tespit bileşeni sürümü."""
        ...

    def detect(self, image: ImageMeta) -> list[Detection]: ...


class ImageFileMissingError(FileNotFoundError):
    """Görüntünün dosyası yok; model çalıştırılamaz (boş kare sayılmaz)."""


def load_detections_json(path: Path) -> dict[str, list[Detection]]:
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


def dump_detections_json(detections: dict[str, list[Detection]], path: Path) -> None:
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


def read_detections_csv(
    path: Path, min_confidence: float = MIN_CONFIDENCE
) -> dict[str, list[Detection]]:
    """Modelin çıktısı: `image_id, cls, score, x, y, w, h` (kutu sol üst köşe + boyut, piksel).

    Modelden canlı istenen alt sınırın (`min_confidence`) altındaki satırlar alınmaz; böylece
    DEMO ve REAL aynı kutuları görür.
    """
    detections: dict[str, list[Detection]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            label = CLASS_ALIASES.get(row["cls"].strip().lower())
            if label is None:
                logger.warning("%s: tanınmayan sınıf atlandı (%r)", row["image_id"], row["cls"])
                continue
            score = float(row["score"])
            if score < min_confidence:
                continue
            detections.setdefault(row["image_id"], []).append(
                Detection(
                    label=label,
                    confidence=score,
                    x=float(row["x"]),
                    y=float(row["y"]),
                    w=float(row["w"]),
                    h=float(row["h"]),
                )
            )
    return detections


class RecordedDetector:
    """Modelin önceden alınmış çıktısını görüntü kimliğine göre döndürür (USE_INFERENCE=DEMO)."""

    def __init__(self, detections: dict[str, list[Detection]], *, version: str) -> None:
        self._detections = detections
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


class _FileModelDetector:
    """Görüntü dosyasını bir modele veren detektörün ortak kısmı.

    Görüntüler statik olduğu için her görüntü bir kez çalıştırılıp sonucu saklanır; tip
    geçmişi için önceki karelerin tekrar tespiti böylece ucuzdur. Değerlendirmeler thread
    havuzunda paralel yürüyebildiği için çıkarım bir kilitle sıraya alınır.
    """

    def __init__(self, images_dir: Path, storage: SupabaseStorage | None = None) -> None:
        self.images_dir = images_dir
        self.storage = storage
        self._cache: dict[str, list[Detection]] = {}
        self._lock = threading.Lock()

    def detect(self, image: ImageMeta) -> list[Detection]:
        with self._lock:
            if image.image_id not in self._cache:
                path = resolve_image_file(self.images_dir, image, self.storage)
                if path is None:
                    raise ImageFileMissingError(
                        f"{image.image_id}: {self.images_dir} içinde ve Storage'da dosya yok"
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
        storage: SupabaseStorage | None = None,
    ) -> None:
        super().__init__(images_dir, storage)
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


def _demo_detector(settings: Settings) -> Detector:
    """USE_INFERENCE=DEMO: modelin önceden alınmış çıktısı; veri kaynağıyla aynı yerden okunur."""
    if settings.data_source == "package":
        path = settings.resolved_detections_csv_path
        if not path.is_file():
            raise ValueError(f"USE_INFERENCE=DEMO için tespit dosyası bulunamadı: {path}")
        return RecordedDetector(read_detections_csv(path), version=f"demo:{path.name}")
    source = settings.detections_source
    with connect(settings) as conn:
        detections = fetch_model_detections(conn, source, MIN_CONFIDENCE)
    if not detections:
        raise ValueError(
            f"USE_INFERENCE=DEMO: model_detections tablosunda '{source}' kaynağı boş "
            "(python -m scripts.load_detections)"
        )
    return RecordedDetector(detections, version=f"demo:{source}")


def build_detector(settings: Settings) -> Detector:
    """`USE_INFERENCE`'a göre tespit bileşeni: DEMO kayıtlı çıktı, REAL EVREN'deki model.

    Kimlik bilgisi ve tespit kaynağı açılışta doğrulanır.
    """
    if settings.use_inference == "DEMO":
        return _demo_detector(settings)
    key = settings.evren_model_api_key.get_secret_value()
    if not key:
        raise ValueError("USE_INFERENCE=REAL için EVREN_MODEL_API_KEY tanımlanmalı")
    return EvrenDetector(
        settings.evren_detector_model,
        settings.resolved_data_dir / "images",
        api_key=key,
        image_size=settings.detector_imgsz or EVREN_IMAGE_SIZE,
        storage=build_storage(settings),
    )
