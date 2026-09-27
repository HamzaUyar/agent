"""Değerlendirme aşamaları: her biri küçük, dondurulmuş girdi ve çıktılarla çalışır.

Saf aşamalar yalnızca argümanlarından hesaplar. Yan etkili olanlar (depo okuması, tespit
modeli, VLM, LLM) bunu imzalarında açıkça taşır: `repo`, `detector`, `verifier` ya da
`router` alırlar. Hiçbir aşama çekim anından sonraki veriyi okumaz (ADR-0001): depo
sorguları çekim anıyla (ya da ondan önceki rapor saatiyle) sınırlıdır.

Sıra: `image_context` → Kol A `detect` ∥ Kol B `track_branch` → `locate` →
`match_contacts` → `inspect_visuals` → `label_history` → `build_contacts` →
`evaluate_reports` (reports_v2) →
`apply_reports` → `assess_risk` → `decide_level` → `compose_brief`.
"""

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import time

from app.agent.brief_text import brief_text, sources
from app.agent.decision import DecisionUnavailableError, decide
from app.core.rules import DetectionRules, LevelRules, MatchingRules, RiskRules
from app.data_package import TRACK_STEP_MINUTES, format_hhmm, from_minutes, to_minutes
from app.db.repositories import DataRepository
from app.formatting import num
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
from app.pipelines.risk import (
    LEVELS,
    LevelDecision,
    engine_basis,
    engine_decision,
    highest,
    recommended_action,
    unregistered_decision,
)
from app.pipelines.vision import BBox, VisualVerifier
from app.reports_v2.stage import ClaimEvaluation, ReportVerifier
from app.risk_engine import EngineConfig, Point, TrackRisk, run_track, to_local
from app.schemas.api import (
    AttentionFinding,
    Brief,
    Certainty,
    ContactFinding,
    LabelObservation,
    LatLon,
    LevelPoint,
    MotionFinding,
    ReportFinding,
    RoutePoint,
    StopFinding,
    TrackCandidate,
    Verdict,
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
    Zone,
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
    histories: dict[str, list[Point]] = field(default_factory=dict)
    """Risk motoru için her adayın çekim anına kadarki gözlemleri (üs merkezli düzlemde)."""


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
    attention: tuple[AttentionFinding, ...] = ()
    """LLM'in dikkat maddeleri ve kodun doğrulaması."""
    summary: str | None = None
    summary_rejected: str | None = None


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
    """Depo: aday track'lerin çekim anı konumu, hareket analizi ve risk motoru girdisi.

    Tespitten bağımsızdır; her track'in geçmişi bir kez okunur.
    """
    base = repo.base().location
    now = image.capture_time
    minutes = max(rules.motion.history_minutes, int(rules.engine.evaluation.history_minutes))
    since = from_minutes(max(to_minutes(now) - minutes, 0))
    positions = candidate_positions(repo, image, rules.matching)
    motions: dict[str, MotionFinding] = {}
    histories: dict[str, list[Point]] = {}
    for p in positions:
        history = repo.track_history(p.track_id, until=now, since=since)
        motions[p.track_id] = motion_finding(history, base, now, repo.zones(), rules)
        histories[p.track_id] = engine_points(history, base, now, rules.engine)
    return TrackBranch(positions, motions, histories)


def engine_points(
    history: list[TrackPoint], base: GeoPoint, now: time, cfg: EngineConfig
) -> list[Point]:
    """Saf: risk motorunun geçmiş penceresindeki gözlemler (üs merkezli düzlemde)."""
    start = to_minutes(now) - cfg.evaluation.history_minutes
    return [
        Point(to_minutes(p.time), *to_local(p.location, base))
        for p in history
        if to_minutes(p.time) >= start
    ]


def track_risk(
    branch: TrackBranch,
    track_id: str,
    label: str | None,
    confidence: float | None,
    cfg: EngineConfig,
) -> TrackRisk | None:
    """Saf: track'in ilk gözleminden çekim anına kadar her adımda risk motoru."""
    points = branch.histories.get(track_id)
    if not points:
        return None
    return run_track(track_id, points, label, confidence, cfg)


@dataclass(frozen=True)
class EngineView:
    """Temasa eklenen motor alanları: kural kodu, öncelik skoru, etiketler, seviye geçmişi."""

    code: str | None = None
    score: float | None = None
    tags: list[str] = field(default_factory=list)
    history: list[LevelPoint] = field(default_factory=list)


def engine_view(risk: TrackRisk | None) -> EngineView:
    if risk is None:
        return EngineView()
    cur = risk.current
    return EngineView(
        code=cur.code,
        score=round(cur.score, 2),
        tags=cur.tags,
        history=[
            LevelPoint(
                time=format_hhmm(from_minutes(int(s.t))),
                level=LEVELS[s.level],
                code=s.code,
                score=round(s.score, 2),
            )
            for s in risk.steps
        ],
    )


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
    history: list[TrackPoint], base: GeoPoint, now: time, zones: list[Zone], rules: RiskRules
) -> MotionFinding:
    """Saf: track'in çekim anına kadarki geçmişinden hareket özeti."""
    start = to_minutes(now) - rules.motion.history_minutes
    history = [p for p in history if to_minutes(p.time) >= start]
    m = analyze_motion(history, base, now, zones, rules.trend, rules.motion)
    ongoing = m.stops[-1] if m.stops and m.stops[-1].end == history[-1].time else None
    return MotionFinding(
        distance_to_base_m=m.distance_to_base_m,
        distance_to_base_30min_ago_m=m.distance_to_base_window_ago_m,
        distance_to_base_60min_ago_m=m.distance_to_base_hour_ago_m,
        trend=m.trend,
        route=[
            RoutePoint(lat=p.location.lat, lon=p.location.lon, time=format_hhmm(p.time))
            for p in m.route
        ],
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
    rules: RiskRules,
) -> Visuals:
    """VLM: track'le eşleşen zayıf tespitler tek bir paralel dalgada; doğrulayıcı yoksa boş.

    Araç derse kesinlik "olası"ya çıkar. "Araç değil" cevabı kutuyu düşürmez: track orada bir
    araç olduğunu zaten gösteriyor. Her VLM çağrısı ~10 sn; sırayla sormak çağrı sayısıyla
    çarpılırdı. Rapor iddialarının rengi ve yükü rapor doğrulamasında (reports_v2) tartılır.
    """
    if verifier is None:
        return {}
    boxes = list(
        dict.fromkeys(
            bbox(m.located.detection)
            for m in matches.matches
            if m.track and is_weak(m.located.detection, rules.detection)
        )
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
    risk = (
        track_risk(branch, track_id, effective.value, det.confidence, rules.engine)
        if track_id
        else None
    )
    decision: LevelDecision = (
        engine_decision(risk.current, dist_base)
        if risk is not None
        else unregistered_decision(dist_base, rules.engine)
    )
    view = engine_view(risk)
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
        level_basis=engine_basis(decision, motion, rules.levels),
        level_code=view.code,
        priority_score=view.score,
        level_tags=view.tags,
        level_history=view.history,
        certainty=_certainty(
            weak=weak,
            uncertain=match.ambiguous or position_estimated or track_id is None,
            confirmed=visual is not None and visual.is_vehicle,
        ),
    )


