"""Değerlendirme seti: elle etiketlenmiş görüntülerle doğruluk ölçümü.

Etiketler bir TOML dosyasındadır (biçim: `eval/mock_labels.toml`). Koşucu her görüntüyü
değerlendirme servisiyle baştan değerlendirir (önbellek kullanılmaz) ve üç ölçüm verir:

- **Seviye doğruluğu:** görüntü seviyesi etiketle aynı mı; olduğundan düşük tahmin ayrıca
  sayılır, çünkü asıl tehlike odur.
- **Eşleşme:** bir tespitle eşleşmesi gereken track'lerden kaçı eşleşti, kaçı fazladan eşleşti.
- **Rapor kararları:** etiketli raporlardan kaçının kararı doğru; çelişkili raporların
  yakalanma oranı ve yanlış alarm (çelişkili denmemesi gerekirken denen) sayısı.
"""

import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from app.agent.service import EvaluationService
from app.data_package import format_hhmm, parse_hhmm
from app.pipelines.risk import LEVELS
from app.schemas.api import Brief, ReportFinding, Verdict
from app.schemas.claims import ClaimType
from app.schemas.domain import ReportSource, RiskLevel

ExpectedVerdict = Literal["consistent", "contradicts", "unverifiable", "irrelevant", "ignored"]
"""`ignored`: rapor o görüntünün değerlendirmesine hiç girmemeli."""

# Bir raporun iddiaları farklı karar alırsa raporun kararı: riski en çok etkileyen önce.
VERDICT_PRIORITY: tuple[Verdict, ...] = ("contradicts", "consistent", "unverifiable", "irrelevant")


