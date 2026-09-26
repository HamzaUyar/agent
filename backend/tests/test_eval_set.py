"""Değerlendirme seti koşucusu (ticket 12).

Etiketler sahte veri paketine göre elle yazılmıştır; koşucu gerçek değerlendirme
servisini çalıştırıp seviye, eşleşme ve rapor kararı ölçümlerini hesaplar.
"""

from datetime import time
from pathlib import Path
from typing import Any

import pytest

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.eval_set import (
    EvalLabels,
    EvalResult,
    LabelError,
    load_labels,
    run_eval_set,
    score_image,
    summarize,
)
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import Detection, FieldReport, ImageMeta, ReportSource, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
MOCK_LABELS = Path(__file__).parents[1] / "eval" / "mock_labels.toml"
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
T0122_AT_1410 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0122" and p.time == time(14, 10)
)
T0032_AT_1235 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0032" and p.time == time(12, 35)
)


class FakeDetector:
    version = "test"

    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK] if image.image_id == "img_000860" else []


def claim_at(lat: float, lon: float, **overrides: Any) -> ReportClaim:
    base: dict[str, Any] = {
        "location_type": "coordinate",
        "lat": lat,
        "lon": lon,
        "zone": None,
        "vehicle_type": None,
        "vehicle_count": 1,
        "color": None,
        "behavior": None,
        "claim_type": "observation",
        "time_reference": None,
        "is_verifiable": True,
    }
    return ReportClaim.model_validate(base | overrides)


CLAIMS = [
    # 12:35 resmi: T0032 ile tutarlı.
    ClaimRecord(
        1,
        FieldReport(time(12, 35), ReportSource.OFFICIAL, "1 agir arac"),
        claim_at(T0032_AT_1235.lat, T0032_AT_1235.lon, vehicle_type="heavy"),
    ),
    # 14:10 üçüncü taraf: "binek araç" diyor, T0122 truck → çelişkili.
    ClaimRecord(
        2,
        FieldReport(time(14, 10), ReportSource.THIRD_PARTY, "binek arac, dost"),
        claim_at(T0122_AT_1410.lat, T0122_AT_1410.lon, vehicle_type="car"),
    ),
    ClaimRecord(
        3,
        FieldReport(time(14, 10), ReportSource.THIRD_PARTY, "binek arac, dost"),
        claim_at(
            T0122_AT_1410.lat, T0122_AT_1410.lon, vehicle_type="car", claim_type="friendly_claim"
        ),
    ),
    # 14:20: çekim anından sonra, değerlendirmeye girmemeli.
    ClaimRecord(
        4,
        FieldReport(time(14, 20), ReportSource.OFFICIAL, "kamyon"),
        claim_at(T0122_AT_1410.lat, T0122_AT_1410.lon, vehicle_type="truck"),
    ),
]


def service() -> EvaluationService:
    return EvaluationService(InMemoryRepository(PACKAGE, claims=CLAIMS), FakeDetector())


def labels(text: str, tmp_path: Path) -> EvalLabels:
    path = tmp_path / "labels.toml"
    path.write_text(text, encoding="utf-8")
    return load_labels(path)


CORRECT = """
[[images]]
image_id = "img_000860"
level = "critical"
matched_tracks = ["T0122"]

  [[images.reports]]
  time = "12:35"
  source = "official"
  verdict = "consistent"

  [[images.reports]]
  time = "14:10"
  source = "third_party"
  verdict = "contradicts"

  [[images.reports]]
  time = "14:20"
  source = "official"
  verdict = "ignored"

[[images]]
image_id = "img_000100"
level = "low"
matched_tracks = []
"""


# --- Etiket formatı ----------------------------------------------------------------


def test_label_file_is_read(tmp_path: Path) -> None:
    parsed = labels(CORRECT, tmp_path)

    assert [i.image_id for i in parsed.images] == ["img_000860", "img_000100"]
    first = parsed.images[0]
    assert first.level == "critical"
    assert first.matched_tracks == ["T0122"]
    assert [(r.time, r.verdict) for r in first.reports] == [
        ("12:35", "consistent"),
        ("14:10", "contradicts"),
        ("14:20", "ignored"),
    ]


def test_matches_and_reports_are_optional(tmp_path: Path) -> None:
    parsed = labels('[[images]]\nimage_id = "img_000860"\nlevel = "high"\n', tmp_path)

    assert parsed.images[0].matched_tracks is None
    assert parsed.images[0].reports == []


@pytest.mark.parametrize(
    "text",
    [
        '[[images]]\nimage_id = "img_000860"\nlevel = "severe"\n',  # bilinmeyen seviye
        '[[images]]\nimage_id = "img_000860"\nlevl = "high"\n',  # yazım hatası
        '[[images]]\nimage_id = "img_000860"\nlevel = "high"\n'
        '[[images.reports]]\ntime = "25:00"\nsource = "official"\nverdict = "consistent"\n',
        '[[images]]\nimage_id = "img_000860"\nlevel = "high"\n'
        '[[images]]\nimage_id = "img_000860"\nlevel = "low"\n',  # aynı görüntü iki kez
    ],
)
def test_invalid_labels_are_rejected_with_the_file_name(text: str, tmp_path: Path) -> None:
    with pytest.raises(LabelError, match="labels.toml"):
        labels(text, tmp_path)


