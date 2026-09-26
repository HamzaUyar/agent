"""Kol B eşleşmeden bağımsız: track kolu tespitle paralel çalışır, temaslar hazır sonucu kullanır.

Görev tanımı s3: her track kendi görüntüsünün çekim anında biter; karedeki track'lerin
hareketi tespiti beklemeden hesaplanabilir.
"""

import threading
from collections import Counter
from dataclasses import replace
from datetime import time
from pathlib import Path

from app.agent.service import EvaluationService
from app.core.rules import default_rules
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.schemas.domain import Detection, GeoPoint, ImageMeta, TrackPoint, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
[IMAGE] = [m for m in PACKAGE.images if m.image_id == "img_000860"]
THRESHOLD_M = default_rules().matching.threshold_m
METERS_PER_DEGREE_LAT = 111_320


def north_of_frame(meters: float) -> GeoPoint:
    """Karenin üst kenarının ortasından `meters` kuzeyde bir nokta."""
    c = IMAGE.corners
    return GeoPoint(
        c.top_left.lat + meters / METERS_PER_DEGREE_LAT, (c.top_left.lon + c.top_right.lon) / 2
    )


def standing_track(track_id: str, at: GeoPoint) -> list[TrackPoint]:
    """12:10–14:10 arası yerinde duran track (çekim anı 14:10)."""
    return [
        TrackPoint(track_id, time(h, m), at)
        for h in (12, 13, 14)
        for m in range(0, 60, 5)
        if (12, 10) <= (h, m) <= (14, 10)
    ]


class FakeDetector:
    version = "test"

    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK] if image.image_id == "img_000860" else []


class RecordingRepository(InMemoryRepository):
    """Hareket geçmişi okumalarını track başına sayar."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.history_reads: Counter[str] = Counter()

    def track_history(
        self, track_id: str, *, until: time, since: time | None = None
    ) -> list[TrackPoint]:
        self.history_reads[track_id] += 1
        return super().track_history(track_id, until=until, since=since)


def package_with_edge_tracks() -> object:
    """Karenin hemen dışında (eşik içinde) ve çok uzağında birer duran track eklenir."""
    near = standing_track("T0901", north_of_frame(THRESHOLD_M / 2))
    far = standing_track("T0902", north_of_frame(500))
    return replace(PACKAGE, track_points=[*PACKAGE.track_points, *near, *far])


def test_track_branch_analyzes_tracks_in_or_near_the_frame_only() -> None:
    repo = InMemoryRepository(package_with_edge_tracks())  # type: ignore[arg-type]
    service = EvaluationService(repo, FakeDetector())

    branch = service.track_branch(IMAGE)

    ids = set(branch.motions)
    assert {"T0122", "T0032"} <= ids  # karenin içinde
    assert "T0901" in ids  # dışarıda ama eşik mesafesi içinde
    assert "T0902" not in ids  # 500 m uzakta
    assert {p.track_id for p in branch.positions} == ids


def test_contacts_reuse_the_track_branch_motion_instead_of_recomputing_it() -> None:
    repo = RecordingRepository(PACKAGE)
    service = EvaluationService(repo, FakeDetector())

    brief = service.run("img_000860")

    contact_tracks = {c.track_id for c in brief.contacts if c.track_id}
    assert contact_tracks == {"T0122", "T0032"}
    assert all(repo.history_reads[t] == 1 for t in contact_tracks), repo.history_reads


def test_track_branch_runs_in_parallel_with_detection() -> None:
    """Tespit ve track kolu aynı anda beklemeye girer; sıralı çalışsalar bariyer kırılırdı."""
    barrier = threading.Barrier(2, timeout=2)

    class WaitingDetector(FakeDetector):
        waited = False

        def detect(self, image: ImageMeta) -> list[Detection]:
            if not self.waited:
                self.waited = True
                barrier.wait()
            return super().detect(image)

    class WaitingRepository(InMemoryRepository):
        waited = False

        def track_points_between(self, since: time, until: time) -> list[TrackPoint]:
            if not self.waited:
                self.waited = True
                barrier.wait()
            return super().track_points_between(since, until)

    service = EvaluationService(WaitingRepository(PACKAGE), WaitingDetector())
    events = [e.name for e in service.evaluate("img_000860")]

    assert not barrier.broken
    assert events == [
        "goruntu",
        "tespit",
        "konum",
        "eslesme",
        "hareket",
        "raporlar",
        "risk",
        "karar",
        "brief",
    ]
