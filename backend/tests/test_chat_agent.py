"""Sohbet agent'ı: araç çağırma döngüsü, yedek model ve kayıt (ticket 10).

LLM sahte sağlayıcıdan senaryolu cevaplar verir; araçlar gerçek kodla çalışır.
"""

import json
from pathlib import Path
from typing import Any

from app.agent.chat import ChatAgent, InMemoryChatStore
from app.agent.service import EvaluationService
from app.agent.tools import ChatTools
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.llm.client import ChatTurn, LLMRouter, ToolCall, load_model_config
from app.schemas.domain import Detection, ImageMeta, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
CONFIG = load_model_config()
CHAIN = [CONFIG.models[name] for name in CONFIG.tasks["chat"]]
PRIMARY, FALLBACK = CHAIN[0], CHAIN[1]


class FakeDetector:
    version = "test"

    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK] if image.image_id == "img_000860" else []


class ScriptedLLM:
    """Her `chat` çağrısında sıradaki cevabı (ya da hatayı) döndürür.

    `cleaned` verilirse cevap temizleme çağrısına (`complete_json`) bu metinle cevap verir;
    verilmezse temizleme çağrısı başarısız olur.
    """

    def __init__(self, script: list[ChatTurn | Exception], cleaned: str | None = None) -> None:
        self.script = list(script)
        self.cleaned = cleaned
        self.seen: list[list[dict[str, Any]]] = []
        self.cleaning_inputs: list[str] = []

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: type[Any],
        max_tokens: int,
        extra_body: object = None,
    ) -> Any:
        self.cleaning_inputs.append(user)
        if self.cleaned is None:
            raise RuntimeError("temizleme yok")
        return schema.model_validate({"cevap": self.cleaned})

    def is_available(self) -> bool:
        return True

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        extra_body: object = None,
    ) -> ChatTurn:
        self.seen.append(messages)
        turn = self.script.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def call(name: str, **args: Any) -> ChatTurn:
    return ChatTurn(
        content=None, tool_calls=[ToolCall(id=f"c-{name}", name=name, arguments=json.dumps(args))]
    )


def answer(text: str) -> ChatTurn:
    return ChatTurn(content=text, tool_calls=[])


def agent(
    primary: ScriptedLLM, fallback: ScriptedLLM | None = None
) -> tuple[ChatAgent, InMemoryChatStore]:
    repo = InMemoryRepository(read_package(FIXTURE))
    service = EvaluationService(repo, FakeDetector())
    brief = service.run("img_000860")
    image = repo.get_image("img_000860")
    assert image is not None
    providers: dict[str, Any] = {e.provider: ScriptedLLM([]) for e in CHAIN}
    for p in providers.values():
        p.is_available = lambda: False  # type: ignore[method-assign]
    providers[PRIMARY.provider] = primary
    if fallback:
        providers[FALLBACK.provider] = fallback
    store = InMemoryChatStore()
    tools = ChatTools(repo, image, brief, evaluate_image=service.run)
    return ChatAgent(LLMRouter(CONFIG, providers), tools, brief, store, run_id="run-1"), store


def test_agent_calls_a_tool_and_answers() -> None:
    llm = ScriptedLLM(
        [call("temas_gecmisi", track_id="T0122"), answer("T0122 12:10'dan beri yaklaşıyor.")]
    )
    chat, store = agent(llm)

    events = list(chat.ask("T0122 nereden geldi?"))

    kinds = [k for k, _ in events]
    assert kinds == ["tool", "answer"]
    tool_event = events[0][1]
    assert tool_event["name"] == "temas_gecmisi" and tool_event["arguments"] == {
        "track_id": "T0122"
    }
    assert events[1][1]["content"] == "T0122 12:10'dan beri yaklaşıyor."
    # Araç sonucu ikinci LLM çağrısında modele verildi.
    assert any(m["role"] == "tool" and "12:10" in m["content"] for m in llm.seen[1])


def test_conversation_is_stored_and_used_as_context_next_time() -> None:
    llm = ScriptedLLM([answer("Kritik."), answer("Evet, T0122.")])
    chat, store = agent(llm)
    list(chat.ask("Durum ne?"))

    list(chat.ask("En riskli temas hangisi?"))

    assert [(m.role, m.content) for m in store.history("run-1")] == [
        ("user", "Durum ne?"),
        ("assistant", "Kritik."),
        ("user", "En riskli temas hangisi?"),
        ("assistant", "Evet, T0122."),
    ]
    assert {"role": "user", "content": "Durum ne?"} in llm.seen[1]


