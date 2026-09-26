"""Değerlendirme aşamaları: her biri küçük, dondurulmuş girdi ve çıktılarla çalışır.

Saf aşamalar yalnızca argümanlarından hesaplar. Yan etkili olanlar (depo okuması, tespit
modeli, VLM, LLM) bunu imzalarında açıkça taşır: `repo`, `detector`, `verifier` ya da
`router` alırlar. Hiçbir aşama çekim anından sonraki veriyi okumaz (ADR-0001): depo
sorguları çekim anıyla (ya da ondan önceki rapor saatiyle) sınırlıdır.

Sıra: `image_context` → Kol A `detect` ∥ Kol B `track_branch` → `locate` →
`match_contacts` → `inspect_visuals` → `label_history` → `build_contacts` →
`evaluate_reports` → `apply_reports` → `assess_risk` → `decide_level` → `compose_brief`.
"""

import logging
from collections import defaultdict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import time

from app.agent.brief_text import brief_text, sources
from app.agent.decision import DecisionUnavailableError, decide
from app.core.rules import DetectionRules, LevelRules, MatchingRules, ReportRules, RiskRules
from app.data_package import TRACK_STEP_MINUTES, format_hhmm, from_minutes, to_minutes
from app.db.repositories import DataRepository
from app.llm.client import LLMRouter
from app.pipelines.detection import Detector, ImageFileMissingError
from app.pipelines.geo import (
    distance_m,
    distance_to_footprint_m,
    in_footprint,
    nearest_zone,
    pixel_to_geo,
)
from app.pipelines.matching import LocatedDetection, MatchResult, match_detections
from app.pipelines.motion import Position, analyze_motion, positions_at
from app.pipelines.reports import ClaimEvaluation, ContactView, evaluate_claims, visual_track_ids
from app.pipelines.risk import LEVELS, base_level, highest, recommended_action
from app.pipelines.vision import BBox, VisualVerifier
from app.schemas.api import (
    Brief,
    Certainty,
    ContactFinding,
    LabelObservation,
    LatLon,
    MotionFinding,
    ReportFinding,
    StopFinding,
    TrackCandidate,
    VisualFinding,
)
from app.schemas.claims import ClaimRecord
from app.schemas.domain import (
    Detection,
    GeoPoint,
    ImageMeta,
    RiskLevel,
    TrackPoint,
    VehicleClass,
    riskier_type,
)

logger = logging.getLogger(__name__)

# Aynı anda en fazla bu kadar görsel doğrulama; gateway de 4 eşzamanlı istek kabul ediyor.
VISUAL_WORKERS = 4
# Aday track sınırına eklenen pay: eşleşme düzlem yaklaşımıyla, kareye uzaklık haversine'le
# ölçülüyor; eşik sınırındaki bir track iki ölçü arasındaki küçük fark yüzünden kaçmasın.
CANDIDATE_SLACK_M = 1.0

Visuals = Mapping[BBox, VisualFinding | None]
"""Görsel doğrulama sonuçları, kutu başına; bakılamayan kutu `None`. Sıra, soruluş sırasıdır."""


# --- aşama girdi ve çıktıları -------------------------------------------------------


@dataclass(frozen=True)
class ImageContext:
    """Değerlendirilen görüntü ve sabit sahnesi: üs konumu ve en yakın bölge."""

    image: ImageMeta
    base: GeoPoint
    zone: str

    @property
    def now(self) -> time:
        """Çekim anı: değerlendirmenin "şimdi"si."""
        return self.image.capture_time

    @property
    def at(self) -> str:
        return format_hhmm(self.now)


@dataclass(frozen=True)
class Detections:
    """Kol A: tespit modelinin kullanılabilir kutuları; düşük güvenliler yalnızca sayılır."""

    usable: tuple[Detection, ...]
    ignored: int


