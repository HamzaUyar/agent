"""POST /evaluations → değerlendirme adımlarını SSE ile akıtır."""

import json
from collections.abc import Iterator
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.agent.chat import ChatAgent
from app.agent.runner import EvaluationRunner
from app.agent.service import EvaluationService, ImageNotFoundError
from app.agent.tools import ChatTools
from app.api.data import RepoDep
from app.db.models import ChatRecorder, RunRecorder
from app.db.repositories import DataRepository
from app.db.session import connect
from app.llm.client import LLMRouter
from app.pipelines.detection import Detector
from app.schemas.api import Brief, ChatRequest, EvaluationRecord, EvaluationRequest

router = APIRouter(tags=["evaluations"])

# no-transform: Next.js proxy'si SSE'yi gzip'leyip olayları sona kadar biriktirmesin.
SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


def get_detector(request: Request) -> Detector:
    detector: Detector = request.app.state.detector
    return detector


DetectorDep = Annotated[Detector, Depends(get_detector)]


def _service(request: Request, repo: DataRepository, detector: Detector) -> EvaluationService:
    state = request.app.state
    return EvaluationService(repo, detector, router=state.router, verifier=state.verifier)


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stream(
    service: EvaluationService, image_id: str, detector_version: str, recompute: bool
) -> Iterator[str]:
    """Kaydederek ya da önbellekten akıtır. Senkron üreteç; Starlette thread havuzunda yürütür."""
    with connect() as conn:
        runner = EvaluationRunner(service, RunRecorder(conn), detector_version=detector_version)
        # İç üreteç bağlantı kapanmadan kapatılsın ki kopmada kayıt 'failed' işaretlenebilsin.
        with closing(runner.stream(image_id, recompute=recompute)) as events:
            for kind, payload in events:
                yield _sse(kind, payload)


@router.post(
    "/evaluations",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Adım olayları, son olay brief"},
        404: {"description": "Görüntü veri setinde yok"},
    },
)
def start_evaluation(
    payload: EvaluationRequest, request: Request, repo: RepoDep, detector: DetectorDep
) -> StreamingResponse:
    """Görüntüyü değerlendirir; `run`, `step` olayları ve son `brief` olayı akar.

    Aynı görüntünün başarılı bir değerlendirmesi varsa önbellekten tekrar oynatılır
    (`run.cached = true`); `recompute = true` yeni değerlendirme başlatır.
    """
    service = _service(request, repo, detector)
    try:
        service.require_image(payload.image_id)
    except ImageNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Görüntü veri setinde yok: {payload.image_id}"
        ) from exc
    return StreamingResponse(
        _stream(service, payload.image_id, detector.version, payload.recompute),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/evaluations/{run_id}",
    response_model=EvaluationRecord,
    responses={404: {"description": "Değerlendirme bulunamadı"}},
)
def read_evaluation(run_id: str) -> EvaluationRecord:
    """Kayıtlı bir değerlendirmeyi bütün adımları ve brief'iyle döndürür."""
    with connect() as conn:
        run = RunRecorder(conn).get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Değerlendirme bulunamadı: {run_id}")
    return EvaluationRecord(
        run_id=run.run_id,
        image_id=run.image_id,
        status=run.status,
        steps=run.steps,
        brief=run.brief,
        error=run.error,
    )


def _chat_stream(
    service: EvaluationService,
    run_id: str,
    image_id: str,
    brief: Brief,
    question: str,
    llm: LLMRouter,
    detector_version: str,
) -> Iterator[str]:
    with connect() as conn:
        runner = EvaluationRunner(service, RunRecorder(conn), detector_version=detector_version)

        def evaluate_image(other_id: str) -> Brief:
            final: Brief | None = None
            with closing(runner.stream(other_id)) as events:
                for kind, payload in events:
                    if kind == "brief":
                        final = Brief.model_validate(payload)
            if final is None:
                raise ValueError(f"{other_id} değerlendirilemedi")
            return final

        image = service.require_image(image_id)
        tools = ChatTools(service.repository, image, brief, evaluate_image=evaluate_image)
        agent = ChatAgent(llm, tools, brief, ChatRecorder(conn), run_id=run_id)
        for kind, payload in agent.ask(question):
            yield _sse(kind, payload)


@router.post(
    "/evaluations/{run_id}/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "`tool` olayları, son olay `answer`",
        },
        404: {"description": "Tamamlanmış değerlendirme bulunamadı"},
    },
)
def chat(
    run_id: str, payload: ChatRequest, request: Request, repo: RepoDep, detector: DetectorDep
) -> StreamingResponse:
    """Değerlendirme hakkında takip sorusu; agent salt okuma araçlarıyla cevaplar."""
    with connect() as conn:
        run = RunRecorder(conn).get(run_id)
    if run is None or run.brief is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tamamlanmış değerlendirme yok: {run_id}")
    service = _service(request, repo, detector)
    return StreamingResponse(
        _chat_stream(
            service,
            run.run_id,
            run.image_id,
            run.brief,
            payload.message,
            request.app.state.router,
            detector.version,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
