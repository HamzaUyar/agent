"""Sohbet mesajı: sohbet deposu ile agent arasındaki ortak tip."""

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["user", "assistant", "tool"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    tool_calls: list[dict[str, Any]] | None = None