@dataclass(frozen=True)
class TrackBranch:
    """Kol B'nin bir görüntü için hazır sonucu; tespitten bağımsız hesaplanır.

    Görev tanımı s3: her track kendi görüntüsünün çekim anında biter. Adaylar çekim anında
    karenin içinde ya da kareye eşleşme eşiği kadar yakın olan track'lerdir.
    """

    positions: list[Position]
    """Adayların çekim anındaki konumları (adım dışı çekim saatinde ileri kestirilmiş)."""
    motions: dict[str, MotionFinding]
    """Her adayın son iki saatlik hareket özeti."""


@dataclass(frozen=True)
class Matches:
    """Tespitlerin çekim anındaki track'lerle birebir eşleşmesi."""

    matches: tuple[MatchResult, ...]
    """Track'le eşleşen ya da eşleşmese de güçlü olan tespitler; eşsiz zayıf tespit düşer."""
    missed: tuple[Position, ...]
    """Karede olduğu halde hiçbir tespitle eşleşmeyen track'ler (kaçırılmış temas)."""
    estimated: frozenset[str]
    """Çekim anı konumu ileri kestirilmiş track'ler."""


@dataclass(frozen=True)
class Contacts:
    contacts: tuple[ContactFinding, ...]


@dataclass(frozen=True)
class ClaimEvaluations:
    """Çekim anına kadarki iddiaların bu görüntüdeki temaslarla karşılaştırılması."""

    evaluations: tuple[ClaimEvaluation, ...]
    findings: tuple[ReportFinding, ...]
    visuals: Visuals
    """Önceden yapılan görsel doğrulamalar ve değerlendirme sırasında bakılan kutular."""


@dataclass(frozen=True)
class RiskResult:
    """Kurallarla hesaplanmış seviye (ADR-0002): temas seviyelerinin en yükseği."""

    level: RiskLevel
    contacts: tuple[ContactFinding, ...]
    riskiest: ContactFinding | None


@dataclass(frozen=True)
class FinalDecision:
    """LLM'in ±1 kademe ayarından sonraki son seviye; LLM yoksa kuralların sonucu."""

    level: RiskLevel
    contacts: tuple[ContactFinding, ...]
    riskiest: ContactFinding | None
    assessment: str | None
    model: str | None
    fallback_reason: str | None
    accepted: int = 0
    rejected: int = 0


# --- yardımcılar ----------------------------------------------------------------------


def latlon(p: GeoPoint) -> LatLon:
    return LatLon(lat=p.lat, lon=p.lon)


def bbox(d: Detection) -> BBox:
    return (d.x, d.y, d.w, d.h)


def is_weak(detection: Detection, rules: DetectionRules) -> bool:
    """Zayıf tespit: yalnızca bir track'le eşleşirse temas sayılır."""
    return detection.confidence < rules.strong_confidence


def _usable(detected: list[Detection], rules: DetectionRules) -> list[Detection]:
    """Güveni `min_confidence`'ın altındaki kutular yok sayılır."""
    return [d for d in detected if d.confidence >= rules.min_confidence]


def _certainty(*, weak: bool, uncertain: bool, confirmed: bool = False) -> Certainty:
    """Zayıf tespit, VLM onu araç olarak doğruladıysa "olası"ya çıkar."""
    if weak and not confirmed:
        return "weak"
    return "likely" if uncertain or weak else "certain"


def _riskiest(contacts: tuple[ContactFinding, ...]) -> ContactFinding | None:
    return max(contacts, key=lambda c: LEVELS.index(c.final_level), default=None)


# --- sahne -----------------------------------------------------------------------------


def image_context(repo: DataRepository, image: ImageMeta) -> ImageContext:
    """Depo: üs konumu ve görüntü merkezine en yakın bölge."""
    zone = nearest_zone(image.corners.center, repo.zones()).name
    return ImageContext(image, repo.base().location, zone)


# --- Kol A: tespit ve konum ------------------------------------------------------------


def detect(detector: Detector, image: ImageMeta, rules: DetectionRules) -> Detections:
    """Tespit modeli: kullanılabilir kutular ve yok sayılanların sayısı."""
    detected = detector.detect(image)
    usable = _usable(detected, rules)
    return Detections(tuple(usable), len(detected) - len(usable))


