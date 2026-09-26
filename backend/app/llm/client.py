"""LLM katmanı: görev → model zinciri, sağlayıcılar ve yedek modele geçiş.

Ana sağlayıcı EVREN (SSB, OpenAI uyumlu uç nokta). Organizatörlerin GLM uç noktası
da OpenAI uyumlu ayrı bir sağlayıcıdır. Claude modelleri, anahtar tanımlıysa, resmi
`anthropic` SDK'sıyla çağrılır. Hangi görevde hangi modelin kullanılacağı
`models.toml` dosyasındadır.
"""

import base64
import json
import logging
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

import anthropic
import openai
from pydantic import BaseModel

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_MODELS_PATH = Path(__file__).with_name("models.toml")

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


@dataclass(frozen=True)
class ModelEntry:
    name: str
    provider: str
    model_id: str
    extra_body: dict[str, Any] = field(default_factory=dict)
    """Sağlayıcıya olduğu gibi iletilen ek istek alanları (ör. düşünmeyi kapatmak)."""


@dataclass(frozen=True)
class ModelConfig:
    models: dict[str, ModelEntry]
    tasks: dict[str, list[str]]


def load_model_config(path: Path | None = None) -> ModelConfig:
    with (path or DEFAULT_MODELS_PATH).open("rb") as f:
        raw = tomllib.load(f)
    models = {
        name: ModelEntry(
            name=name,
            provider=m["provider"],
            model_id=m["model_id"],
            extra_body=dict(m.get("extra_body", {})),
        )
        for name, m in raw["models"].items()
    }
    tasks: dict[str, list[str]] = {task: list(chain) for task, chain in raw["tasks"].items()}
    unknown = {n for chain in tasks.values() for n in chain} - models.keys()
    if unknown:
        raise ValueError(f"models.toml: tanımsız model(ler): {sorted(unknown)}")
    return ModelConfig(models=models, tasks=tasks)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str
    """JSON metni; modelin ürettiği haliyle."""


@dataclass(frozen=True)
class ChatTurn:
    """Modelin bir sohbet turu: ya metin cevap ya da araç çağrıları."""

    content: str | None
    tool_calls: list[ToolCall]


class Provider(Protocol):
    def is_available(self) -> bool:
        """Kimlik bilgisi tanımlı mı."""
        ...

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int,
        extra_body: Mapping[str, Any] | None = None,
        image: bytes | None = None,
    ) -> BaseModel:
        """Cevabı `schema`'ya uyan bir nesne olarak döndürür; uymazsa hata fırlatır.

        `image` verilirse (JPEG) kullanıcı mesajına eklenir; görüntü destekli model gerekir.
        """
        ...

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        extra_body: Mapping[str, Any] | None = None,
    ) -> ChatTurn:
        """OpenAI biçiminde mesaj ve araç tanımlarıyla tek bir sohbet turu."""
        ...


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class AnthropicProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: anthropic.Anthropic | None = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int,
        extra_body: Mapping[str, Any] | None = None,
        image: bytes | None = None,
    ) -> BaseModel:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)
        content: Any = user
        if image is not None:
            content = [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(image)},
                },
                {"type": "text", "text": user},
            ]
        response = self._client.messages.parse(
            model=model_id,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"{model_id} isteği reddetti")
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError(f"{model_id} yapılandırılmış çıktı döndürmedi")
        return parsed

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        extra_body: Mapping[str, Any] | None = None,
    ) -> ChatTurn:
        raise NotImplementedError("Sohbet araçları yalnızca OpenAI uyumlu sağlayıcılarda")


# Düşünen modellerde (GLM, DeepSeek, Qwen) max_tokens düşünme ve cevap için ortak
# bütçedir; EVREN en az 4096 öneriyor, aksi halde JSON yarıda kalıyor.
MIN_OPENAI_COMPAT_TOKENS = 4096


