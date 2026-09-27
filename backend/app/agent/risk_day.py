"""Günün tamamı için risk motoru: her görüntünün aday track'leri, her adımda seviye.

Agent'ın aşama fonksiyonlarını (aday track'ler, tespit-track eşleşmesi) kullanır; böylece
buradaki seviyeler canlı değerlendirmedeki temel seviyelerle aynıdır. Tip, yalnızca o
görüntüdeki tespitten alınır (önceki karelerle tip çelişkisi burada aranmaz).

Canlı değerlendirme yalnızca kareye eşleşme eşiği kadar yakın track'leri temas sayar. Gün
tablosu, çekim anında kareye `FRAME_MARGIN_M` içinde olan track'leri de kapsar: görev tanımı
(s3) kaydı olan aracın çekim anında kadraj dışında kalabileceğini söylüyor; gerçek veride
20 track karenin 7-26 m dışında.
Sonuç `scripts.compute_risk` ile Supabase'e yazılır.
"""

import logging
from dataclasses import dataclass

from app.agent import stages
from app.core.rules import RiskRules
from app.data_package import to_minutes
from app.db.repositories import DataRepository
from app.pipelines.detection import Detector, ImageFileMissingError
from app.pipelines.geo import distance_m, distance_to_footprint_m
from app.pipelines.motion import positions_at
from app.risk_engine import TrackRisk, run_track, unregistered_level
from app.risk_engine.summary import ImageRisk, image_summary

logger = logging.getLogger(__name__)

FRAME_MARGIN_M = 30.0


@dataclass(frozen=True)
class DayRisk:
    tracks: dict[str, TrackRisk]
    """Track başına motor sonucu (track'in en son çekim anına kadar)."""
    image_of: dict[str, str]
    """Track -> sonucun ait olduğu görüntü."""
    images: list[ImageRisk]

    @property
    def step_count(self) -> int:
        return sum(len(r.steps) for r in self.tracks.values())


def compute_day(repo: DataRepository, detector: Detector, rules: RiskRules) -> DayRisk:
    cfg = rules.engine
    base = repo.base().location
    tracks: dict[str, TrackRisk] = {}
    image_of: dict[str, str] = {}
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
        now = image.capture_time
        histories = dict(branch.histories)
        for p in positions_at(repo.track_points_between(now, now), now):
            if p.track_id in histories:
                continue
            if distance_to_footprint_m(image, p.location) <= FRAME_MARGIN_M:
                history = repo.track_history(p.track_id, until=now)
                histories[p.track_id] = stages.engine_points(history, base, now, cfg)
        risks: list[TrackRisk] = []
        for track_id, points in histories.items():
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
    return DayRisk(tracks, image_of, summaries)