def test_mock_label_file_matches_the_format() -> None:
    assert {i.image_id for i in load_labels(MOCK_LABELS).images} == {"img_000860", "img_000100"}


# --- Koşucu ve özet ----------------------------------------------------------------


def test_everything_right_scores_full_marks(tmp_path: Path) -> None:
    result = run_eval_set(service(), labels(CORRECT, tmp_path))

    s = result.summary
    assert (s.images, s.level_correct, s.level_under) == (2, 2, 0)
    assert (s.match_expected, s.match_found, s.match_wrong) == (1, 1, 0)
    assert (s.reports_labeled, s.reports_correct) == (3, 3)
    assert (s.contradictions_labeled, s.contradictions_caught, s.false_alarms) == (1, 1, 0)
    assert s.failed == 0


def test_wrong_level_is_counted_and_underestimation_is_flagged(tmp_path: Path) -> None:
    text = CORRECT.replace('level = "low"', 'level = "high"')  # img_000100 aslında düşük

    result = run_eval_set(service(), labels(text, tmp_path))

    assert (result.summary.level_correct, result.summary.level_under) == (1, 1)
    row = next(r for r in result.images if r.image_id == "img_000100")
    assert (row.expected_level, row.actual_level, row.level_ok) == ("high", "low", False)


def test_missing_and_extra_matches_are_counted(tmp_path: Path) -> None:
    text = CORRECT.replace('matched_tracks = ["T0122"]', 'matched_tracks = ["T0032"]')

    result = run_eval_set(service(), labels(text, tmp_path))

    s = result.summary
    assert (s.match_expected, s.match_found, s.match_wrong) == (1, 0, 1)
    row = next(r for r in result.images if r.image_id == "img_000860")
    assert (row.missing_matches, row.extra_matches) == (["T0032"], ["T0122"])


def test_uncaught_contradiction_and_false_alarm(tmp_path: Path) -> None:
    text = CORRECT.replace(
        'time = "12:35"\n  source = "official"\n  verdict = "consistent"',
        'time = "12:35"\n  source = "official"\n  verdict = "contradicts"',
    ).replace(
        'time = "14:10"\n  source = "third_party"\n  verdict = "contradicts"',
        'time = "14:10"\n  source = "third_party"\n  verdict = "unverifiable"',
    )

    result = run_eval_set(service(), labels(text, tmp_path))

    s = result.summary
    assert (s.contradictions_labeled, s.contradictions_caught, s.false_alarms) == (1, 0, 1)
    assert s.reports_correct == 1  # yalnızca 14:20 "ignored"


def test_report_with_several_claims_contradicts_if_any_claim_does(tmp_path: Path) -> None:
    result = run_eval_set(service(), labels(CORRECT, tmp_path))

    row = next(r for r in result.images if r.image_id == "img_000860")
    check = next(c for c in row.reports if c.time == "14:10")
    assert (check.expected, check.actual, check.ok) == ("contradicts", "contradicts", True)


def test_claim_type_narrows_which_claims_of_a_report_are_judged(tmp_path: Path) -> None:
    text = """
[[images]]
image_id = "img_000860"
level = "critical"

  [[images.reports]]
  time = "14:10"
  source = "third_party"
  claim_type = "friendly_claim"
  verdict = "contradicts"
"""
    result = run_eval_set(service(), labels(text, tmp_path))

    assert result.summary.reports_correct == 1


def test_unknown_image_is_reported_as_failed_not_crashing(tmp_path: Path) -> None:
    text = CORRECT + '\n[[images]]\nimage_id = "img_999999"\nlevel = "low"\n'

    result = run_eval_set(service(), labels(text, tmp_path))

    assert result.summary.failed == 1
    row = next(r for r in result.images if r.image_id == "img_999999")
    assert row.error is not None
    assert result.summary.images == 2  # başarısız görüntü oranlara girmez


def test_summary_text_shows_the_headline_numbers(tmp_path: Path) -> None:
    result = run_eval_set(service(), labels(CORRECT, tmp_path))

    text = result.render()
    assert "Seviye doğruluğu: 2/2 (%100)" in text
    assert "Eşleşme: 1/1 doğru, 0 yanlış" in text
    assert "Çelişkili rapor yakalama: 1/1 (%100), 0 yanlış alarm" in text
    assert "img_000860" in text


def test_brief_source_is_recorded_per_image(tmp_path: Path) -> None:
    result = run_eval_set(service(), labels(CORRECT, tmp_path))

    assert all(r.automatic for r in result.images if r.error is None)  # LLM yok
    assert result.summary.automatic == 2


def test_llm_adjusted_images_are_counted_separately(tmp_path: Path) -> None:
    brief = service().run("img_000860")
    raised = [
        c.model_copy(update={"final_level": "critical", "adjustment_reason": "üsse yakın park"})
        if c.track_id == "T0032"
        else c
        for c in brief.contacts
    ]
    label = labels(CORRECT, tmp_path).images[0]

    row = score_image(label, brief.model_copy(update={"contacts": raised}))

    assert row.llm_adjusted is True
    assert summarize([row]).llm_adjusted == 1
    assert "LLM ayarı" in EvalResult([row], summarize([row])).render()
