"""Yaklaşım C (tek LLM) ve D (çok ajanlı ekip) — rapor doğrulama.

D'nin rolleri:
1. Görsel müfettiş (VLM): koordinatlı raporlarda noktanın kırpıntısına bakar.
2. Müfettiş (LLM): kanıt dosyası + görsel sonuçla karar verir.
3. Şüpheci (LLM): müfettişin kararını çürütmeye çalışır, nihai kararı verir.
4. Hakem (kod): politikayı uygular (kimlik iddiası "consistent" olamaz; "olağan" güvencesi
   çelişkiliyse tehlikeli bayrağı).
5. Gün analisti (LLM, tek çağrı): raporlar arası çelişki ve bayat bilgi.

Bütün LLM cevapları önbelleğe yazılır; aynı girdiyle tekrar çağrılmaz.
"""

import hashlib
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.client import LLMRouter
from app.reports_v2 import evidence as ev
from app.reports_v2.verdict import ReportVerdict, VerdictLabel

PROMPTS = Path(__file__).parent / "prompts"
POLICY = (PROMPTS / "policy.md").read_text(encoding="utf-8")
MAX_TOKENS = 4096


class Cache:
    """LLM cevap önbelleği. `path` verilirse diske yazılır (demo öncesi bir kez doldurulur),
    verilmezse yalnızca bellekte tutulur (testler)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.data: dict[str, Any] = (
            json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
        )
        self.calls = 0

    def get_or(self, key_parts: list[str], fn: Callable[[], Any]) -> Any:
        key = hashlib.sha256("\x1f".join(key_parts).encode()).hexdigest()
        with self._lock:
            if key in self.data:
                return self.data[key]
        value = fn()
        with self._lock:
            self.data[key] = value
            self.calls += 1
            if self.path is not None:
                self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        return value


class VisualObject(BaseModel):
    tip: Literal["otomobil", "panelvan", "kamyon", "otobüs", "belirsiz"]
    renk: str | None
    yuk: Literal["yüklü", "boş", "örtülü", "görünmüyor"] | None


class VisualCheck(BaseModel):
    arac_var: Literal["evet", "hayır", "belirsiz"]
    araclar: list[VisualObject]
    goruntu_kalitesi: Literal["net", "bulanık", "karanlık"]
    not_: str = Field(alias="not", default="")


class Revision(BaseModel):
    report_id: int
    new_verdict: VerdictLabel
    related_ids: list[int]
    reason: str


class DayReview(BaseModel):
    revisions: list[Revision]


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _complete(
    router: LLMRouter,
    cache: Cache,
    task: str,
    system: str,
    user: str,
    schema: type[BaseModel],
    tag: str,
    image: bytes | None = None,
) -> dict[str, Any]:
    def call() -> dict[str, Any]:
        obj, model = router.complete_json(task, system, user, schema, MAX_TOKENS, image=image)
        return {"model": model, "out": obj.model_dump(by_alias=True)}

    img_key = hashlib.sha256(image).hexdigest() if image else ""
    result: dict[str, Any] = cache.get_or([tag, task, system, user, img_key], call)
    return result


def single_llm(
    router: LLMRouter, cache: Cache, dossier: dict[str, Any]
) -> tuple[ReportVerdict, list[str]]:
    """Yaklaşım C: tek çağrı."""
    user = "KANIT DOSYASI:\n" + _json(dossier) + "\n\nBu raporu doğrula."
    r = _complete(router, cache, "report_verify", POLICY, user, ReportVerdict, "C")
    return ReportVerdict.model_validate(r["out"]), [r["model"]]


def visual_check(
    router: LLMRouter, cache: Cache, data: ev.Data, report_id: int
) -> dict[str, Any] | None:
    loc = ev.point_of(data, report_id)
    if loc is None:
        return None
    img, point = loc
    image = ev.crop(data, img, point)
    text = data.package.reports[report_id].text
    system = (PROMPTS / "vision.md").read_text(encoding="utf-8")
    try:
        r = _complete(
            router,
            cache,
            "vision",
            system,
            f"Rapor: {text}\nKareye bak.",
            VisualCheck,
            "D-vision",
            image=image,
        )
    except Exception as exc:  # görsel inceleme opsiyonel
        return {"hata": str(exc)[:200]}
    out: dict[str, Any] = r["out"]
    return out


def team(
    router: LLMRouter, cache: Cache, data: ev.Data, dossier: dict[str, Any]
) -> tuple[ReportVerdict, dict[str, Any]]:
    """Yaklaşım D: görsel müfettiş → müfettiş → şüpheci → hakem (tek rapor)."""
    rid = dossier["rapor_id"]
    visual = (
        visual_check(router, cache, data, rid) if dossier.get("konum_turu") == "koordinat" else None
    )
    packet = dict(dossier)
    if visual is not None:
        packet["gorsel_inceleme"] = visual
    inv_user = (
        "KANIT DOSYASI:\n"
        + _json(packet)
        + "\n\nBu raporu doğrula. Her özellik için ayrı bir kontrol yaz."
    )
    inv = _complete(router, cache, "reasoning", POLICY, inv_user, ReportVerdict, "D-inv")
    skeptic_system = POLICY + "\n\n" + (PROMPTS / "skeptic.md").read_text(encoding="utf-8")
    sk_user = (
        "KANIT DOSYASI:\n"
        + _json(packet)
        + "\n\nMÜFETTİŞİN KARARI:\n"
        + _json(inv["out"])
        + "\n\nKararı çürütmeye çalış ve nihai kararını ver."
    )
    sk = _complete(router, cache, "reasoning", skeptic_system, sk_user, ReportVerdict, "D-skeptic")
    final = arbiter(
        ReportVerdict.model_validate(inv["out"]), ReportVerdict.model_validate(sk["out"]), dossier
    )
    return final, {
        "visual": visual,
        "investigator": inv["out"],
        "skeptic": sk["out"],
        "models": [inv["model"], sk["model"]],
    }


IDENTITY = ("dost", "ikmal", "bize bagli", "devriye")


def arbiter(inv: ReportVerdict, sk: ReportVerdict, dossier: dict[str, Any]) -> ReportVerdict:
    """Hakem (kod): şüphecinin nihai kararı esas; politika kuralları üstüne uygulanır."""
    final = sk
    text = dossier["metin"].lower()
    if any(k in text for k in IDENTITY) and final.verdict == "consistent":
        final = final.model_copy(
            update={
                "verdict": "unverifiable",
                "reasoning": final.reasoning + " (kimlik doğrulanamaz)",
            }
        )
    if final.harm == "lowers_risk" and final.verdict == "contradicts":
        final = final.model_copy(update={"dangerous_reassurance": True})
    return final


def day_review(router: LLMRouter, cache: Cache, rows: list[dict[str, Any]]) -> DayReview:
    system = POLICY + "\n\n" + (PROMPTS / "day_analyst.md").read_text(encoding="utf-8")
    user = "GÜNÜN RAPORLARI VE ÖN KARARLAR:\n" + _json(rows)
    r = _complete(router, cache, "reasoning", system, user, DayReview, "D-day")
    return DayReview.model_validate(r["out"])
