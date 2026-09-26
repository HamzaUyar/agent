"""KOL A + KOL B birleştirme: tespitleri çekim anındaki en yakın track'le eşler."""

from dataclasses import dataclass

from app.pipelines.geo import distance_m
from app.schemas.domain import Detection, GeoPoint, TrackPoint

MATCH_THRESHOLD_M = 15.0


@dataclass(frozen=True)
class Candidate:
    track_id: str
    distance_m: float


@dataclass(frozen=True)
class LocatedDetection:
    detection: Detection
    location: GeoPoint


@dataclass(frozen=True)
class MatchResult:
    located: LocatedDetection
    track: Candidate | None
    """Eşik içindeki en yakın track; yoksa temas kayıt dışıdır."""
    second: Candidate | None
    """En yakın ikinci track (eşikten bağımsız), brief'te aday olarak gösterilir."""
    ambiguous: bool = False
    """Eşik içinde başka tespite atanmamış birden fazla track vardı (belirsiz eşleşme)."""


def match_detections(
    located: list[LocatedDetection],
    points_at_capture: list[TrackPoint],
    threshold_m: float = MATCH_THRESHOLD_M,
) -> list[MatchResult]:
    """Her track en fazla bir tespite atanır; eşik içi çiftler mesafeye göre açgözlü eşlenir."""
    ranked_by_item = [
        sorted(
            (
                Candidate(p.track_id, distance_m(item.location, p.location))
                for p in points_at_capture
            ),
            key=lambda c: c.distance_m,
        )
        for item in located
    ]

    assigned: dict[int, Candidate] = {}
    taken: set[str] = set()
    pairs = sorted(
        (
            (c.distance_m, i, c)
            for i, ranked in enumerate(ranked_by_item)
            for c in ranked
            if c.distance_m <= threshold_m
        ),
        key=lambda pair: (pair[0], pair[1]),
    )
    for _, i, candidate in pairs:
        if i not in assigned and candidate.track_id not in taken:
            assigned[i] = candidate
            taken.add(candidate.track_id)

    results: list[MatchResult] = []
    for i, (item, ranked) in enumerate(zip(located, ranked_by_item, strict=True)):
        track = assigned.get(i)
        # İkinci aday: eşleşmede atanan track dışındaki en yakın; eşleşme yoksa ikinci en yakın.
        if track is not None:
            second = next((c for c in ranked if c.track_id != track.track_id), None)
        else:
            second = ranked[1] if len(ranked) > 1 else None
        # Belirsizlik: eşik içinde, başka bir tespite atanmamış birden fazla aday. Komşu aracın
        # kendi track'i bu tespit için bir alternatif değildir.
        free = {track.track_id} if track else set()
        within = sum(
            1
            for c in ranked
            if c.distance_m <= threshold_m and (c.track_id not in taken or c.track_id in free)
        )
        results.append(MatchResult(located=item, track=track, second=second, ambiguous=within > 1))
    return results