class LabelError(ValueError):
    """Etiket dosyası okunamadı ya da biçimi hatalı."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportLabel(_Strict):
    time: str
    source: ReportSource
    claim_type: ClaimType | None = None
    verdict: ExpectedVerdict

    @field_validator("time")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        return format_hhmm(parse_hhmm(value))


class ImageLabel(_Strict):
    image_id: str
    level: RiskLevel
    matched_tracks: list[str] | None = None
    note: str | None = None
    reports: list[ReportLabel] = []


class EvalLabels(_Strict):
    images: list[ImageLabel]

    @model_validator(mode="after")
    def _unique(self) -> "EvalLabels":
        repeated = [i for i, n in Counter(x.image_id for x in self.images).items() if n > 1]
        if repeated:
            raise ValueError(f"aynı görüntü birden fazla kez etiketlenmiş: {repeated}")
        return self


def load_labels(path: Path) -> EvalLabels:
    try:
        with path.open("rb") as f:
            return EvalLabels.model_validate(tomllib.load(f))
    except (OSError, tomllib.TOMLDecodeError, ValidationError, ValueError) as exc:
        raise LabelError(f"{path}: {exc}") from exc


@dataclass(frozen=True)
class ReportCheck:
    time: str
    source: str
    claim_type: str | None
    expected: ExpectedVerdict
    actual: ExpectedVerdict

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True)
class ImageResult:
    image_id: str
    expected_level: RiskLevel
    actual_level: RiskLevel | None = None
    expected_matches: list[str] | None = None
    """Etiketteki eşleşmeler; `None` ise eşleşme kontrol edilmez."""
    missing_matches: list[str] = field(default_factory=list)
    extra_matches: list[str] = field(default_factory=list)
    reports: list[ReportCheck] = field(default_factory=list)
    automatic: bool = False
    """Brief otomatik özet mi (LLM kullanılmadı ya da cevap vermedi)."""
    error: str | None = None

    @property
    def level_ok(self) -> bool:
        return self.actual_level == self.expected_level

    @property
    def level_under(self) -> bool:
        """Seviye olduğundan düşük tahmin edildi."""
        return self.actual_level is not None and LEVELS.index(self.actual_level) < LEVELS.index(
            self.expected_level
        )


@dataclass(frozen=True)
class Summary:
    images: int
    """Başarıyla değerlendirilen görüntü sayısı; oranlar bunun üzerinden."""
    failed: int
    level_correct: int
    level_under: int
    match_expected: int
    match_found: int
    match_wrong: int
    reports_labeled: int
    reports_correct: int
    contradictions_labeled: int
    contradictions_caught: int
    false_alarms: int
    automatic: int


@dataclass(frozen=True)
class EvalResult:
    images: list[ImageResult]
    summary: Summary

    def render(self) -> str:
        return render(self)


def _report_verdict(findings: list[ReportFinding], label: ReportLabel) -> ExpectedVerdict:
    verdicts = {
        f.verdict
        for f in findings
        if f.report_time == label.time
        and f.source == label.source.value
        and (label.claim_type is None or f.claim_type == label.claim_type)
    }
    return next((v for v in VERDICT_PRIORITY if v in verdicts), "ignored")


def score_image(label: ImageLabel, brief: Brief) -> ImageResult:
    matched = {c.track_id for c in brief.contacts if c.kind == "matched" and c.track_id}
    expected = set(label.matched_tracks or [])
    return ImageResult(
        image_id=label.image_id,
        expected_level=label.level,
        actual_level=brief.risk_level,
        expected_matches=label.matched_tracks,
        missing_matches=sorted(expected - matched) if label.matched_tracks is not None else [],
        extra_matches=sorted(matched - expected) if label.matched_tracks is not None else [],
        reports=[
            ReportCheck(
                time=r.time,
                source=r.source.value,
                claim_type=r.claim_type,
                expected=r.verdict,
                actual=_report_verdict(brief.report_findings, r),
            )
            for r in label.reports
        ],
        automatic=brief.is_fallback,
    )


def summarize(results: list[ImageResult]) -> Summary:
    done = [r for r in results if r.error is None]
    expected = sum(len(r.expected_matches or []) for r in done)
    missing = sum(len(r.missing_matches) for r in done)
    reports = [c for r in done for c in r.reports]
    return Summary(
        images=len(done),
        failed=len(results) - len(done),
        level_correct=sum(r.level_ok for r in done),
        level_under=sum(r.level_under for r in done),
        match_expected=expected,
        match_found=expected - missing,
        match_wrong=sum(len(r.extra_matches) for r in done),
        reports_labeled=len(reports),
        reports_correct=sum(c.ok for c in reports),
        contradictions_labeled=sum(c.expected == "contradicts" for c in reports),
        contradictions_caught=sum(
            c.expected == "contradicts" and c.actual == "contradicts" for c in reports
        ),
        false_alarms=sum(
            c.expected != "contradicts" and c.actual == "contradicts" for c in reports
        ),
        automatic=sum(r.automatic for r in done),
    )


def run_eval_set(service: EvaluationService, labels: EvalLabels) -> EvalResult:
    """Her etiketli görüntüyü değerlendirir; bir görüntünün hatası diğerlerini durdurmaz."""
    results: list[ImageResult] = []
    for label in labels.images:
        try:
            brief = service.run(label.image_id)
        except Exception as exc:  # koşucu raporlamaya devam etmeli
            results.append(
                ImageResult(label.image_id, label.level, error=f"{type(exc).__name__}: {exc}")
            )
            continue
        results.append(score_image(label, brief))
    return EvalResult(results, summarize(results))


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} (%{round(100 * part / whole)})" if whole else "0/0 (—)"


def render(result: EvalResult) -> str:
    s = result.summary
    lines = ["Görüntüler:"]
    for r in result.images:
        if r.error:
            lines.append(f"  ✗ {r.image_id}: hata — {r.error}")
            continue
        mark = "✓" if r.level_ok else "✗"
        level = f"seviye {r.actual_level} (beklenen {r.expected_level})"
        if r.level_under:
            level += " ⚠ düşük tahmin"
        parts = [level]
        if r.missing_matches:
            parts.append(f"eşleşmeyen: {', '.join(r.missing_matches)}")
        if r.extra_matches:
            parts.append(f"fazla eşleşme: {', '.join(r.extra_matches)}")
        wrong = [c for c in r.reports if not c.ok]
        parts += [f"rapor {c.time} {c.source}: {c.actual} (beklenen {c.expected})" for c in wrong]
        if r.automatic:
            parts.append("otomatik özet")
        lines.append(f"  {mark} {r.image_id}: " + "; ".join(parts))
    lines += [
        "",
        f"Seviye doğruluğu: {_pct(s.level_correct, s.images)}, {s.level_under} düşük tahmin",
        f"Eşleşme: {s.match_found}/{s.match_expected} doğru, {s.match_wrong} yanlış",
        f"Rapor kararları: {_pct(s.reports_correct, s.reports_labeled)}",
        f"Çelişkili rapor yakalama: {_pct(s.contradictions_caught, s.contradictions_labeled)}, "
        f"{s.false_alarms} yanlış alarm",
        f"LLM brief: {s.images - s.automatic}/{s.images} (otomatik özet: {s.automatic})",
    ]
    if s.failed:
        lines.append(f"Değerlendirilemeyen görüntü: {s.failed}")
    return "\n".join(lines)