class OpenAICompatibleProvider:
    """OpenAI uyumlu uç nokta (EVREN, organizatör GLM'i); şema `json_schema` ile istenir."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client: openai.OpenAI | None = None

    def is_available(self) -> bool:
        return bool(self._api_key and self._base_url)

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int,
        extra_body: Mapping[str, Any] | None = None,
        image: bytes | None = None,
    ) -> BaseModel:
        if self._client is None:
            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        json_schema = schema.model_json_schema()
        schema_text = json.dumps(json_schema, ensure_ascii=False)
        content: Any = user
        if image is not None:
            content = [
                {"type": "text", "text": user},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{_b64(image)}"},
                },
            ]
        response = self._client.chat.completions.create(
            model=model_id,
            max_tokens=max(max_tokens, MIN_OPENAI_COMPAT_TOKENS),
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": json_schema},
            },
            extra_body=dict(extra_body) if extra_body else None,
            messages=[
                {
                    "role": "system",
                    "content": f"{system}\n\nYalnızca şu JSON şemasına uyan JSON döndür:\n"
                    f"{schema_text}",
                },
                {"role": "user", "content": content},
            ],
        )
        text = response.choices[0].message.content
        if not text:
            raise ValueError(f"{model_id} boş cevap döndürdü")
        return schema.model_validate_json(text)

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        extra_body: Mapping[str, Any] | None = None,
    ) -> ChatTurn:
        if self._client is None:
            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        # Mesaj ve araç listeleri dinamik (dict) üretiliyor; SDK'nın aşırı yüklemeleri
        # TypedDict beklediği için bu çağrıda tip denetimini gevşetiyoruz.
        completions: Any = self._client.chat.completions
        response = completions.create(
            model=model_id,
            max_tokens=max(max_tokens, MIN_OPENAI_COMPAT_TOKENS),
            messages=messages,
            tools=tools,
            tool_choice="auto",
            extra_body=dict(extra_body) if extra_body else None,
        )
        message = response.choices[0].message
        calls = [
            ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments or "{}")
            for c in message.tool_calls or []
            if c.type == "function"
        ]
        if not calls and not message.content:
            raise ValueError(f"{model_id} boş cevap döndürdü")
        return ChatTurn(content=message.content, tool_calls=calls)


class LLMUnavailableError(RuntimeError):
    """Görevin zincirindeki hiçbir model cevap veremedi."""

    def __init__(self, task: str, attempts: list[tuple[str, str]]) -> None:
        self.task = task
        self.attempts = attempts
        tried = "; ".join(f"{model}: {reason}" for model, reason in attempts)
        super().__init__(f"'{task}' için kullanılabilir model yok ({tried})")


class LLMRouter:
    def __init__(self, config: ModelConfig, providers: Mapping[str, Provider]) -> None:
        self._config = config
        self._providers = providers

    def _run_chain(self, task: str, call: Callable[[Provider, ModelEntry], R]) -> tuple[R, str]:
        """Görevin zincirini sırayla dener; sonucu ve sonucu veren modeli döndürür.

        Model `sağlayıcı/model_id` biçimindedir (ör. `evren/glm-5.3`); aynı model birden
        fazla sağlayıcıda olabileceği için sağlayıcı da yazılır.
        """
        attempts: list[tuple[str, str]] = []
        for name in self._config.tasks[task]:
            entry = self._config.models[name]
            provider = self._providers.get(entry.provider)
            if provider is None or not provider.is_available():
                attempts.append((entry.model_id, "kimlik bilgisi yok"))
                continue
            try:
                result = call(provider, entry)
            except Exception as exc:  # herhangi bir hata: zincirdeki sıradaki modele geç
                logger.warning("%s başarısız (%s): %s", entry.model_id, task, exc)
                attempts.append((entry.model_id, f"{type(exc).__name__}: {exc}"))
                continue
            return result, f"{entry.provider}/{entry.model_id}"
        raise LLMUnavailableError(task, attempts)

    def complete_json(
        self,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 4096,
        *,
        image: bytes | None = None,
    ) -> tuple[T, str]:
        # Görüntüsüz çağrılarda `image` iletilmez; metin sağlayıcılarının imzası değişmez.
        extra: dict[str, Any] = {"image": image} if image is not None else {}

        def call(provider: Provider, entry: ModelEntry) -> T:
            result = provider.complete_json(
                entry.model_id, system, user, schema, max_tokens, entry.extra_body or None, **extra
            )
            if not isinstance(result, schema):
                raise TypeError("beklenen şemada değil")
            return result

        return self._run_chain(task, call)

    def chat(
        self,
        task: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> tuple[ChatTurn, str]:
        def call(provider: Provider, entry: ModelEntry) -> ChatTurn:
            return provider.chat(
                entry.model_id, messages, tools, max_tokens, entry.extra_body or None
            )

        return self._run_chain(task, call)


def build_router(settings: Settings | None = None, config: ModelConfig | None = None) -> LLMRouter:
    s = settings or get_settings()
    providers: dict[str, Provider] = {
        "evren": OpenAICompatibleProvider(s.evren_api_key.get_secret_value(), s.evren_api_base),
        "glm": OpenAICompatibleProvider(s.glm_api_key.get_secret_value(), s.glm_api_base),
        "anthropic": AnthropicProvider(s.anthropic_api_key.get_secret_value()),
    }
    return LLMRouter(config or load_model_config(), providers)
