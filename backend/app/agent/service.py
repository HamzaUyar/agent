"""Değerlendirme servisi: bir görüntüyü çekim anı itibarıyla uçtan uca değerlendirir.

Adımları sabit sırayla çalıştırır ve her adımı bir `StepEvent` olarak yayar; son
olay yapılandırılmış Brief'i taşır. Çekim anından sonraki veri okunmaz (ADR-0001).
"""

import logging
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import time

from app.agent.decision import DecisionUnavailableError, decide
from app.core.rules import RiskRules, default_rules
from app.data_package import TRACK_STEP_MINUTES, format_hhmm, from_minutes, to_minutes
from app.db.repositories import DataRepository
from app.formatting import km, mps
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
    StepEvent,
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

BRIEF_STEP = "brief"
# Aynı anda en fazla bu kadar görsel doğrulama; gateway de 4 eşzamanlı istek kabul ediyor.
VISUAL_WORKERS = 4
# Aday track sınırına eklenen pay: eşleşme düzlem yaklaşımıyla, kareye uzaklık haversine'le
# ölçülüyor; eşik sınırındaki bir track iki ölçü arasındaki küçük fark yüzünden kaçmasın.
CANDIDATE_SLACK_M = 1.0

LEVEL_TR = {"low": "DÜŞÜK", "medium": "ORTA", "high": "YÜKSEK", "critical": "KRİTİK"}
TREND_TR = {
    "approaching": "üsse yaklaşıyor",
    "receding": "üsten uzaklaşıyor",
    "stationary": "yerinde duruyor",
    "passing": "üsse yaklaşmadan geçiyor",
    "unknown": "hareket eğilimi belirsiz",
}
CARGO_TR = {"loaded": "yüklü", "empty": "boş"}


class ImageNotFoundError(LookupError):
    """Görüntü veri setinde yok; konumu ve saati bilinmediği için değerlendirilemez."""


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


def _latlon(p: GeoPoint) -> LatLon:
    return LatLon(lat=p.lat, lon=p.lon)


def _certainty(*, weak: bool, uncertain: bool, confirmed: bool = False) -> Certainty:
    """Zayıf tespit, VLM onu araç olarak doğruladıysa "olası"ya çıkar."""
    if weak and not confirmed:
        return "weak"
    return "likely" if uncertain or weak else "certain"


def _bbox(d: Detection) -> BBox:
    return (d.x, d.y, d.w, d.h)


