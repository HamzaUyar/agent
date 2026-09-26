"""Sohbet agent'ı: brief'ten sonraki takip sorularını araç çağırarak cevaplar.

Bir soru için en fazla `MAX_STEPS` tur araç çağrılır. Araç çağrıları `tool`, cevap
`answer` olayı olarak yayılır; hiçbir model cevap veremezse `error` yayılır.
Kullanıcı mesajları ve cevaplar kayda geçer.
"""

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.agent.tools import ChatTools
from app.llm.client import LLMRouter, LLMUnavailableError
from app.schemas.api import Brief
from app.schemas.chat import ChatMessage

TASK = "chat"
PROMPT_PATH = Path(__file__).parent / "prompts" / "chat.md"
# Düşünmesi kapalı model iç akıl yürütmesini metne yazabiliyor; operatöre yalnızca
# etiketin içi gider. Etiket yoksa metnin tamamı kullanılır.
ANSWER_TAG = re.compile(r"<cevap>(.*?)</cevap>", re.DOTALL)
RESULT_MARKER = re.compile(r"\*{0,2}Sonuç:")
CLEAN_PROMPT = (
    "Aşağıdaki metin bir modelin operatöre vereceği cevabın taslağı; başında modelin kendi "
    "düşünceleri (çoğunlukla İngilizce) olabilir. Yalnızca operatöre gidecek Türkçe cevabı, "
    "içeriğini değiştirmeden ve biçimini koruyarak cevap alanına yaz. Düşünceleri atla."
)


class CleanAnswer(BaseModel):
    cevap: str = Field(description="Yalnızca operatöre gidecek Türkçe cevap")


ChatEvent = tuple[Literal["tool", "answer", "error"], dict[str, Any]]


class ChatStore(Protocol):
    def history(self, run_id: str) -> list[ChatMessage]: ...

    def append(self, run_id: str, message: ChatMessage) -> None: ...


class InMemoryChatStore:
    def __init__(self) -> None:
        self._messages: dict[str, list[ChatMessage]] = defaultdict(list)

    def history(self, run_id: str) -> list[ChatMessage]:
        return list(self._messages[run_id])

    def append(self, run_id: str, message: ChatMessage) -> None:
        self._messages[run_id].append(message)


def _fallback_answer(raw: str) -> str:
    """Temizleme çağrısı yapılamazsa: etiket, yoksa 'Sonuç:' işareti, yoksa metnin tamamı."""
    tagged = ANSWER_TAG.findall(raw)
    if tagged:
        return str(tagged[-1]).strip()
    marker = RESULT_MARKER.search(raw)
    # Yalnızca işaretten önceki kısım sızmış (İngilizce) bir düşünceye benziyorsa kes;
    # Türkçe bir cevabın ilk cümleleri atılmasın.
    if marker and _looks_like_leaked_reasoning(raw[: marker.start()]):
        return raw[marker.start() :].strip()
    return raw.strip()


TURKISH_LETTERS = frozenset("çğıöşüÇĞİÖŞÜ")


def _looks_like_leaked_reasoning(prefix: str) -> bool:
    return bool(prefix.strip()) and not TURKISH_LETTERS.intersection(prefix)


def _brief_context(brief: Brief) -> str:
    compact = {
        "text": brief.text,
        "contacts": [
            {
                "track_id": c.track_id,
                "kind": c.kind,
                "type": c.effective_label,
                "base_level": c.base_level,
                "final_level": c.final_level,
                "level_reasons": c.level_reasons,
            }
            for c in brief.contacts
        ],
        "reports": [f.model_dump() for f in brief.report_findings],
    }
    return "Aktif değerlendirme:\n" + json.dumps(compact, ensure_ascii=False)


class ChatAgent:
    MAX_STEPS = 6

    def __init__(
        self,
        router: LLMRouter,
        tools: ChatTools,
        brief: Brief,
        store: ChatStore,
        *,
        run_id: str,
    ) -> None:
        self._router = router
        self._tools = tools
        self._brief = brief
        self._store = store
        self._run_id = run_id

    def _clean(self, raw: str, model: str) -> str:
        """Düşünmesi kapalı model akıl yürütmesini metne yazabiliyor; cevabı ondan ayırır.

        Düşüncesini ayrı alanda veren modelin (gateway'deki glm-5.3-flash) cevabı zaten
        temizdir; ikinci bir LLM çağrısı yapılmaz.
        """
        tagged = ANSWER_TAG.findall(raw)
        if tagged:
            return str(tagged[-1]).strip()
        if self._router.separates_reasoning(model):
            return raw.strip()
        try:
            cleaned, _ = self._router.complete_json(TASK, CLEAN_PROMPT, raw, CleanAnswer, 2048)
        except LLMUnavailableError:
            return _fallback_answer(raw)
        return cleaned.cevap.strip() or _fallback_answer(raw)

    def ask(self, question: str) -> Iterator[ChatEvent]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
            {"role": "system", "content": _brief_context(self._brief)},
        ]
        messages += [
            {"role": m.role, "content": m.content}
            for m in self._store.history(self._run_id)
            if m.role in ("user", "assistant")
        ]
        messages.append({"role": "user", "content": question})
        self._store.append(self._run_id, ChatMessage("user", question))

        specs = self._tools.specs()
        for _ in range(self.MAX_STEPS):
            try:
                turn, model = self._router.chat(TASK, messages, specs)
            except LLMUnavailableError:
                yield "error", {"message": "Şu anda cevap verecek model yok; tekrar deneyin."}
                return
            if not turn.tool_calls:
                content = self._clean(turn.content or "", model)
                self._store.append(self._run_id, ChatMessage("assistant", content))
                yield "answer", {"content": content, "model": model}
                return
            messages.append(
                {
                    "role": "assistant",
                    "content": turn.content or "",
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in turn.tool_calls
                    ],
                }
            )
            for c in turn.tool_calls:
                try:
                    arguments = json.loads(c.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                    result: dict[str, Any] = {"hata": "argümanlar geçerli JSON değil"}
                else:
                    result = self._tools.call(
                        c.name, arguments if isinstance(arguments, dict) else {}
                    )
                payload = json.dumps(result, ensure_ascii=False)
                messages.append({"role": "tool", "tool_call_id": c.id, "content": payload})
                self._store.append(
                    self._run_id,
                    ChatMessage("tool", payload, [{"name": c.name, "arguments": arguments}]),
                )
                yield "tool", {"name": c.name, "arguments": arguments, "result": result}

        content = "Soru için adım sınırına ulaşıldı; soruyu daraltarak tekrar sorun."
        self._store.append(self._run_id, ChatMessage("assistant", content))
        yield "answer", {"content": content, "model": None}
