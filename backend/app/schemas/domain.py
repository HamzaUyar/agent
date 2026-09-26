"""İç veri modelleri. Terimler `CONTEXT.md` ile aynıdır."""

from dataclasses import dataclass, field
from datetime import time
from enum import StrEnum
from typing import Literal

RiskLevel = Literal["low", "medium", "high", "critical"]
Trend = Literal["approaching", "receding", "stationary", "passing", "unknown"]
VehicleColor = Literal[
    "beyaz",
    "siyah",
    "gri",
    "kirmizi",
    "mavi",
    "yesil",
    "sari",
    "turuncu",
    "kahverengi",
    "bej",
    "mor",
]
"""Görsel doğrulamanın renk paleti; rapordaki renk buna indirgenerek karşılaştırılır."""
CargoState = Literal["loaded", "empty"]


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class Base:
    """Üs."""

    name: str
    location: GeoPoint


@dataclass(frozen=True)
class Zone:
    """Bölge; yalnızca merkez noktasıyla tanımlı."""

    name: str
    center: GeoPoint


@dataclass(frozen=True)
class Corners:
    top_left: GeoPoint
    top_right: GeoPoint
    bottom_left: GeoPoint
    bottom_right: GeoPoint

    def as_ring(self) -> list[GeoPoint]:
        """Köşeleri kapalı bir halka olarak döndürür (saat yönünde, ilk nokta tekrar eder)."""
        return [
            self.top_left,
            self.top_right,
            self.bottom_right,
            self.bottom_left,
            self.top_left,
        ]

    @property
    def center(self) -> GeoPoint:
        points = (self.top_left, self.top_right, self.bottom_left, self.bottom_right)
        return GeoPoint(
            lat=sum(p.lat for p in points) / 4,
            lon=sum(p.lon for p in points) / 4,
        )


@dataclass(frozen=True)
class ImageMeta:
    """Görüntü: boyut, çekim anı ve köşe koordinatları."""

    image_id: str
    width_px: int
    height_px: int
    capture_time: time
    corners: Corners


@dataclass(frozen=True)
class TrackPoint:
    track_id: str
    time: time
    location: GeoPoint


class VehicleClass(StrEnum):
    CAR = "car"
    VAN = "van"
    TRUCK = "truck"
    BUS = "bus"


HEAVY_CLASSES = frozenset({VehicleClass.TRUCK, VehicleClass.BUS})

# Tip çelişkisinde riskli olan seçilir: ağır araçlar en riskli.
TYPE_RISK_ORDER = (VehicleClass.CAR, VehicleClass.VAN, VehicleClass.BUS, VehicleClass.TRUCK)


def riskier_type(labels: list[VehicleClass]) -> VehicleClass:
    return max(labels, key=TYPE_RISK_ORDER.index)


@dataclass(frozen=True)
class Detection:
    """Tespit: modelin tek bir görüntüde bulduğu araç; kutu piksel cinsinden (x, y, w, h)."""

    label: VehicleClass
    confidence: float
    x: float
    y: float
    w: float
    h: float

    @property
    def center_px(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


class ReportSource(StrEnum):
    OFFICIAL = "official"
    THIRD_PARTY = "third_party"


@dataclass(frozen=True)
class FieldReport:
    """Rapor: saatli, kaynaklı serbest metin gözlem."""

    time: time
    source: ReportSource
    text: str


@dataclass(frozen=True)
class DataPackage:
    """2. aşama veri paketinin okunmuş hali."""

    base: Base
    zones: list[Zone]
    images: list[ImageMeta]
    track_points: list[TrackPoint]
    reports: list[FieldReport]
    image_files: set[str] = field(default_factory=set)
    """Paketin `images/` klasöründe dosyası bulunan görüntü kimlikleri."""