class EvaluationService:
    def __init__(
        self,
        repo: DataRepository,
        detector: Detector,
        rules: RiskRules | None = None,
        *,
        router: LLMRouter | None = None,
        brief_timeout_s: float | None = None,
        verifier: VisualVerifier | None = None,
    ) -> None:
        self._repo = repo
        self._detector = detector
        self._verifier = verifier
        self._rules = rules or default_rules()
        self._router = router
        self._brief_timeout_s = brief_timeout_s or self._rules.brief.timeout_s

    @property
    def repository(self) -> DataRepository:
        return self._repo

    def run(self, image_id: str) -> Brief:
        """Bütün adımları çalıştırıp Brief'i döndürür."""
        for event in self.evaluate(image_id):
            if event.name == BRIEF_STEP:
                return Brief.model_validate(event.data)
        raise RuntimeError("Değerlendirme brief üretmeden bitti")

    def require_image(self, image_id: str) -> ImageMeta:
        image = self._repo.get_image(image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        return image

    def evaluate(self, image_id: str) -> Iterator[StepEvent]:
        image = self.require_image(image_id)
        base = self._repo.base().location
        now = image.capture_time
        zone = nearest_zone(image.corners.center, self._repo.zones()).name
        step = 0

        def emit(name: str, summary: str, **data: object) -> StepEvent:
            nonlocal step
            step += 1
            return StepEvent(step_no=step, name=name, summary=summary, data=data)

        yield emit(
            "goruntu",
            f"{image.width_px}×{image.height_px} px · {format_hhmm(now)} · {zone}",
            image_id=image.image_id,
            zone=zone,
            capture_time=format_hhmm(now),
            corners=[_latlon(p).model_dump() for p in image.corners.as_ring()[:4]],
        )

        # Kol B tespiti beklemez: karedeki track'lerin hareketi tespitle aynı anda hesaplanır.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.track_branch, image)
            detected = self._detector.detect(image)
            branch = pending.result()
        usable = self._usable(detected)
        ignored = len(detected) - len(usable)
        yield emit(
            "tespit",
            f"{len(usable)} araç tespit edildi"
            + (f" ({ignored} düşük güvenli kutu yok sayıldı)" if ignored else ""),
            detections=[
                {
                    "label": d.label.value,
                    "confidence": d.confidence,
                    "bbox": [d.x, d.y, d.w, d.h],
                    "weak": self._is_weak(d),
                }
                for d in usable
            ],
            ignored=ignored,
        )

        located = self._locate(image, usable)
        yield emit(
            "konum",
            "Kutu merkezleri köşe koordinatlarından konuma çevrildi",
            locations=[_latlon(item.location).model_dump() for item in located],
        )

        # Görsel doğrulama yalnızca gerekince ve her kutu için en fazla bir kez yapılır.
        visuals: dict[BBox, VisualFinding | None] = {}

        def look(box: BBox) -> VisualFinding | None:
            if box not in visuals:
                visuals[box] = self._verifier.inspect(image, box) if self._verifier else None
            return visuals[box]

        matches = self._match(image, located, branch.positions)
        positions = branch.positions
        assigned = {m.track.track_id for m in matches if m.track}
        missed = [
            p for p in positions if p.track_id not in assigned and in_footprint(image, p.location)
        ]
        claims = self._repo.claims_until(now)
        if self._verifier is not None:
            self._inspect_all(image, matches, missed, claims, visuals)
        unconfirmed = [
            m.track.track_id
            for m in matches
            if m.track
            and self._is_weak(m.located.detection)
            and (v := visuals.get(_bbox(m.located.detection))) is not None
            and not v.is_vehicle
        ]
        estimated = {p.track_id for p in positions if p.estimated}
        yield emit(
            "eslesme",
            _match_summary(matches, missed),
            matches=[
                {
                    "bbox": list(_bbox(m.located.detection)),
                    "track_id": m.track.track_id if m.track else None,
                    "distance_m": m.track.distance_m if m.track else None,
                    "ambiguous": m.ambiguous,
                    "second": (
                        {"track_id": m.second.track_id, "distance_m": m.second.distance_m}
                        if m.second
                        else None
                    ),
                }
                for m in matches
            ],
            missed=[p.track_id for p in missed],
            estimated_positions=sorted(estimated),
            visually_unconfirmed=unconfirmed,
        )

        history = self._label_history(image)
        contacts = [
            self._detection_contact(
                m, base, branch, estimated, history, visuals.get(_bbox(m.located.detection))
            )
            for m in matches
        ] + [self._missed_contact(p, base, branch) for p in missed]
        yield emit(
            "hareket",
            "; ".join(
                f"{c.track_id}: {TREND_TR[c.motion.trend]}, üsse {km(c.motion.distance_to_base_m)}"
                for c in contacts
                if c.motion and c.track_id
            )
            or "hareket kaydı olan temas yok",
            motions={
                c.track_id: c.motion.model_dump() for c in contacts if c.motion and c.track_id
            },
            # Temel seviyenin girdileri: tip ve mesafe Kol A'dan, eğilim ve duraklama Kol B'den.
            contacts=[
                {
                    "kind": c.kind,
                    "track_id": c.track_id,
                    "label": c.effective_label,
                    "distance_to_base_m": c.distance_to_base_m,
                    "trend": c.motion.trend if c.motion else None,
                    "base_level": c.base_level,
                    "reasons": c.level_reasons,
                    "certainty": c.certainty,
                }
                for c in contacts
            ],
        )

        # Kaçırılmış temasın kutusu yok: rengi ve yükü görsel olarak doğrulanamaz.
        boxes = {c.track_id: c.bbox for c in contacts if c.track_id and c.bbox}
        evaluations = evaluate_claims(
            claims,
            [
                ContactView(
                    track_id=c.track_id,
                    label=VehicleClass(c.effective_label) if c.effective_label else None,
                    location=GeoPoint(c.location.lat, c.location.lon),
                    motion=c.motion,
                )
                for c in contacts
            ],
            image_center=image.corners.center,
            image_zone=zone,
            now=now,
            rules=self._rules.reports,
            position_at=self._position_at,
            observe=lambda track_id: look(boxes[track_id]) if track_id in boxes else None,
            in_frame=lambda point: in_footprint(image, point),
        )
        contacts = [
            _apply_report_effects(
                c.model_copy(update={"visual": visuals.get(c.bbox)}) if c.bbox else c,
                evaluations,
            )
            for c in contacts
        ]
        findings = [_finding(e) for e in evaluations]
        yield emit(
            "raporlar",
            _reports_summary(findings),
            findings=[f.model_dump() for f in findings],
            visual_checks=[
                {"bbox": list(box), **(v.model_dump() if v else {"result": None})}
                for box, v in visuals.items()
            ],
        )

        level = highest([c.final_level for c in contacts])
        riskiest = max(contacts, key=lambda c: LEVELS.index(c.final_level), default=None)
        yield emit(
            "risk",
            f"Görüntü seviyesi: {LEVEL_TR[level]}",
            level=level,
            contacts=[
                {
                    "kind": c.kind,
                    "track_id": c.track_id,
                    "base_level": c.base_level,
                    "final_level": c.final_level,
                    "reasons": c.level_reasons,
                }
                for c in contacts
            ],
        )

        assessment: str | None = None
        model: str | None = None
        fallback_reason: str | None = None
        accepted = rejected = 0
        if self._router is None:
            fallback_reason = "LLM yapılandırılmadı"
        else:
            try:
                decision = decide(
                    self._router,
                    image_id=image.image_id,
                    zone=zone,
                    at=format_hhmm(now),
                    contacts=contacts,
                    findings=findings,
                    timeout_s=self._brief_timeout_s,
                    max_tokens=self._rules.brief.max_tokens,
                )
            except DecisionUnavailableError as exc:
                fallback_reason = str(exc)
            else:
                contacts, assessment, model = decision.contacts, decision.assessment, decision.model
                accepted, rejected = decision.accepted, decision.rejected
                level = highest([c.final_level for c in contacts])
                riskiest = max(contacts, key=lambda c: LEVELS.index(c.final_level), default=None)
        yield emit(
            "karar",
            f"{model}: {accepted} ayar kabul, {rejected} red"
            if model
            else f"Otomatik özet: {fallback_reason}",
            model=model,
            fallback_reason=fallback_reason,
            contacts=[
                {
                    "track_id": c.track_id,
                    "final_level": c.final_level,
                    "adjustment_reason": c.adjustment_reason,
                    "adjustment_rejected": c.adjustment_rejected,
                }
                for c in contacts
            ],
        )

        action = recommended_action(
            level, zone=zone, contact=riskiest.track_id if riskiest else None
        )
        brief = Brief(
            image_id=image.image_id,
            zone=zone,
            capture_time=format_hhmm(now),
            risk_level=level,
            recommended_action=action,
            is_fallback=model is None,
            fallback_reason=fallback_reason,
            model=model,
            contacts=contacts,
            report_findings=findings,
            text=_brief_text(
                image.image_id,
                zone,
                format_hhmm(now),
                level,
                contacts,
                findings,
                action,
                assessment,
                automatic=model is None,
            ),
            sources=_sources(self._detector.version, contacts, findings),
        )
        yield emit(BRIEF_STEP, f"Risk: {LEVEL_TR[level]} · {action}", **brief.model_dump())

    # --- adımlar ----------------------------------------------------------------

    def _usable(self, detected: list[Detection]) -> list[Detection]:
        """Güveni `min_confidence`'ın altındaki kutular yok sayılır."""
        return [d for d in detected if d.confidence >= self._rules.detection.min_confidence]

    def _is_weak(self, detection: Detection) -> bool:
        """Zayıf tespit: yalnızca bir track'le eşleşirse temas sayılır."""
        return detection.confidence < self._rules.detection.strong_confidence

    def _position_at(self, track_id: str, at: time) -> GeoPoint | None:
        """Track'in `at` anındaki ya da en fazla bir adım önceki konumu."""
        since = from_minutes(to_minutes(at) - TRACK_STEP_MINUTES)
        history = self._repo.track_history(track_id, until=at, since=since)
        return history[-1].location if history else None

    @staticmethod
    def _locate(image: ImageMeta, detections: list[Detection]) -> list[LocatedDetection]:
        return [LocatedDetection(d, pixel_to_geo(image, *d.center_px)) for d in detections]

    def _inspect_all(
        self,
        image: ImageMeta,
        matches: list[MatchResult],
        missed: list[Position],
        claims: list[ClaimRecord],
        visuals: dict[BBox, VisualFinding | None],
    ) -> None:
        """Bütün görsel doğrulama tek bir paralel dalgada; sonuçlar `visuals`'a yazılır.

        - Track'le eşleşen zayıf tespit: araç derse kesinlik "olası"ya çıkar. "Araç değil"
          cevabı kutuyu düşürmez: track orada bir araç olduğunu zaten gösteriyor.
        - Renk ya da yük belirten iddianın bağlanacağı kutu: bağlama ucuz bir hesap, rapor
          değerlendirmesiyle aynı kuralla önceden yapılır; değerlendirme yalnızca sonucu okur.
        Her VLM çağrısı ~10 sn; sırayla sormak çağrı sayısıyla çarpılırdı.
        """
        assert self._verifier is not None
        weak = [
            _bbox(m.located.detection)
            for m in matches
            if m.track and self._is_weak(m.located.detection)
        ]
        tracked_boxes = {m.track.track_id: _bbox(m.located.detection) for m in matches if m.track}
        views = [
            ContactView(m.track.track_id if m.track else None, None, m.located.location)
            for m in matches
        ] + [ContactView(p.track_id, None, p.location) for p in missed]
        claimed = visual_track_ids(
            claims,
            views,
            image_center=image.corners.center,
            now=image.capture_time,
            rules=self._rules.reports,
        )
        boxes = list(
            dict.fromkeys(weak + [tracked_boxes[t] for t in sorted(claimed) if t in tracked_boxes])
        )
        if not boxes:
            return
        verifier = self._verifier
        with ThreadPoolExecutor(max_workers=VISUAL_WORKERS) as pool:
            found = pool.map(lambda box: verifier.inspect(image, box), boxes)
            visuals.update(zip(boxes, found, strict=True))

    def track_branch(self, image: ImageMeta) -> TrackBranch:
        """Kol B: aday track'lerin çekim anı konumu ve hareket analizi, tespitten bağımsız."""
        base = self._repo.base().location
        positions = self._candidate_positions(image)
        motions = {
            p.track_id: self._motion(p.track_id, base, image.capture_time) for p in positions
        }
        return TrackBranch(positions, motions)

    def _candidate_positions(self, image: ImageMeta) -> list[Position]:
        """Çekim anında karenin içinde ya da kareye eşleşme eşiği kadar yakın track'ler."""
        now = image.capture_time
        since = from_minutes(to_minutes(now) - 2 * TRACK_STEP_MINUTES)
        reach = self._rules.matching.threshold_m + CANDIDATE_SLACK_M
        return [
            p
            for p in positions_at(self._repo.track_points_between(since, now), now)
            if distance_to_footprint_m(image, p.location) <= reach
        ]

    def _match(
        self, image: ImageMeta, located: list[LocatedDetection], positions: list[Position]
    ) -> list[MatchResult]:
        """Tespitleri aday track'lerin çekim anı konumlarıyla birebir eşler.

        Güçlü ve zayıf tespitler tek atamada eşlenir; eşitlik bozma güçlü tespiti öne alır.
        Eşleşmeyen zayıf tespit düşer.
        """
        points = [TrackPoint(p.track_id, image.capture_time, p.location) for p in positions]
        rules = self._rules.matching
        matches = match_detections(located, points, rules.threshold_m, rules.score_tiebreak)
        return [m for m in matches if m.track is not None or not self._is_weak(m.located.detection)]

    def _label_history(self, image: ImageMeta) -> dict[str, list[LabelObservation]]:
        """Çekim anına kadarki karelerde her track'in hangi sınıfla tespit edildiği."""
        now = image.capture_time
        history: dict[str, list[LabelObservation]] = defaultdict(list)
        frames = [m for m in self._repo.list_images() if m.capture_time <= now]
        for frame in frames:
            try:
                detected = self._detector.detect(frame)
            except ImageFileMissingError:
                # Önceki karenin dosyası yoksa yalnızca tip geçmişi eksik kalır.
                logger.warning("Tip geçmişi: %s atlandı, dosya yok", frame.image_id)
                continue
            usable = self._usable(detected)
            located = self._locate(frame, usable)
            matches = self._match(frame, located, self._candidate_positions(frame))
            for m in matches:
                if m.track:
                    history[m.track.track_id].append(
                        LabelObservation(
                            image_id=frame.image_id, label=m.located.detection.label.value
                        )
                    )
        return history

    def _motion(self, track_id: str, base: GeoPoint, now: time) -> MotionFinding:
        rules = self._rules
        since = from_minutes(to_minutes(now) - rules.motion.history_minutes)
        history = self._repo.track_history(track_id, until=now, since=since)
        m = analyze_motion(history, base, now, self._repo.zones(), rules.trend, rules.motion)
        ongoing = m.stops[-1] if m.stops and m.stops[-1].end == history[-1].time else None
        return MotionFinding(
            distance_to_base_m=m.distance_to_base_m,
            distance_to_base_30min_ago_m=m.distance_to_base_window_ago_m,
            distance_to_base_60min_ago_m=m.distance_to_base_hour_ago_m,
            trend=m.trend,
            route=[_latlon(p) for p in m.route],
            total_distance_m=m.total_distance_m,
            avg_speed_mps=m.avg_speed_mps,
            recent_speed_mps=m.recent_speed_mps,
            heading_deg=m.heading_deg,
            stops=[
                StopFinding(
                    start=format_hhmm(s.start),
                    end=format_hhmm(s.end),
                    minutes=s.minutes,
                    location=_latlon(s.location),
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

    def _loiter_minutes(self, motion: MotionFinding | None) -> int:
        """Üsse `loiter_m`'den yakın en uzun duraklamanın süresi."""
        if motion is None:
            return 0
        near = [
            s.minutes for s in motion.stops if s.distance_to_base_m < self._rules.levels.loiter_m
        ]
        return max(near, default=0)

    def _circling_path_m(self, motion: MotionFinding | None) -> float:
        """Üssün çevresinde dar bir mesafe bandında kalarak gidilen yol; dolaşmıyorsa 0.

        Görev tanımı s3: araçlar üs çevresinde dolaşır. Üsse mesafesi kayıt boyunca
        `circle_band_m` içinde kalan, `loiter_m`'den yakın ve en az `circle_min_extent_m`
        genişliğinde bir yay çizen araç dolaşıyordur; yerinde gidip gelen yerel trafik değil.
        """
        t = self._rules.levels
        if (
            motion is None
            or motion.base_distance_max_m >= t.loiter_m
            or motion.base_distance_max_m - motion.base_distance_min_m > t.circle_band_m
            or motion.extent_m < t.circle_min_extent_m
        ):
            return 0.0
        return motion.total_distance_m

    def _detection_contact(
        self,
        match: MatchResult,
        base: GeoPoint,
        branch: TrackBranch,
        estimated: set[str],
        history: dict[str, list[LabelObservation]],
        visual: VisualFinding | None,
    ) -> ContactFinding:
        det = match.located.detection
        location = match.located.location
        dist_base = distance_m(location, base)
        track_id = match.track.track_id if match.track else None

        motion = branch.motions[track_id] if track_id else None
        observed = history.get(track_id, []) if track_id else []
        labels = {VehicleClass(o.label) for o in observed} | {det.label}
        effective = riskier_type(sorted(labels, key=str))
        decision = base_level(
            effective,
            dist_base,
            motion.trend if motion else None,
            registered=track_id is not None,
            loiter_minutes_near_base=self._loiter_minutes(motion),
            circling_path_m=self._circling_path_m(motion),
            rules=self._rules.levels,
        )
        position_estimated = track_id in estimated
        return ContactFinding(
            kind="matched" if track_id else "unregistered",
            label=det.label.value,
            effective_label=effective.value,
            confidence=det.confidence,
            bbox=(det.x, det.y, det.w, det.h),
            location=_latlon(location),
            is_weak=self._is_weak(det),
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
                weak=self._is_weak(det),
                uncertain=match.ambiguous or position_estimated or track_id is None,
                confirmed=visual is not None and visual.is_vehicle,
            ),
        )

    def _missed_contact(
        self, position: Position, base: GeoPoint, branch: TrackBranch
    ) -> ContactFinding:
        """Karede olduğu halde tespit edilmemiş track: tipi bilinmez, risk yalnızca hareketten."""
        motion = branch.motions[position.track_id]
        dist_base = distance_m(position.location, base)
        decision = base_level(
            None,
            dist_base,
            motion.trend,
            registered=True,
            loiter_minutes_near_base=self._loiter_minutes(motion),
            circling_path_m=self._circling_path_m(motion),
            rules=self._rules.levels,
        )
        return ContactFinding(
            kind="missed",
            label=None,
            effective_label=None,
            confidence=None,
            bbox=None,
            location=_latlon(position.location),
            position_estimated=position.estimated,
            distance_to_base_m=dist_base,
            track_id=position.track_id,
            motion=motion,
            base_level=decision.level,
            final_level=decision.level,
            level_reasons=["kaçırılmış temas: karede ama tespit edilmedi", *decision.reasons],
            certainty="likely",
        )


def _apply_report_effects(
    contact: ContactFinding, evaluations: list[ClaimEvaluation]
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


VERDICT_TR = {
    "consistent": "tutarlı",
    "contradicts": "çelişkili",
    "unverifiable": "doğrulanamaz",
    "irrelevant": "ilgisiz",
}


TIME_TR = {
    "ok": "saat tutuyor",
    "mismatch": "araç rapor saatinde başka yerdeydi",
    "unknown": "saat bilinmiyor",
}


def _time_tag(f: ReportFinding) -> str:
    """Bir temasa bağlanmış iddianın rapor saatindeki konum kontrolü."""
    return f", {TIME_TR[f.time_check]}" if f.track_id else ""


def _reports_summary(findings: list[ReportFinding]) -> str:
    if not findings:
        return "İlgili rapor yok"
    counts: dict[str, int] = defaultdict(int)
    for f in findings:
        counts[VERDICT_TR[f.verdict]] += 1
    return f"{len(findings)} iddia: " + ", ".join(f"{n} {v}" for v, n in counts.items())


def _match_summary(matches: list[MatchResult], missed: list[Position]) -> str:
    parts = []
    for m in matches:
        if m.track is None:
            parts.append("track yok (kayıt dışı)")
        else:
            note = " · belirsiz" if m.ambiguous else ""
            parts.append(f"{m.track.track_id} · {m.track.distance_m:.0f} m{note}")
    parts += [f"{p.track_id} karede ama tespit yok (kaçırılmış)" for p in missed]
    return ", ".join(parts) or "eşleşecek tespit yok"


def _contact_notes(c: ContactFinding) -> list[str]:
    notes = []
    if c.is_weak:
        if c.visual is None:
            notes.append("zayıf tespit")
        elif c.visual.is_vehicle:
            notes.append("zayıf tespit, görsel olarak araç doğrulandı")
        else:
            notes.append("zayıf tespit, araç görsel olarak seçilemedi (hareket kaydı var)")
    if c.visual:
        looks: list[str] = [c.visual.color] if c.visual.color else []
        looks += [CARGO_TR[c.visual.cargo]] if c.visual.cargo else []
        notes.append(f"görsel: {', '.join(looks) or 'renk ve yük seçilemedi'}")
    if c.is_ambiguous and c.second_candidate:
        notes.append(f"belirsiz eşleşme, diğer aday {c.second_candidate.track_id}")
    if c.position_estimated:
        notes.append("konum kestirildi")
    if c.type_conflict:
        seen = ", ".join(f"{o.image_id}: {o.label}" for o in c.observed_labels)
        notes.append(f"tip çelişkisi ({seen}); {c.effective_label} kabul edildi")
    return notes


def _movement_text(m: MotionFinding) -> str:
    parts = [TREND_TR[m.trend]]
    if m.distance_to_base_30min_ago_m is not None:
        hour = (
            f"1 saat önce {km(m.distance_to_base_60min_ago_m)}, "
            if m.distance_to_base_60min_ago_m is not None
            else ""
        )
        parts.append(
            f"üsse uzaklık {hour}30 dk önce {km(m.distance_to_base_30min_ago_m)}, "
            f"şimdi {km(m.distance_to_base_m)}"
        )
    parts.append(f"son 30 dk {mps(m.recent_speed_mps)}, 2 saatlik ortalama {mps(m.avg_speed_mps)}")
    if m.heading_deg is not None:
        parts.append(f"yön {m.heading_deg:.0f}°")
    if m.stops:
        parts.append(
            "duraklamalar: " + ", ".join(f"{st.start} ({st.minutes} dk)" for st in m.stops)
        )
    return ", ".join(parts)


def _brief_text(
    image_id: str,
    zone: str,
    at: str,
    level: RiskLevel,
    contacts: list[ContactFinding],
    findings: list[ReportFinding],
    action: str,
    assessment: str | None,
    *,
    automatic: bool,
) -> str:
    """Başlık, bulgular ve eylem kodla; LLM varsa değerlendirme paragrafı ondan gelir."""
    header = f"{image_id} · {zone} · {at} · Risk: {LEVEL_TR[level]}"
    lines = [f"{header} (otomatik özet)" if automatic else header]
    if assessment:
        lines.append(f"Değerlendirme: {assessment}")
    if not contacts:
        lines.append("Karede temas yok.")
    for c in contacts:
        who = c.track_id or "kayıt dışı temas"
        label = c.effective_label or "tipi bilinmiyor"
        movement = _movement_text(c.motion) if c.motion else "hareket geçmişi yok"
        notes = _contact_notes(c)
        if c.adjustment_reason:
            notes.append(f"LLM ayarı: {c.adjustment_reason.rstrip('. ')}")
        lines.append(
            f"- {who} ({label}): üsse {km(c.distance_to_base_m)}, {movement}; "
            f"seviye {LEVEL_TR[c.final_level]} ({'; '.join(c.level_reasons)})."
            + (f" Not: {'; '.join(notes)}." if notes else "")
        )
    if findings:
        lines.append("Raporlar:")
        lines += [
            f"- {f.report_time} ({'resmi' if f.source == 'official' else 'üçüncü taraf'}): "
            f"{VERDICT_TR[f.verdict]}{_time_tag(f)}; {f.reasoning}."
            for f in findings
        ]
    lines.append(f"Önerilen eylem: {action}")
    return "\n".join(lines)


def _sources(
    detector: str, contacts: list[ContactFinding], findings: list[ReportFinding]
) -> list[str]:
    sources = [f"tespit: {detector}", "konum: köşe koordinatları"]
    sources += [f"hareket: {c.track_id}" for c in contacts if c.track_id]
    sources += sorted({f"görsel: {c.visual.model}" for c in contacts if c.visual})
    sources += sorted({f"rapor: {f.report_time}" for f in findings})
    return sources
