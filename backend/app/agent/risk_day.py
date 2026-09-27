"""Günün tamamı için risk motoru: her görüntünün aday track'leri, her adımda seviye.

Agent'ın aşama fonksiyonlarını (aday track'ler, tespit-track eşleşmesi) kullanır; böylece
buradaki seviyeler canlı değerlendirmedeki temel seviyelerle aynıdır. Tip, yalnızca o
görüntüdeki tespitten alınır (önceki karelerle tip çelişkisi burada aranmaz).

Hiçbir görüntünün adayı olmayan track'ler (kaydı var ama çekim anında kadraj dışında kaldı,
görev tanımı s3) görüntüsüz olarak, kaydının son anına kadar değerlendirilir; görüntü
özetlerine katılmaz. Gerçek veride 20 track böyle.
Sonuç `scripts.compute_risk` ile Supabase'e yazılır.
"""

import logging
from dataclasses import dataclass

from app.agent import stages
from app.core.rules import RiskRules
from app.data_package import from_minutes, to_minutes
from app.db.repositories import DataRepository
from app.pipelines.detection import Detector, ImageFileMissingError
from app.pipelines.geo import distance_m
from app.risk_engine import TrackRisk, run_track, unregistered_level
from app.risk_engine.summary import ImageRisk, image_summary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DayRisk:
    tracks: dict[str, TrackRisk]
    """Track başına motor sonucu (track'in en son çekim anına kadar)."""
    image_of: dict[str, str | None]
    """Track -> sonucun ait olduğu görüntü; görüntüsüz track için None."""
    images: list[ImageRisk]

    @property
    def step_count(self) -> int:
        return sum(len(r.steps) for r in self.tracks.values())

    @property
    def unframed(self) -> list[str]:
        """Hiçbir görüntünün adayı olmayan track'ler."""
        return sorted(t for t, img in self.image_of.items() if img is None)


def compute_day(repo: DataRepository, detector: Detector, rules: RiskRules) -> DayRisk:
    cfg = rules.engine
    base = repo.base().location
    tracks: dict[str, TrackRisk] = {}
    image_of: dict[str, str | None] = {}
    summaries: list[ImageRisk] = []
    for image in sorted(repo.list_images(), key=lambda m: m.capture_time):
        branch = stages.track_branch(repo, image, rules)
        try:
            detected = detector.detect(image)
        except ImageFileMissingError:
            logger.warning("%s: görüntü dosyası yok, tip bilgisi olmadan", image.image_id)
            detected = []
        usable = tuple(d for d in detected if d.confidence >= rules.detection.min_confidence)
        matches = stages.match_tracks(image, stages.locate(image, usable), branch.positions, rules)
        detection_of = {m.track.track_id: m.located.detection for m in matches if m.track}
        unregistered = max(
            (
                unregistered_level(distance_m(m.located.location, base), cfg)
                for m in matches
                if m.track is None
                and m.located.detection.confidence >= cfg.unregistered.min_confidence
            ),
            default=0,
        )
        risks: list[TrackRisk] = []
        for track_id, points in branch.histories.items():
            if not points:
                continue
            det = detection_of.get(track_id)
            risk = run_track(
                track_id,
                points,
                det.label.value if det else None,
                det.confidence if det else None,
                cfg,
            )
            risks.append(risk)
            # Aynı track birden çok karede adaysa en son çekim anına kadarki sonuç tutulur.
            known = tracks.get(track_id)
            if known is None or len(risk.steps) >= len(known.steps):
                tracks[track_id] = risk
                image_of[track_id] = image.image_id
        summaries.append(
            image_summary(image.image_id, to_minutes(image.capture_time), risks, unregistered)
        )
    for track_id, risk in unframed_tracks(repo, set(tracks), rules).items():
        tracks[track_id] = risk
        image_of[track_id] = None
    return DayRisk(tracks, image_of, summaries)


def unframed_tracks(
    repo: DataRepository, framed: set[str], rules: RiskRules
) -> dict[str, TrackRisk]:
    """Görüntüsüz track'ler: kaydının son anına kadar, tipi bilinmeden değerlendirilir."""
    base = repo.base().location
    last: dict[str, int] = {}
    for p in repo.track_points_between(from_minutes(0), from_minutes(24 * 60 - 1)):
        if p.track_id not in framed:
            last[p.track_id] = max(last.get(p.track_id, 0), to_minutes(p.time))
    out: dict[str, TrackRisk] = {}
    for track_id, end in sorted(last.items()):
        now = from_minutes(end)
        points = stages.engine_points(
            repo.track_history(track_id, until=now), base, now, rules.engine
        )
        if points:
            out[track_id] = run_track(track_id, points, None, None, rules.engine)
    return out