def locate(image: ImageMeta, detections: tuple[Detection, ...]) -> tuple[LocatedDetection, ...]:
    """Saf: kutu merkezleri köşe koordinatlarından doğrusal oranla konuma çevrilir."""
    return tuple(LocatedDetection(d, pixel_to_geo(image, *d.center_px)) for d in detections)


# --- Kol B: track'ler ------------------------------------------------------------------


def track_branch(repo: DataRepository, image: ImageMeta, rules: RiskRules) -> TrackBranch:
    """Depo: aday track'lerin çekim anı konumu ve hareket analizi, tespitten bağımsız."""
    base = repo.base().location
    positions = candidate_positions(repo, image, rules.matching)
    motions = {
        p.track_id: motion_finding(repo, p.track_id, base, image.capture_time, rules)
        for p in positions
    }
    return TrackBranch(positions, motions)


def candidate_positions(
    repo: DataRepository, image: ImageMeta, rules: MatchingRules
) -> list[Position]:
    """Depo: çekim anında karenin içinde ya da kareye eşleşme eşiği kadar yakın track'ler."""
    now = image.capture_time
    since = from_minutes(to_minutes(now) - 2 * TRACK_STEP_MINUTES)
    reach = rules.threshold_m + CANDIDATE_SLACK_M
    return [
        p
        for p in positions_at(repo.track_points_between(since, now), now)
        if distance_to_footprint_m(image, p.location) <= reach
    ]


def motion_finding(
    repo: DataRepository, track_id: str, base: GeoPoint, now: time, rules: RiskRules
) -> MotionFinding:
    """Depo: track'in çekim anına kadarki geçmişinden hareket özeti."""
    since = from_minutes(to_minutes(now) - rules.motion.history_minutes)
    history = repo.track_history(track_id, until=now, since=since)
    m = analyze_motion(history, base, now, repo.zones(), rules.trend, rules.motion)
    ongoing = m.stops[-1] if m.stops and m.stops[-1].end == history[-1].time else None
    return MotionFinding(
        distance_to_base_m=m.distance_to_base_m,
        distance_to_base_30min_ago_m=m.distance_to_base_window_ago_m,
        distance_to_base_60min_ago_m=m.distance_to_base_hour_ago_m,
        trend=m.trend,
        route=[latlon(p) for p in m.route],
        total_distance_m=m.total_distance_m,
        avg_speed_mps=m.avg_speed_mps,
        recent_speed_mps=m.recent_speed_mps,
        heading_deg=m.heading_deg,
        stops=[
            StopFinding(
                start=format_hhmm(s.start),
                end=format_hhmm(s.end),
                minutes=s.minutes,
                location=latlon(s.location),
                zone=s.zone,
                distance_to_base_m=distance_m(s.location, base),
            )
            for s in m.stops
        ],
        zones_passed=m.zones_passed,
        current_stop_minutes=ongoing.minutes if ongoing else None,
        stop_open_ended=ongoing is not None and ongoing.start == history[0].time,
        base_distance_min_m=m.base_distance_min_m,
        base_distance_max_m=m.base_distance_max_m,
        extent_m=m.extent_m,
    )


# --- eşleşme ---------------------------------------------------------------------------


def match_tracks(
    image: ImageMeta,
    located: tuple[LocatedDetection, ...],
    positions: list[Position],
    rules: RiskRules,
) -> list[MatchResult]:
    """Saf: tespitleri aday track'lerin çekim anı konumlarıyla birebir eşler.

    Güçlü ve zayıf tespitler tek atamada eşlenir; eşitlik bozma güçlü tespiti öne alır.
    Eşleşmeyen zayıf tespit düşer.
    """
    points = [TrackPoint(p.track_id, image.capture_time, p.location) for p in positions]
    m = rules.matching
    matches = match_detections(list(located), points, m.threshold_m, m.score_tiebreak)
    return [
        x
        for x in matches
        if x.track is not None or not is_weak(x.located.detection, rules.detection)
    ]


