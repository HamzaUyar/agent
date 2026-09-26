"""KOL A + KOL B birleştirme: tespitleri çekim anındaki track konumlarıyla birebir eşler.

Eşleme görüntü başına birebirdir: bir track yalnızca bir tespite, bir tespit yalnızca bir
track'e bağlanır. Eşik içindeki çiftler arasından toplam mesafeyi en aza indiren atama
seçilir (Hungarian, `scipy.optimize.linear_sum_assignment`). Mesafeler neredeyse eşitse
güveni yüksek tespit kazanır: maliyet = mesafe + `score_tiebreak` × (1 − güven).
"""

from dataclasses import dataclass
from math import cos, hypot, radians

from scipy.optimize import linear_sum_assignment

from app.schemas.domain import Detection, GeoPoint, TrackPoint

MATCH_THRESHOLD_M = 5.0
SCORE_TIEBREAK = 0.01

METERS_PER_DEGREE = 111_320.0
_UNREACHABLE = 1e9
"""Eşik dışı çiftlerin maliyeti; atamada seçilse bile eşleşme sayılmaz."""


def local_distance_m(a: GeoPoint, b: GeoPoint) -> float:
    """Eşleşme mesafesi: düzlem yaklaşımıyla metre (birkaç metrelik farklarda haversine'le aynı)."""
    dy = (a.lat - b.lat) * METERS_PER_DEGREE
    dx = (a.lon - b.lon) * METERS_PER_DEGREE * cos(radians(a.lat))
    return hypot(dx, dy)


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
    """Atamada bu tespite düşen track; yoksa temas kayıt dışıdır."""
    second: Candidate | None
    """Atanan track dışındaki en yakın track (eşikten bağımsız), brief'te aday olarak gösterilir."""
    ambiguous: bool = False
    """Eşik içinde başka tespite atanmamış birden fazla track vardı (belirsiz eşleşme)."""


def match_detections(
    located: list[LocatedDetection],
    points_at_capture: list[TrackPoint],
    threshold_m: float = MATCH_THRESHOLD_M,
    score_tiebreak: float = SCORE_TIEBREAK,
) -> list[MatchResult]:
    """Toplam mesafeyi en aza indiren birebir atama; yalnızca eşik içindeki çiftler eşleşir."""
    distances = [
        [local_distance_m(item.location, p.location) for p in points_at_capture] for item in located
    ]

    assigned: dict[int, Candidate] = {}
    if located and points_at_capture:
        cost = [[_UNREACHABLE] * len(points_at_capture) for _ in located]
        for i, (item, row) in enumerate(zip(located, distances, strict=True)):
            penalty = score_tiebreak * (1.0 - item.detection.confidence)
            for j, d in enumerate(row):
                if d <= threshold_m:
                    cost[i][j] = d + penalty
        rows, cols = linear_sum_assignment(cost)
        for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
            if cost[i][j] < _UNREACHABLE:
                assigned[i] = Candidate(points_at_capture[j].track_id, distances[i][j])
    taken = {c.track_id for c in assigned.values()}

    results: list[MatchResult] = []
    for i, (item, row) in enumerate(zip(located, distances, strict=True)):
        ranked = sorted(
            (Candidate(p.track_id, d) for p, d in zip(points_at_capture, row, strict=True)),
            key=lambda c: c.distance_m,
        )
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
