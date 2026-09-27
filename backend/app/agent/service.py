"""Değerlendirme servisi: bir görüntüyü çekim anı itibarıyla uçtan uca değerlendirir.

Aşamaları (`app/agent/stages.py`) sabit sırayla çağırır ve her birinin sonucunu bir
`StepEvent` olarak yayar (`app/agent/events.py`); son olay yapılandırılmış Brief'i taşır.
Tespit (Kol A) ve track kolu (Kol B) birbirini beklemez. Çekim anından sonraki veri
okunmaz (ADR-0001).
"""

import itertools
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.agent import events, stages
from app.agent.events import Payload
from app.agent.stages import TrackBranch
from app.core.config import get_settings
from app.core.rules import RiskRules, default_rules
from app.db.repositories import DataRepository
from app.llm.client import LLMRouter
from app.pipelines.detection import Detector
from app.pipelines.vision import VisualVerifier
from app.reports_v2.stage import ReportVerifier
from app.schemas.api import Brief, StepEvent
from app.schemas.domain import ImageMeta

__all__ = ["BRIEF_STEP", "EvaluationService", "ImageNotFoundError", "TrackBranch"]

BRIEF_STEP = "brief"


class ImageNotFoundError(LookupError):
    """Görüntü veri setinde yok; konumu ve saati bilinmediği için değerlendirilemez."""


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
        report_verifier: ReportVerifier | None = None,
        images_dir: Path | None = None,
        report_cache: Path | None = None,
    ) -> None:
        self._repo = repo
        self._detector = detector
        self._verifier = verifier
        self._report_verifier = report_verifier or ReportVerifier(
            repo,
            detector,
            router,
            images_dir or get_settings().resolved_data_dir / "images",
            report_cache,
        )
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

    def track_branch(self, image: ImageMeta) -> TrackBranch:
        """Kol B: aday track'lerin çekim anı konumu ve hareket analizi, tespitten bağımsız."""
        return stages.track_branch(self._repo, image, self._rules)

    def evaluate(self, image_id: str) -> Iterator[StepEvent]:
        """Aşamaları sırayla çalıştırır; her aşamadan sonra adımını yayar."""
        repo, rules = self._repo, self._rules
        ctx = stages.image_context(repo, self.require_image(image_id))
        image = ctx.image
        step_no = itertools.count(1)

        def emit(name: str, payload: Payload) -> StepEvent:
            summary, data = payload
            return StepEvent(step_no=next(step_no), name=name, summary=summary, data=data)

        yield emit("goruntu", events.image(ctx))

        # Kol B tespiti beklemez: karedeki track'lerin hareketi tespitle aynı anda hesaplanır.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.track_branch, image)
            detections = stages.detect(self._detector, image, rules.detection)
            branch = pending.result()
        yield emit("tespit", events.detections(detections, rules.detection))

        located = stages.locate(image, detections.usable)
        yield emit("konum", events.locations(located))

        matches = stages.match_contacts(image, located, branch, rules)
        claims = repo.claims_until(ctx.now)
        visuals = stages.inspect_visuals(self._verifier, image, matches, rules)
        unconfirmed = stages.visually_unconfirmed(matches, visuals, rules.detection)
        yield emit("eslesme", events.matches(matches, unconfirmed))

        history = stages.label_history(repo, self._detector, image, rules)
        contacts = stages.build_contacts(ctx, matches, branch, history, visuals, rules)
        yield emit("hareket", events.motions(contacts))

        reports = stages.evaluate_reports(ctx, claims, visuals, self._report_verifier)
        contacts = stages.apply_reports(contacts, reports)
        yield emit("raporlar", events.reports(reports))

        risk = stages.assess_risk(contacts)
        yield emit("risk", events.risk(risk))

        decision = stages.decide_level(
            self._router,
            ctx,
            risk,
            reports,
            levels=rules.levels,
            zone_names=[z.name for z in repo.zones()],
            timeout_s=self._brief_timeout_s,
            max_tokens=rules.brief.max_tokens,
        )
        yield emit("karar", events.decision(decision))

        brief = stages.compose_brief(ctx, decision, reports, self._detector.version)
        yield emit(BRIEF_STEP, events.brief(brief))