def match_contacts(
    image: ImageMeta,
    located: tuple[LocatedDetection, ...],
    branch: TrackBranch,
    rules: RiskRules,
) -> Matches:
    """Saf: eşleşmeler, karede olduğu halde eşleşmeyen track'ler ve kestirilmiş konumlar."""
    matches = match_tracks(image, located, branch.positions, rules)
    assigned = {m.track.track_id for m in matches if m.track}
    missed = tuple(
        p
        for p in branch.positions
        if p.track_id not in assigned and in_footprint(image, p.location)
    )
    estimated = frozenset(p.track_id for p in branch.positions if p.estimated)
    return Matches(tuple(matches), missed, estimated)


# --- görsel doğrulama ------------------------------------------------------------------


def inspect_visuals(
    verifier: VisualVerifier | None,
    image: ImageMeta,
    matches: Matches,
    claims: list[ClaimRecord],
    rules: RiskRules,
) -> Visuals:
    """VLM: bütün görsel doğrulama tek bir paralel dalgada; doğrulayıcı yoksa boş.

    - Track'le eşleşen zayıf tespit: araç derse kesinlik "olası"ya çıkar. "Araç değil"
      cevabı kutuyu düşürmez: track orada bir araç olduğunu zaten gösteriyor.
    - Renk ya da yük belirten iddianın bağlanacağı kutu: bağlama ucuz bir hesap, rapor
      değerlendirmesiyle aynı kuralla önceden yapılır; değerlendirme yalnızca sonucu okur.
    Her VLM çağrısı ~10 sn; sırayla sormak çağrı sayısıyla çarpılırdı.
    """
    if verifier is None:
        return {}
    tracked = [m for m in matches.matches if m.track]
    weak = [
        bbox(m.located.detection) for m in tracked if is_weak(m.located.detection, rules.detection)
    ]
    tracked_boxes = {m.track.track_id: bbox(m.located.detection) for m in tracked if m.track}
    views = [
        ContactView(m.track.track_id if m.track else None, None, m.located.location)
        for m in matches.matches
    ] + [ContactView(p.track_id, None, p.location) for p in matches.missed]
    claimed = visual_track_ids(
        claims,
        views,
        image_center=image.corners.center,
        now=image.capture_time,
        rules=rules.reports,
    )
    boxes = list(
        dict.fromkeys(weak + [tracked_boxes[t] for t in sorted(claimed) if t in tracked_boxes])
    )
    if not boxes:
        return {}
    with ThreadPoolExecutor(max_workers=VISUAL_WORKERS) as pool:
        found = pool.map(lambda box: verifier.inspect(image, box), boxes)
        return dict(zip(boxes, found, strict=True))


def visually_unconfirmed(matches: Matches, visuals: Visuals, rules: DetectionRules) -> list[str]:
    """Saf: VLM'in araç göremediği, track'le eşleşmiş zayıf tespitlerin track'leri."""
    return [
        m.track.track_id
        for m in matches.matches
        if m.track
        and is_weak(m.located.detection, rules)
        and (v := visuals.get(bbox(m.located.detection))) is not None
        and not v.is_vehicle
    ]


# --- temaslar --------------------------------------------------------------------------


def label_history(
    repo: DataRepository, detector: Detector, image: ImageMeta, rules: RiskRules
) -> dict[str, list[LabelObservation]]:
    """Depo ve tespit modeli: çekim anına kadarki karelerde her track'in sınıfı."""
    now = image.capture_time
    history: dict[str, list[LabelObservation]] = defaultdict(list)
    frames = [m for m in repo.list_images() if m.capture_time <= now]
    for frame in frames:
        try:
            detected = detector.detect(frame)
        except ImageFileMissingError:
            # Önceki karenin dosyası yoksa yalnızca tip geçmişi eksik kalır.
            logger.warning("Tip geçmişi: %s atlandı, dosya yok", frame.image_id)
            continue
        located = locate(frame, tuple(_usable(detected, rules.detection)))
        positions = candidate_positions(repo, frame, rules.matching)
        for m in match_tracks(frame, located, positions, rules):
            if m.track:
                history[m.track.track_id].append(
                    LabelObservation(image_id=frame.image_id, label=m.located.detection.label.value)
                )
    return history