def _missed_contact(
    position: Position, ctx: ImageContext, branch: TrackBranch, rules: RiskRules
) -> ContactFinding:
    """Karede olduğu halde tespit edilmemiş track: tipi bilinmez, risk yalnızca hareketten."""
    motion = branch.motions[position.track_id]
    dist_base = distance_m(position.location, ctx.base)
    risk = track_risk(branch, position.track_id, None, None, rules.engine)
    decision = (
        engine_decision(risk.current, dist_base)
        if risk is not None
        else unregistered_decision(dist_base, rules.engine)
    )
    view = engine_view(risk)
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
        level_basis=engine_basis(decision, motion, rules.levels, missed=True),
        level_code=view.code,
        priority_score=view.score,
        level_tags=view.tags,
        level_history=view.history,
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
    missed = [_missed_contact(p, ctx, branch, rules) for p in matches.missed]
    return Contacts(tuple(detected + missed))


# --- raporlar --------------------------------------------------------------------------


def evaluate_reports(
    ctx: ImageContext,
    claims: list[ClaimRecord],
    visuals: Visuals,
    verifier: ReportVerifier,
) -> ClaimEvaluations:
    """Rapor doğrulama (app/reports_v2): kanıt dosyası ve bağlam kodla, karar LLM'in, kurallar
    ikinci görüş. Rapor seviyeyi değiştirmez; yalnızca gerekçe ve bayrak üretir."""
    evaluations: list[ClaimEvaluation] = []
    findings: list[ReportFinding] = []
    for v in verifier.verify(ctx.image, ctx.zone, ctx.now, claims):
        detail = v.final.verdict
        # "Kısmen" (ör. araç var, tipi doğrulanamadı) yalan değildir: genel kararda "tutarlı"
        # ve "olası" kesinlikte; ayrıntı `detail_verdict`'te kalır.
        verdict: Verdict = "consistent" if detail == "partial" else detail
        certainty: Certainty = "likely" if detail == "partial" or v.needs_review else "certain"
        notes = []
        # Bilgi notları: karara girmez, operatör aracın ne olabileceğini görür.
        if v.nearby is not None:
            notes.append(
                f"tespit modeli track noktasında araç görmedi; "
                f"{num(v.nearby['track_noktasina_uzaklik_m'])} m ötede "
                f"{v.nearby['tip']} tespiti var (olası aynı araç, karara girmedi)"
            )
        if v.visual is not None:
            notes.append(
                f"tespit modeli görmedi; görsel incelemede {v.visual['tip']} "
                f"(eminlik {v.visual['emin']}, karara girmedi)"
            )
        if v.final.dangerous_reassurance:
            notes.append("TEHLİKELİ GÜVENCE")
        notes += v.final.context_flags
        if v.needs_review:
            notes.append(f"kurallar '{v.rule.verdict}' dedi, operatör incelemeli")
        reasoning = v.final.reasoning + (f" [{'; '.join(notes)}]" if notes else "")
        e = ClaimEvaluation(v.record, v.track_id, verdict, certainty, reasoning)
        evaluations.append(e)
        findings.append(
            ReportFinding(
                claim_id=v.record.claim_id,
                report_time=format_hhmm(v.record.report.time),
                source=v.record.report.source.value,
                text=v.record.report.text,
                claim_type=v.record.claim.claim_type,
                track_id=v.track_id,
                verdict=verdict,
                certainty=certainty,
                effect="none",
                reasoning=reasoning,
                detail_verdict=detail,
                dangerous_reassurance=v.final.dangerous_reassurance,
                context_flags=list(v.final.context_flags),
                needs_review=v.needs_review,
                rule_verdict=v.rule.verdict,
            )
        )
    return ClaimEvaluations(tuple(evaluations), tuple(findings), dict(visuals))


