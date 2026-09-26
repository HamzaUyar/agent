"""Veri deposu arayüzü ve bellek içi gerçekleştirimi.

Pipeline'lar veriye yalnızca bu arayüzden erişir. Zamana bağlı her okuma bir
üst sınır (`until`) alır: değerlendirme çekim anından sonrasını görmez (ADR-0001).
"""

from collections import defaultdict
from datetime import time
from typing import Protocol

from app.schemas.claims import ClaimRecord
from app.schemas.domain import Base, DataPackage, FieldReport, ImageMeta, TrackPoint, Zone


class DataRepository(Protocol):
    def base(self) -> Base: ...

    def zones(self) -> list[Zone]: ...

    def list_images(self) -> list[ImageMeta]: ...

    def get_image(self, image_id: str) -> ImageMeta | None: ...

    def track_history(
        self, track_id: str, until: time, since: time | None = None
    ) -> list[TrackPoint]:
        """Bir track'in `since`–`until` (dahil) arasındaki noktaları, zamana göre sıralı."""
        ...

    def track_points_between(self, since: time, until: time) -> list[TrackPoint]:
        """Bütün track'lerin `since`–`until` (dahil) arasındaki noktaları, zamana göre sıralı."""
        ...

    def reports_between(self, until: time, since: time | None = None) -> list[FieldReport]:
        """`since`–`until` (dahil) arasındaki raporlar, zamana göre sıralı."""
        ...

    def claims_until(self, until: time) -> list[ClaimRecord]:
        """Rapor saati `until` ve öncesi olan iddialar, rapor saatine göre sıralı."""
        ...


class InMemoryRepository:
    """Bir `DataPackage` üzerinde çalışan depo; testlerde ve sahte veriyle kullanılır."""

    def __init__(self, package: DataPackage, claims: list[ClaimRecord] | None = None) -> None:
        self._package = package
        self._claims = sorted(claims or [], key=lambda r: (r.report.time, r.claim_id))
        self._images = {m.image_id: m for m in package.images}
        self._by_track: dict[str, list[TrackPoint]] = defaultdict(list)
        for point in sorted(package.track_points, key=lambda p: p.time):
            self._by_track[point.track_id].append(point)

    def base(self) -> Base:
        return self._package.base

    def zones(self) -> list[Zone]:
        return list(self._package.zones)

    def list_images(self) -> list[ImageMeta]:
        return sorted(self._images.values(), key=lambda m: (m.capture_time, m.image_id))

    def get_image(self, image_id: str) -> ImageMeta | None:
        return self._images.get(image_id)

    def track_history(
        self, track_id: str, until: time, since: time | None = None
    ) -> list[TrackPoint]:
        return [
            p
            for p in self._by_track.get(track_id, [])
            if p.time <= until and (since is None or p.time >= since)
        ]

    def track_points_between(self, since: time, until: time) -> list[TrackPoint]:
        return sorted(
            (p for points in self._by_track.values() for p in points if since <= p.time <= until),
            key=lambda p: (p.time, p.track_id),
        )

    def reports_between(self, until: time, since: time | None = None) -> list[FieldReport]:
        return sorted(
            (
                r
                for r in self._package.reports
                if r.time <= until and (since is None or r.time >= since)
            ),
            key=lambda r: r.time,
        )

    def claims_until(self, until: time) -> list[ClaimRecord]:
        return [r for r in self._claims if r.report.time <= until]
