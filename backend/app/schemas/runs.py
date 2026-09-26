"""Kayıtlı değerlendirme: kayıt deposu ile API arasındaki ortak tip."""

from dataclasses import dataclass, field
from typing import Literal

from app.schemas.api import Brief, StepEvent

RunStatus = Literal["running", "done", "failed"]


@dataclass
class StoredRun:
    run_id: str
    image_id: str
    status: RunStatus
    steps: list[StepEvent] = field(default_factory=list)
    brief: Brief | None = None
    error: str | None = None
