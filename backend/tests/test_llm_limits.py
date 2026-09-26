"""Organizatör gateway'i: takım limitleri, 429'da bekleme ve istek biçimi (görev tanımı s4-s11).

Saat, uyku ve OpenAI istemcisi sahtedir; ağ çağrısı yapılmaz.
"""

import threading
import time as clock
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.client import (
    MIN_OPENAI_COMPAT_TOKENS,
    LimitedProvider,
    LLMRouter,
    OpenAICompatibleProvider,
    build_router,
    load_model_config,
)
from app.llm.limits import BudgetExceededError, GatewayLimits

CONFIG = load_model_config()


class Answer(BaseModel):
    ok: bool


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def rate_limit_error() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://gateway/v1/chat/completions")
    return openai.RateLimitError(
        "rate limited", response=httpx.Response(429, request=request), body=None
    )


class ScriptedProvider:
    """Sırayla verilen cevapları döndürür; istisna verilirse fırlatır."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def complete_json(self, *args: Any, **kwargs: Any) -> BaseModel:
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Answer(ok=reply)

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


def completion(
    content: str | None, finish_reason: str = "stop", usage: tuple[int, int] = (100, 20)
) -> Any:
    message = SimpleNamespace(content=content, tool_calls=None, reasoning_content="düşünce")
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]),
    )


class FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.response


def provider_with(response: Any, **kwargs: Any) -> tuple[OpenAICompatibleProvider, FakeCompletions]:
    provider = OpenAICompatibleProvider("sk-test", "https://gateway/v1", **kwargs)
    completions = FakeCompletions(response)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))  # type: ignore[assignment]
    return provider, completions


# --- Limitler ---------------------------------------------------------------------------


def test_61st_request_in_a_minute_waits_for_the_window() -> None:
    fake = FakeClock()
    limits = GatewayLimits(per_minute=60, clock=fake, sleep=fake.sleep)

    for _ in range(60):
        with limits.slot():
            pass
    assert fake.sleeps == []

    with limits.slot():
        pass
    assert fake.sleeps == [60.0]


def test_fifth_concurrent_request_waits_for_a_free_slot() -> None:
    limits = GatewayLimits(max_concurrent=4)
    inside = threading.Semaphore(0)
    release = threading.Event()
    peak = 0
    active = 0
    lock = threading.Lock()

    def request() -> None:
        nonlocal peak, active
        with limits.slot():
            with lock:
                active += 1
                peak = max(peak, active)
            inside.release()
            release.wait(timeout=2)
            with lock:
                active -= 1

    threads = [threading.Thread(target=request) for _ in range(5)]
    for t in threads:
        t.start()
    for _ in range(4):
        assert inside.acquire(timeout=2)
    assert not inside.acquire(timeout=0.1)  # beşinci istek yer bekliyor
    release.set()
    for t in threads:
        t.join(timeout=2)

    assert peak == 4


def test_budget_exceeded_stops_new_requests() -> None:
    limits = GatewayLimits(budget_usd=1.0, price_input_per_mtok=1.0, price_output_per_mtok=4.0)
    limits.record_usage(600_000, 100_000)  # 0,6 + 0,4 = 1,0 USD

    assert limits.spent_usd == pytest.approx(1.0)
    with pytest.raises(BudgetExceededError), limits.slot():
        pass


def test_without_prices_the_budget_never_blocks() -> None:
    limits = GatewayLimits(budget_usd=15.0)
    limits.record_usage(10_000_000, 10_000_000)

    with limits.slot():
        pass
    assert (limits.input_tokens, limits.output_tokens) == (10_000_000, 10_000_000)


# --- 429 ve yedek model -----------------------------------------------------------------


def test_429_retries_the_same_model_with_exponential_backoff() -> None:
    fake = FakeClock()
    inner = ScriptedProvider(rate_limit_error(), rate_limit_error(), True)
    provider = LimitedProvider(inner, GatewayLimits(), backoff_s=2.0, sleep=fake.sleep)

    result = provider.complete_json("glm-5.3-flash", "s", "u", Answer, 4096)

    assert result == Answer(ok=True)
    assert inner.calls == 3
    assert fake.sleeps == [2.0, 4.0]


def test_persistent_429_falls_through_to_the_next_model_in_the_chain() -> None:
    fake = FakeClock()
    gateway = LimitedProvider(
        ScriptedProvider(*[rate_limit_error()] * 5), GatewayLimits(), sleep=fake.sleep
    )
    evren = ScriptedProvider(True)
    router = LLMRouter(CONFIG, {"glm": gateway, "evren": evren})

    result, model = router.complete_json("reasoning", "s", "u", Answer)

    assert result == Answer(ok=True)
    assert model == "evren/glm-5.3"
    assert len(fake.sleeps) == 4


def test_exhausted_budget_falls_through_to_the_next_model() -> None:
    limits = GatewayLimits(budget_usd=0.0)
    gateway_inner = ScriptedProvider(True)
    router = LLMRouter(
        CONFIG, {"glm": LimitedProvider(gateway_inner, limits), "evren": ScriptedProvider(True)}
    )

    _, model = router.complete_json("reasoning", "s", "u", Answer)

    assert model == "evren/glm-5.3"
    assert gateway_inner.calls == 0


# --- İstek ve cevap biçimi --------------------------------------------------------------


def test_request_follows_the_gateway_rules() -> None:
    provider, completions = provider_with(completion('{"ok": true}'))
    entry = CONFIG.models["glm_org"]

    provider.complete_json(
        entry.model_id, "s", "u", Answer, 256, entry.extra_body, image=b"\xff\xd8jpeg"
    )

    [request] = completions.requests
    assert request["model"] == "glm-5.3-flash"
    assert request["max_tokens"] >= 1000  # düşünme de bu bütçeden harcar (s10)
    assert request["max_tokens"] == MIN_OPENAI_COMPAT_TOKENS
    assert request["extra_body"] == {"reasoning_effort": "low"}
    assert "thinking" not in request and "thinking" not in request["extra_body"]
    image_part = request["messages"][1]["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_answer_is_read_from_content_not_reasoning_content() -> None:
    usage: list[tuple[int, int]] = []
    provider, _ = provider_with(
        completion('{"ok": true}', usage=(700, 300)), on_usage=lambda i, o: usage.append((i, o))
    )

    assert provider.complete_json("m", "s", "u", Answer, 4096) == Answer(ok=True)
    assert usage == [(700, 300)]


def test_answer_cut_at_max_tokens_is_rejected() -> None:
    provider, _ = provider_with(completion('{"ok": tr', finish_reason="length"))

    with pytest.raises(ValueError, match="kesildi"):
        provider.complete_json("m", "s", "u", Answer, 4096)


def test_chat_answer_cut_at_max_tokens_is_rejected() -> None:
    provider, _ = provider_with(completion("Yarım kalan cev", finish_reason="length"))

    with pytest.raises(ValueError, match="kesildi"):
        provider.chat("m", [{"role": "user", "content": "?"}], [], 4096)


def test_gateway_provider_is_limited_and_sdk_retries_are_off() -> None:
    settings = Settings(_env_file=None, glm_api_key="sk-test")  # type: ignore[call-arg]

    router = build_router(settings)

    gateway = router._providers["glm"]
    assert isinstance(gateway, LimitedProvider)
    assert gateway.is_available()
    assert gateway._inner._max_retries == 0  # type: ignore[attr-defined]
    assert settings.glm_api_base.endswith("railway.app/v1")


def test_limited_provider_releases_its_slot_while_backing_off() -> None:
    limits = GatewayLimits(max_concurrent=1)
    waited_with_free_slot: list[bool] = []

    def sleep(_: float) -> None:
        got = limits._slots.acquire(blocking=False)
        waited_with_free_slot.append(got)
        if got:
            limits._slots.release()

    provider = LimitedProvider(ScriptedProvider(rate_limit_error(), True), limits, sleep=sleep)
    started = clock.monotonic()

    provider.complete_json("m", "s", "u", Answer, 4096)

    assert waited_with_free_slot == [True]
    assert clock.monotonic() - started < 1
