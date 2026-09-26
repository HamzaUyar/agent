"""2. aşama veri paketini okur, yazar ve tutarlılığını denetler.

Paket düzeni (organizatör formatı):
    image_meta.json, zones.json, tracks.csv, field_reports.json, images/
"""

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any

from app.schemas.domain import (
    Base,
    Corners,
    DataPackage,
    FieldReport,
    GeoPoint,
    ImageMeta,
    ReportSource,
    TrackPoint,
    Zone,
)

IMAGE_META_FILE = "image_meta.json"
ZONES_FILE = "zones.json"
TRACKS_FILE = "tracks.csv"
REPORTS_FILE = "field_reports.json"
IMAGES_DIR = "images"
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
TRACK_STEP_MINUTES = 5


class DataPackageError(ValueError):
    """Veri paketi okunamadı ya da beklenen formatta değil."""


def find_image_file(images_dir: Path, image_id: str) -> Path | None:
    """`images_dir` içinde görüntünün dosyası (uzantı büyük/küçük harf fark etmez)."""
    for suffix in sorted(IMAGE_SUFFIXES):
        for candidate in (
            images_dir / f"{image_id}{suffix}",
            images_dir / f"{image_id}{suffix.upper()}",
        ):
            if candidate.is_file():
                return candidate
    return None


def parse_hhmm(value: str) -> time:
    try:
        hours, minutes = value.strip().split(":")
        return time(int(hours), int(minutes))
    except ValueError as exc:
        raise DataPackageError(f"Saat 'SS:DD' biçiminde değil: {value!r}") from exc