def _loiter_minutes(motion: MotionFinding | None, rules: LevelRules) -> int:
    """Üsse `loiter_m`'den yakın en uzun duraklamanın süresi."""
    if motion is None:
        return 0
    return max(
        (s.minutes for s in motion.stops if s.distance_to_base_m < rules.loiter_m), default=0
    )


def _circling_path_m(motion: MotionFinding | None, rules: LevelRules) -> float:
    """Üssün çevresinde dar bir mesafe bandında kalarak gidilen yol; dolaşmıyorsa 0.

    Görev tanımı s3: araçlar üs çevresinde dolaşır. Üsse mesafesi kayıt boyunca
    `circle_band_m` içinde kalan, `loiter_m`'den yakın ve en az `circle_min_extent_m`
    genişliğinde bir yay çizen araç dolaşıyordur; yerinde gidip gelen yerel trafik değil.
    """
    if (
        motion is None
        or motion.base_distance_max_m >= rules.loiter_m
        or motion.base_distance_max_m - motion.base_distance_min_m > rules.circle_band_m
        or motion.extent_m < rules.circle_min_extent_m
    ):
        return 0.0
    return motion.total_distance_m


def _detection_contact(
    match: MatchResult,
    ctx: ImageContext,
    branch: TrackBranch,
    estimated: frozenset[str],
    history: Mapping[str, list[LabelObservation]],
    visual: VisualFinding | None,
    rules: RiskRules,
) -> ContactFinding:
    det = match.located.detection
    location = match.located.location
    dist_base = distance_m(location, ctx.base)
    track_id = match.track.track_id if match.track else None
    weak = is_weak(det, rules.detection)

    motion = branch.motions[track_id] if track_id else None
    observed = history.get(track_id, []) if track_id else []
    labels = {VehicleClass(o.label) for o in observed} | {det.label}
    effective = riskier_type(sorted(labels, key=str))
    decision = base_level(
        effective,
        dist_base,
        motion.trend if motion else None,
        registered=track_id is not None,
        loiter_minutes_near_base=_loiter_minutes(motion, rules.levels),
        circling_path_m=_circling_path_m(motion, rules.levels),
        rules=rules.levels,
    )
    position_estimated = track_id in estimated
    return ContactFinding(
        kind="matched" if track_id else "unregistered",
        label=det.label.value,
        effective_label=effective.value,
        confidence=det.confidence,
        bbox=bbox(det),
        location=latlon(location),
        is_weak=weak,
        is_ambiguous=match.ambiguous,
        position_estimated=position_estimated,
        type_conflict=len(labels) > 1,
        observed_labels=observed,
        distance_to_base_m=dist_base,
        track_id=track_id,
        match_distance_m=match.track.distance_m if match.track else None,
        second_candidate=(
            TrackCandidate(track_id=match.second.track_id, distance_m=match.second.distance_m)
            if match.second
            else None
        ),
        motion=motion,
        visual=visual,
        base_level=decision.level,
        final_level=decision.level,
        level_reasons=decision.reasons,
        certainty=_certainty(
            weak=weak,
            uncertain=match.ambiguous or position_estimated or track_id is None,
            confirmed=visual is not None and visual.is_vehicle,
        ),
    )


def _missed_contact(
    position: Position, ctx: ImageContext, branch: TrackBranch, rules: LevelRules
) -> ContactFinding:
    """Karede olduğu halde tespit edilmemiş track: tipi bilinmez, risk yalnızca hareketten."""
    motion = branch.motions[position.track_id]
    dist_base = distance_m(position.location, ctx.base)
    decision = base_level(
        None,
        dist_base,
        motion.trend,
        registered=True,
        loiter_minutes_near_base=_loiter_minutes(motion, rules),
        circling_path_m=_circling_path_m(motion, rules),
        rules=rules,
    )
    return ContactFinding(
        kind="missed",
        label=None,
        effective_label=None,
        confidence=None,
        bbox=None,
        location=latlon(position.location),
        position_estimated=position.estimated,
        distance_to_base_m=dist_base,
        track_id=position.track_id,
        motion=motion,
        base_level=decision.level,
        final_level=decision.level,
        level_reasons=["kaçırılmış temas: karede ama tespit edilmedi", *decision.reasons],
        certainty="likely",
    )