def apply_reports(contacts: Contacts, reports: ClaimEvaluations) -> Contacts:
    """Saf: görsel bulguları temaslara yazar; çelişen rapor gerekçeye not düşer.

    Rapor seviyeyi değiştirmez (görev tanımı s2: tespit esas alınır; doğrulanamayan bilgi
    riski düşüremez). Kimlik iddiası "doğrulanmış dost" yapmaz.
    """
    return Contacts(
        tuple(
            _note_reports(
                c.model_copy(update={"visual": reports.visuals.get(c.bbox)}) if c.bbox else c,
                reports.evaluations,
            )
            for c in contacts.contacts
        )
    )


def _note_reports(
    contact: ContactFinding, evaluations: tuple[ClaimEvaluation, ...]
) -> ContactFinding:
    linked = [e for e in evaluations if contact.track_id and e.track_id == contact.track_id]
    if not any(e.verdict == "contradicts" for e in linked):
        return contact
    reasons = [*contact.level_reasons, "rapor tespitle çelişiyor; tespit esas alındı"]
    return contact.model_copy(update={"level_reasons": reasons})


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
    levels: LevelRules,
    zone_names: Sequence[str],
    timeout_s: float,
    max_tokens: int,
) -> FinalDecision:
    """LLM: dikkat maddeleri önerir, kod her birini veriyle doğrular (ADR-0002).

    Seviye yalnızca doğrulanmış bir nedenle ve en fazla ±1 kademe değişir. LLM
    yapılandırılmamışsa ya da cevap alınamazsa kuralların sonucu olduğu gibi kalır.
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
            levels=levels,
            zone_names=zone_names,
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
        attention=tuple(decision.attention),
        summary=decision.summary,
        summary_rejected=decision.summary_rejected,
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
        attention=list(decision.attention),
        summary=decision.summary,
        summary_rejected=decision.summary_rejected,
    )