def format_hhmm(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _point(pair: list[float]) -> GeoPoint:
    lat, lon = pair
    return GeoPoint(lat=float(lat), lon=float(lon))


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise DataPackageError(f"Dosya bulunamadı: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def read_package(root: Path) -> DataPackage:
    """`root` klasöründeki veri paketini okur."""
    zones_raw = _read_json(root / ZONES_FILE)
    base_raw = zones_raw["base"]
    base = Base(
        name=base_raw["name"],
        location=GeoPoint(lat=float(base_raw["lat"]), lon=float(base_raw["lon"])),
    )
    zones = [Zone(name=z["name"], center=_point(z["center"])) for z in zones_raw["zones"]]

    images: list[ImageMeta] = []
    for image_id, meta in _read_json(root / IMAGE_META_FILE).items():
        c = meta["corner_coordinates"]
        images.append(
            ImageMeta(
                image_id=image_id,
                width_px=int(meta["width_px"]),
                height_px=int(meta["height_px"]),
                capture_time=parse_hhmm(meta["capture_time"]),
                corners=Corners(
                    top_left=_point(c["top_left"]),
                    top_right=_point(c["top_right"]),
                    bottom_left=_point(c["bottom_left"]),
                    bottom_right=_point(c["bottom_right"]),
                ),
            )
        )

    tracks_path = root / TRACKS_FILE
    if not tracks_path.is_file():
        raise DataPackageError(f"Dosya bulunamadı: {tracks_path}")
    with tracks_path.open(encoding="utf-8", newline="") as f:
        track_points = [
            TrackPoint(
                track_id=row["track_id"],
                time=parse_hhmm(row["time"]),
                location=GeoPoint(lat=float(row["lat"]), lon=float(row["lon"])),
            )
            for row in csv.DictReader(f)
        ]

    reports_raw = _read_json(root / REPORTS_FILE)
    if isinstance(reports_raw, dict):
        reports_raw = reports_raw.get("reports", [])
    reports = [
        FieldReport(time=parse_hhmm(r["time"]), source=ReportSource(r["source"]), text=r["text"])
        for r in reports_raw
    ]

    images_dir = root / IMAGES_DIR
    image_files = (
        {
            p.stem
            for p in images_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith(".")
        }
        if images_dir.is_dir()
        else set()
    )

    return DataPackage(
        base=base,
        zones=zones,
        images=images,
        track_points=track_points,
        reports=reports,
        image_files=image_files,
    )


def write_package(package: DataPackage, root: Path) -> None:
    """Paketi organizatör formatında `root` klasörüne yazar (görüntü dosyaları hariç)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / IMAGES_DIR).mkdir(exist_ok=True)

    def pair(p: GeoPoint) -> list[float]:
        return [p.lat, p.lon]

    zones = {
        "base": {
            "name": package.base.name,
            "lat": package.base.location.lat,
            "lon": package.base.location.lon,
        },
        "zones": [{"name": z.name, "center": pair(z.center)} for z in package.zones],
    }
    image_meta = {
        m.image_id: {
            "width_px": m.width_px,
            "height_px": m.height_px,
            "capture_time": format_hhmm(m.capture_time),
            "corner_coordinates": {
                "top_left": pair(m.corners.top_left),
                "top_right": pair(m.corners.top_right),
                "bottom_left": pair(m.corners.bottom_left),
                "bottom_right": pair(m.corners.bottom_right),
            },
        }
        for m in package.images
    }
    reports = [
        {"time": format_hhmm(r.time), "source": r.source.value, "text": r.text}
        for r in package.reports
    ]

    for name, payload in (
        (ZONES_FILE, zones),
        (IMAGE_META_FILE, image_meta),
        (REPORTS_FILE, reports),
    ):
        (root / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    with (root / TRACKS_FILE).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["track_id", "time", "lat", "lon"])
        for p in package.track_points:
            writer.writerow(
                [p.track_id, format_hhmm(p.time), f"{p.location.lat:.6f}", f"{p.location.lon:.6f}"]
            )


@dataclass
class ConsistencyReport:
    image_count: int
    track_count: int
    track_point_count: int
    report_count: int
    images_without_file: list[str] = field(default_factory=list)
    files_without_meta: list[str] = field(default_factory=list)
    off_step_capture_times: list[str] = field(default_factory=list)
    tracks_with_gaps: list[str] = field(default_factory=list)
    duplicate_track_points: list[str] = field(default_factory=list)
    capture_time_range: tuple[str, str] | None = None
    track_time_range: tuple[str, str] | None = None
    report_time_range: tuple[str, str] | None = None

    @property
    def warnings(self) -> list[str]:
        items: list[str] = []
        if self.images_without_file:
            items.append(f"Dosyası olmayan görüntü: {', '.join(self.images_without_file)}")
        if self.files_without_meta:
            items.append(
                f"Meta kaydı olmayan görüntü dosyası: {', '.join(self.files_without_meta)}"
            )
        if self.off_step_capture_times:
            items.append(
                "5 dakikalık adıma denk gelmeyen çekim saati (interpolasyon gerekir): "
                + ", ".join(self.off_step_capture_times)
            )
        if self.tracks_with_gaps:
            items.append(f"Adım boşluğu olan track: {', '.join(self.tracks_with_gaps)}")
        if self.duplicate_track_points:
            items.append(
                "Aynı saatte birden fazla noktası olan track: "
                + ", ".join(self.duplicate_track_points)
            )
        return items

    def render(self) -> str:
        lines = [
            "Tutarlılık raporu",
            f"  görüntü: {self.image_count} · track: {self.track_count} · "
            f"track noktası: {self.track_point_count} · rapor: {self.report_count}",
        ]
        for label, rng in (
            ("çekim saatleri", self.capture_time_range),
            ("track saatleri", self.track_time_range),
            ("rapor saatleri", self.report_time_range),
        ):
            if rng:
                lines.append(f"  {label}: {rng[0]}–{rng[1]}")
        warnings = self.warnings
        if warnings:
            lines.extend(f"  ⚠ {w}" for w in warnings)
        else:
            lines.append("  ✓ uyarı yok")
        return "\n".join(lines)


def to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def from_minutes(m: int) -> time:
    m = max(m, 0)
    return time(m // 60, m % 60)


def _time_range(times: list[time]) -> tuple[str, str] | None:
    return (format_hhmm(min(times)), format_hhmm(max(times))) if times else None


def check_consistency(package: DataPackage) -> ConsistencyReport:
    """Paketteki eksik, hizasız ve tekrarlı kayıtları raporlar."""
    meta_ids = {m.image_id for m in package.images}

    points_by_track: dict[str, list[time]] = defaultdict(list)
    for p in package.track_points:
        points_by_track[p.track_id].append(p.time)

    gaps: list[str] = []
    duplicates: list[str] = []
    for track_id, times in sorted(points_by_track.items()):
        if len(set(times)) != len(times):
            duplicates.append(track_id)
        ordered = sorted(set(times))
        steps = {to_minutes(b) - to_minutes(a) for a, b in zip(ordered, ordered[1:], strict=False)}
        if steps - {TRACK_STEP_MINUTES}:
            gaps.append(track_id)

    return ConsistencyReport(
        image_count=len(package.images),
        track_count=len(points_by_track),
        track_point_count=len(package.track_points),
        report_count=len(package.reports),
        images_without_file=sorted(meta_ids - package.image_files),
        files_without_meta=sorted(package.image_files - meta_ids),
        off_step_capture_times=sorted(
            f"{m.image_id} ({format_hhmm(m.capture_time)})"
            for m in package.images
            if to_minutes(m.capture_time) % TRACK_STEP_MINUTES
        ),
        tracks_with_gaps=gaps,
        duplicate_track_points=duplicates,
        capture_time_range=_time_range([m.capture_time for m in package.images]),
        track_time_range=_time_range([p.time for p in package.track_points]),
        report_time_range=_time_range([r.time for r in package.reports]),
    )