def build_contacts(
    ctx: ImageContext,
    matches: Matches,
    branch: TrackBranch,
    history: Mapping[str, list[LabelObservation]],
    visuals: Visuals,
    rules: RiskRules,
) -> Contacts:
    """Saf: her eşleşme ve kaçırılmış track bir temas; temel seviye kurallarla."""
    detected = [
        _detection_contact(
            m,
            ctx,
            branch,
            matches.estimated,
            history,
            visuals.get(bbox(m.located.detection)),
            rules,
        )
        for m in matches.matches
    ]
    missed = [_missed_contact(p, ctx, branch, rules.levels) for p in matches.missed]
    return Contacts(tuple(detected + missed))


# --- raporlar --------------------------------------------------------------------------


def evaluate_reports(
    ctx: ImageContext,
    contacts: Contacts,
    claims: list[ClaimRecord],
    visuals: Visuals,
    *,
    repo: DataRepository,
    verifier: VisualVerifier | None,
    rules: ReportRules,
) -> ClaimEvaluations:
    """Depo ve VLM: iddialar çekim anındaki temaslara bağlanıp karşılaştırılır (ADR-0002).

    Renk ya da yük için önceden bakılmamış bir kutu gerekirse burada, en fazla bir kez
    sorulur. Rapor saatindeki track konumu yalnızca rapor saatine kadarki kayıttan okunur.
    """
    looked: dict[BBox, VisualFinding | None] = dict(visuals)

    def look(box: BBox) -> VisualFinding | None:
        if box not in looked:
            looked[box] = verifier.inspect(ctx.image, box) if verifier else None
        return looked[box]

    def position_at(track_id: str, at: time) -> GeoPoint | None:
        """Track'in `at` anındaki ya da en fazla bir adım önceki konumu."""
        since = from_minutes(to_minutes(at) - TRACK_STEP_MINUTES)
        history = repo.track_history(track_id, until=at, since=since)
        return history[-1].location if history else None

    # Kaçırılmış temasın kutusu yok: rengi ve yükü görsel olarak doğrulanamaz.
    boxes = {c.track_id: c.bbox for c in contacts.contacts if c.track_id and c.bbox}
    evaluations = evaluate_claims(
        claims,
        [
            ContactView(
                track_id=c.track_id,
                label=VehicleClass(c.effective_label) if c.effective_label else None,
                location=GeoPoint(c.location.lat, c.location.lon),
                motion=c.motion,
            )
            for c in contacts.contacts
        ],
        image_center=ctx.image.corners.center,
        image_zone=ctx.zone,
        now=ctx.now,
        rules=rules,
        position_at=position_at,
        observe=lambda track_id: look(boxes[track_id]) if track_id in boxes else None,
        in_frame=lambda point: in_footprint(ctx.image, point),
    )
    return ClaimEvaluations(tuple(evaluations), tuple(_finding(e) for e in evaluations), looked)


def _finding(e: ClaimEvaluation) -> ReportFinding:
    return ReportFinding(
        claim_id=e.record.claim_id,
        report_time=format_hhmm(e.record.report.time),
        source=e.record.report.source.value,
        text=e.record.report.text,
        claim_type=e.record.claim.claim_type,
        track_id=e.track_id,
        verdict=e.verdict,
        certainty=e.certainty,
        effect=e.effect,
        time_check=e.time_check,
        reasoning=e.reasoning,
    )


def apply_reports(contacts: Contacts, reports: ClaimEvaluations) -> Contacts:
    """Saf: görsel bulguları temaslara yazar ve rapor etkilerini seviyelerine uygular."""
    return Contacts(
        tuple(
            _apply_report_effects(
                c.model_copy(update={"visual": reports.visuals.get(c.bbox)}) if c.bbox else c,
                reports.evaluations,
            )
            for c in contacts.contacts
        )
    )


