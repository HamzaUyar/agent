"""Değerlendirme kaydı, önbellek ve yeniden hesaplama (ticket 09).

Test noktası, değerlendirme servisini saran koşucu; kayıt deposu bellekte çalışır.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.agent.runner import EvaluationRunner, InMemoryRunStore
from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.llm.client import LLMRouter, load_model_config
from app.schemas.domain import Detection, ImageMeta, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
CONFIG = load_model_config()
PRIMARY = CONFIG.models[CONFIG.tasks["reasoning"][0]]


class CountingDetector:
    version = "fake-1"

    def __init__(self) -> None:
        self.calls = 0

    def detect(self, image: ImageMeta) -> list[Detection]:
        self.calls += 1
        return [TRUCK] if image.image_id == "img_000860" else []


class SwitchableLLM:
    """İlk çağrılarda hata, `working` açılınca geçerli cevap döndürür."""

    def __init__(self, working: bool = True) -> None:
        self.working = working
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int,
        extra_body: object = None,
    ) -> BaseModel:
        self.calls += 1
        if not self.working:
            raise RuntimeError("503")
        return schema.model_validate(
            {"adjustments": [], "assessment": "T0122 üsse yaklaşan kamyon."}
        )


def setup(
    llm: SwitchableLLM | None = None,
) -> tuple[EvaluationRunner, InMemoryRunStore, CountingDetector]:
    detector = CountingDetector()
    router = LLMRouter(CONFIG, {PRIMARY.provider: llm}) if llm else None
    service = EvaluationService(InMemoryRepository(PACKAGE), detector, router=router)
    store = InMemoryRunStore()
    return EvaluationRunner(service, store, detector_version=detector.version), store, detector


def events(runner: EvaluationRunner, **kwargs: Any) -> list[tuple[str, dict[str, Any]]]:
    return list(runner.stream("img_000860", **kwargs))


def test_first_evaluation_is_recorded_and_streamed() -> None:
    runner, store, _ = setup()

    stream = events(runner)

    kind, run = stream[0]
    assert (kind, run["cached"]) == ("run", False)
    assert [k for k, _ in stream[1:-1]] == ["step"] * 8
    assert stream[-1][0] == "brief"
    stored = store.get(run["run_id"])
    assert stored is not None and stored.status == "done"
    assert stored.brief is not None and stored.brief.risk_level == "critical"
    assert [s.name for s in stored.steps][-1] == "brief"


def test_same_image_again_replays_the_cached_run_without_recomputing() -> None:
    runner, _, detector = setup()
    first = events(runner)
    calls_after_first = detector.calls

    second = events(runner)

    assert second[0][1]["cached"] is True
    assert second[0][1]["run_id"] == first[0][1]["run_id"]
    assert [e for e in second[1:]] == [e for e in first[1:]]
    assert detector.calls == calls_after_first


def test_recompute_starts_a_new_run() -> None:
    runner, _, detector = setup()
    first = events(runner)
    calls_after_first = detector.calls

    again = events(runner, recompute=True)

    assert again[0][1]["cached"] is False
    assert again[0][1]["run_id"] != first[0][1]["run_id"]
    assert detector.calls > calls_after_first


def test_llm_written_brief_is_preferred_over_a_newer_automatic_summary() -> None:
    llm = SwitchableLLM(working=True)
    runner, _, _ = setup(llm)
    good = events(runner)
    llm.working = False
    fallback = events(runner, recompute=True)
    assert fallback[-1][1]["is_fallback"] is True

    cached = events(runner)

    assert cached[0][1]["run_id"] == good[0][1]["run_id"]
    assert cached[-1][1]["is_fallback"] is False


def test_automatic_summary_is_cached_when_nothing_better_exists() -> None:
    runner, _, _ = setup(SwitchableLLM(working=False))
    first = events(runner)

    second = events(runner)

    assert second[0][1] == {**first[0][1], "cached": True}


def test_failed_run_is_not_used_as_cache() -> None:
    runner, store, _ = setup()
    run_id = store.start("img_000860", "fake-1", {})
    store.fail(run_id, "patladı")

    stream = events(runner)

    assert stream[0][1]["cached"] is False


def test_disconnect_mid_stream_marks_the_run_failed() -> None:
    runner, store, _ = setup()
    stream = runner.stream("img_000860")
    _, run = next(stream)
    next(stream)
    stream.close()

    stored = store.get(run["run_id"])
    assert stored is not None and stored.status == "failed"


def test_stored_run_can_be_read_with_all_steps() -> None:
    runner, store, _ = setup()
    run_id = events(runner)[0][1]["run_id"]

    stored = store.get(run_id)

    assert stored is not None
    assert [s.step_no for s in stored.steps] == list(range(1, 10))
    assert store.get("yok") is None


def test_runs_from_another_detector_are_not_replayed() -> None:
    llm = SwitchableLLM()
    mock_runner, store, _ = setup(llm)
    events(mock_runner)  # sahte tespitle, LLM brief'li kayıt

    # Model moduna geçildi; yeni kayıt otomatik özete düşse bile eski tespit dönmemeli.
    llm.working = False
    model_detector = CountingDetector()
    model_detector.version = "yolo:best.pt"
    router = LLMRouter(CONFIG, {PRIMARY.provider: llm})
    service = EvaluationService(InMemoryRepository(PACKAGE), model_detector, router=router)
    model_runner = EvaluationRunner(service, store, detector_version=model_detector.version)

    first = events(model_runner)
    replay = events(model_runner)

    assert first[0][1]["cached"] is False
    assert replay[0][1]["cached"] is True
    assert replay[0][1]["run_id"] == first[0][1]["run_id"]
