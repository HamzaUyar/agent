"""Değerlendirme koşucusu: kayıt, önbellekten tekrar oynatma ve yeniden hesaplama.

Aynı görüntü tekrar istendiğinde son başarılı değerlendirme, adımlarıyla birlikte
tekrar oynatılır; LLM ve tespit yeniden çalışmaz. LLM'in yazdığı bir brief, daha yeni
bir otomatik özete tercih edilir (ör. demo sırasında 503 yüzünden düşmüş bir özet).
"""

import itertools
import logging
from collections.abc import Generator, Mapping
from typing import Any, Literal, Protocol
from uuid import uuid4

from app.agent.service import BRIEF_STEP, EvaluationService
from app.schemas.api import Brief, StepEvent
from app.schemas.runs import StoredRun

logger = logging.getLogger(__name__)

EventKind = Literal["run", "step", "brief", "error"]
RunEvent = tuple[EventKind, dict[str, Any]]


class RunStore(Protocol):
    def start(self, image_id: str, detector_version: str, models: Mapping[str, Any]) -> str: ...

    def add_step(self, run_id: str, event: StepEvent) -> None: ...

    def finish(self, run_id: str, brief: Brief) -> None: ...

    def fail(self, run_id: str, error: str) -> None: ...

    def get(self, run_id: str) -> StoredRun | None: ...

    def latest_cached(self, image_id: str, detector_version: str) -> StoredRun | None:
        """Aynı tespit bileşeniyle yapılmış son başarılı değerlendirme; LLM'in yazdığı brief
        otomatik özete tercih edilir."""
        ...


class InMemoryRunStore:
    """Testler için kayıt deposu."""

    def __init__(self) -> None:
        self._runs: dict[str, StoredRun] = {}
        self._order: dict[str, int] = {}
        self._versions: dict[str, str] = {}
        self._counter = itertools.count()

    def start(self, image_id: str, detector_version: str, models: Mapping[str, Any]) -> str:
        run_id = str(uuid4())
        self._runs[run_id] = StoredRun(run_id, image_id, "running")
        self._order[run_id] = next(self._counter)
        self._versions[run_id] = detector_version
        return run_id

    def add_step(self, run_id: str, event: StepEvent) -> None:
        self._runs[run_id].steps.append(event)

    def finish(self, run_id: str, brief: Brief) -> None:
        run = self._runs[run_id]
        run.status, run.brief = "done", brief

    def fail(self, run_id: str, error: str) -> None:
        run = self._runs[run_id]
        run.status, run.error = "failed", error

    def get(self, run_id: str) -> StoredRun | None:
        return self._runs.get(run_id)

    def latest_cached(self, image_id: str, detector_version: str) -> StoredRun | None:
        done = [
            r
            for r in self._runs.values()
            if r.image_id == image_id
            and self._versions[r.run_id] == detector_version
            and r.status == "done"
            and r.brief is not None
        ]
        done.sort(key=lambda r: self._order[r.run_id], reverse=True)
        written = [r for r in done if r.brief is not None and not r.brief.is_fallback]
        candidates = written or done
        return candidates[0] if candidates else None


def _payload(event: StepEvent) -> RunEvent:
    if event.name == BRIEF_STEP:
        return "brief", Brief.model_validate(event.data).model_dump(mode="json")
    return "step", event.model_dump(mode="json")


class EvaluationRunner:
    def __init__(
        self, service: EvaluationService, store: RunStore, *, detector_version: str
    ) -> None:
        self._service = service
        self._store = store
        self._detector_version = detector_version

    def stream(self, image_id: str, *, recompute: bool = False) -> Generator[RunEvent, None, None]:
        """`run`, ardından `step` olayları ve son `brief` olayı; hata olursa `error`."""
        self._service.require_image(image_id)
        if (
            not recompute
            and (cached := self._store.latest_cached(image_id, self._detector_version)) is not None
        ):
            yield "run", {"run_id": cached.run_id, "image_id": image_id, "cached": True}
            for step in cached.steps:
                yield _payload(step)
            return

        run_id = self._store.start(image_id, self._detector_version, {})
        finished = False
        try:
            yield "run", {"run_id": run_id, "image_id": image_id, "cached": False}
            for event in self._service.evaluate(image_id):
                self._store.add_step(run_id, event)
                if event.name == BRIEF_STEP:
                    self._store.finish(run_id, Brief.model_validate(event.data))
                    finished = True
                yield _payload(event)
        except GeneratorExit:
            # İstemci akış bitmeden bağlantıyı kapattı; kayıt 'running' durumunda kalmasın.
            if not finished:
                self._store.fail(run_id, "istemci bağlantıyı kapattı")
            raise
        except Exception as exc:
            logger.exception("Değerlendirme başarısız: %s", run_id)
            self._store.fail(run_id, repr(exc))
            yield "error", {"run_id": run_id, "message": "Değerlendirme başarısız"}