def _apply_report_effects(
    contact: ContactFinding, evaluations: tuple[ClaimEvaluation, ...]
) -> ContactFinding:
    """Rapor etkilerini temasın seviyesine uygular; riski artıran etki düşüreni ezer.

    Çelişen rapor seviyeyi değiştirmez (görev tanımı s2: tespit esas alınır), ama aynı temas
    hakkındaki başka bir raporun riski düşürmesini engeller.
    """
    linked = [e for e in evaluations if contact.track_id and e.track_id == contact.track_id]
    if not linked:
        return contact
    level = contact.final_level
    reasons = list(contact.level_reasons)
    contradicted = any(e.verdict == "contradicts" for e in linked)
    if contradicted:
        reasons.append("rapor tespitle çelişiyor; tespit esas alındı")
    raised = any(e.effect == "raises" for e in linked)
    if raised:
        level = LEVELS[min(LEVELS.index(level) + 1, len(LEVELS) - 1)]
        reasons.append("tehdit uyarısı")
    verified_friend = False
    if not raised and not contradicted and any(e.effect == "lowers" for e in linked):
        level, verified_friend = "low", True
        reasons.append("doğrulanmış dost (resmi rapor)")
    return contact.model_copy(
        update={"final_level": level, "level_reasons": reasons, "verified_friend": verified_friend}
    )


# --- karar ve brief --------------------------------------------------------------------


def assess_risk(contacts: Contacts) -> RiskResult:
    """Saf: görüntünün seviyesi, temaslarının en yükseği."""
    cs = contacts.contacts
    return RiskResult(highest([c.final_level for c in cs]), cs, _riskiest(cs))


def decide_level(
    router: LLMRouter | None,
    ctx: ImageContext,
    risk: RiskResult,
    reports: ClaimEvaluations,
    *,
    timeout_s: float,
    max_tokens: int,
) -> FinalDecision:
    """LLM: seviyeyi gerekçesiyle en fazla ±1 kademe ayarlar (ADR-0002).

    LLM yapılandırılmamışsa ya da cevap alınamazsa kuralların sonucu olduğu gibi kalır.
    """

    def fallback(reason: str) -> FinalDecision:
        return FinalDecision(risk.level, risk.contacts, risk.riskiest, None, None, reason)

    if router is None:
        return fallback("LLM yapılandırılmadı")
    try:
        decision = decide(
            router,
            image_id=ctx.image.image_id,
            zone=ctx.zone,
            at=ctx.at,
            contacts=list(risk.contacts),
            findings=list(reports.findings),
            timeout_s=timeout_s,
            max_tokens=max_tokens,
        )
    except DecisionUnavailableError as exc:
        return fallback(str(exc))
    contacts = tuple(decision.contacts)
    return FinalDecision(
        level=highest([c.final_level for c in contacts]),
        contacts=contacts,
        riskiest=_riskiest(contacts),
        assessment=decision.assessment,
        model=decision.model,
        fallback_reason=None,
        accepted=decision.accepted,
        rejected=decision.rejected,
    )


def compose_brief(
    ctx: ImageContext, decision: FinalDecision, reports: ClaimEvaluations, detector_version: str
) -> Brief:
    """Saf: son seviye, önerilen eylem, bulgular, metin ve kaynaklarla Brief."""
    contacts, findings = list(decision.contacts), list(reports.findings)
    riskiest = decision.riskiest
    action = recommended_action(
        decision.level, zone=ctx.zone, contact=riskiest.track_id if riskiest else None
    )
    return Brief(
        image_id=ctx.image.image_id,
        zone=ctx.zone,
        capture_time=ctx.at,
        risk_level=decision.level,
        recommended_action=action,
        is_fallback=decision.model is None,
        fallback_reason=decision.fallback_reason,
        model=decision.model,
        contacts=contacts,
        report_findings=findings,
        text=brief_text(
            ctx.image.image_id,
            ctx.zone,
            ctx.at,
            decision.level,
            contacts,
            findings,
            action,
            decision.assessment,
            automatic=decision.model is None,
        ),
        sources=sources(detector_version, contacts, findings),
    )