def test_active_brief_is_given_to_the_model_as_context() -> None:
    llm = ScriptedLLM([answer("Tamam.")])
    chat, _ = agent(llm)

    list(chat.ask("Özetle"))

    context = " ".join(m["content"] for m in llm.seen[0] if m["role"] == "system")
    assert "img_000860" in context and "T0122" in context


def test_failing_primary_falls_back_to_the_next_model() -> None:
    chat, _ = agent(ScriptedLLM([RuntimeError("503")]), ScriptedLLM([answer("Yedekten cevap.")]))

    events = list(chat.ask("Durum?"))

    assert events[-1] == (
        "answer",
        {"content": "Yedekten cevap.", "model": f"{FALLBACK.provider}/{FALLBACK.model_id}"},
    )


def test_all_models_failing_gives_an_error_event_and_stores_nothing_for_the_assistant() -> None:
    chat, store = agent(ScriptedLLM([RuntimeError("503")]), ScriptedLLM([RuntimeError("503")]))

    events = list(chat.ask("Durum?"))

    assert events[-1][0] == "error"
    assert [m.role for m in store.history("run-1")] == ["user"]


def test_endless_tool_calls_stop_at_the_step_limit() -> None:
    llm = ScriptedLLM([call("temas_gecmisi", track_id="T0122")] * 10)
    chat, _ = agent(llm)

    events = list(chat.ask("Döngü"))

    assert [k for k, _ in events].count("tool") == ChatAgent.MAX_STEPS
    assert events[-1][0] == "answer" and "adım sınırı" in events[-1][1]["content"]


def test_reasoning_outside_the_answer_tags_is_not_shown_or_stored() -> None:
    leaked = (
        "Summarize: T0122 came from the northeast. Answer in Turkish.\n"
        "<cevap>**Sonuç:** T0122 kuzeydoğudan geldi.</cevap>"
    )
    chat, store = agent(ScriptedLLM([answer(leaked)]))

    events = list(chat.ask("T0122 nereden geldi?"))

    assert events[-1][1]["content"] == "**Sonuç:** T0122 kuzeydoğudan geldi."
    assert store.history("run-1")[-1].content == "**Sonuç:** T0122 kuzeydoğudan geldi."


def test_answer_without_tags_is_used_as_is() -> None:
    chat, _ = agent(ScriptedLLM([answer("Kritik durum.")]))

    assert list(chat.ask("Durum?"))[-1][1]["content"] == "Kritik durum."


LEAKED = "The user asks X. I should answer in Turkish.**Sonuç:** Kritik."


def test_leaked_reasoning_without_tags_is_cleaned_by_a_structured_call() -> None:
    """Yedek model (EVREN glm-5.3, düşünme kapalı) düşüncesini cevaba yazabiliyor."""
    fallback = ScriptedLLM([answer(LEAKED)], cleaned="**Sonuç:** Kritik.")
    chat, store = agent(ScriptedLLM([RuntimeError("503")]), fallback)

    events = list(chat.ask("Durum?"))

    assert events[-1][1]["content"] == "**Sonuç:** Kritik."
    assert fallback.cleaning_inputs == [LEAKED]


def test_when_cleaning_fails_the_answer_starts_at_the_result_marker() -> None:
    chat, _ = agent(ScriptedLLM([RuntimeError("503")]), ScriptedLLM([answer(LEAKED)]))

    assert list(chat.ask("Durum?"))[-1][1]["content"] == "**Sonuç:** Kritik."


def test_gateway_answer_is_not_sent_to_a_second_cleaning_call() -> None:
    """glm-5.3-flash düşüncesini `reasoning_content`'te ayrı verir (s11): cevap temizdir."""
    assert PRIMARY.separate_reasoning
    llm = ScriptedLLM([answer("**Sonuç:** Kritik.")], cleaned="başka")
    chat, _ = agent(llm)

    assert list(chat.ask("Durum?"))[-1][1]["content"] == "**Sonuç:** Kritik."
    assert llm.cleaning_inputs == []


def test_fallback_keeps_a_turkish_answer_that_mentions_the_result_marker_later() -> None:
    text = "Hayır. T0122 başka karede yok. Sonuç: yalnızca img_000860."
    chat, _ = agent(ScriptedLLM([answer(text)]))

    assert list(chat.ask("Başka karede var mı?"))[-1][1]["content"] == text
