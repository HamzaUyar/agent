"""Zaman boyutlu risk motoru (app/risk_engine)."""

import csv
import os
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from app.agent.risk_day import compute_day
from app.core.rules import load_rules
from app.data_package import read_package, to_minutes
from app.db.repositories import InMemoryRepository
from app.risk_engine import Point, default_config, load_config, run_track, to_local
from app.risk_engine.config import DEFAULT_PATH
from app.risk_engine.summary import events, image_summary
from app.schemas.domain import GeoPoint

BACKEND_DIR = Path(__file__).resolve().parents[1]
STAGE2 = Path(os.environ.get("STAGE2_DIR", BACKEND_DIR / "../../stage2")).resolve()
GOLDEN = Path(__file__).parent / "fixtures" / "risk_engine" / "golden.csv"
BASE = GeoPoint(39.92184, 32.85306)
CFG = default_config()


def east(t: float, meters: float, north: float = 0.0) -> Point:
    return Point(t, meters, north)


def line(start_m: float, end_m: float, minutes: int = 120, t0: float = 600) -> list[Point]:
    """Üssün doğusunda `start_m`'den `end_m`'e 5 dakikalık adımlarla doğrusal hareket."""
    n = minutes // 5
    return [east(t0 + 5 * i, start_m + (end_m - start_m) * i / n) for i in range(n + 1)]


# --- referans uygulamayla birebir ----------------------------------------------------


@pytest.mark.skipif(not (STAGE2 / "tracks.csv").is_file(), reason="stage2 veri paketi yok")
def test_matches_the_reference_implementation_on_every_real_step() -> None:
    """Konsensüs simülasyonundaki referans kodun 226 iz × 25 adımlık çıktısı: seviye, kural
    kodu, iniş beklemesi ve öncelik skoru birebir aynı olmalı."""
    points: dict[str, list[Point]] = defaultdict(list)
    with (STAGE2 / "tracks.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            h, m = r["time"].split(":")
            x, y = to_local(GeoPoint(float(r["lat"]), float(r["lon"])), BASE)
            points[r["track_id"]].append(Point(int(h) * 60 + int(m), x, y))
    golden: dict[str, list[dict[str, str]]] = defaultdict(list)
    with GOLDEN.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            golden[r["tid"]].append(r)

    mismatches = []
    for tid, rows in golden.items():
        label = rows[0]["label"] or None
        conf = float(rows[0]["conf"]) if rows[0]["conf"] else None
        risk = run_track(tid, sorted(points[tid], key=lambda p: p.t), label, conf, CFG)
        for step, row in zip(risk.steps, rows, strict=True):
            got = (step.level_raw, step.code_raw, step.level, step.code, step.held)
            want = (int(row["Lraw"]), row["code_raw"], int(row["S"]), row["code"])
            if got[:4] != want or str(step.held) != row["held"]:
                mismatches.append((tid, row["i"], got, want))
            assert step.score == pytest.approx(float(row["score"]), abs=1e-3)
    assert len(golden) == 226
    assert mismatches == []


# --- yapılandırma --------------------------------------------------------------------


def test_config_rejects_missing_or_extra_keys(tmp_path: Path) -> None:
    text = DEFAULT_PATH.read_text(encoding="utf-8")
    extra = tmp_path / "extra.toml"
    extra.write_text(text.replace("[trend]", "[trend]\nunknown_key = 1"), encoding="utf-8")
    missing = tmp_path / "missing.toml"
    missing.write_text(text.replace("a30_m = 300\n", "", 1), encoding="utf-8")

    with pytest.raises(ValueError, match="fazla"):
        load_config(extra)
    with pytest.raises(ValueError, match="eksik"):
        load_config(missing)


# --- seviye kuralları ----------------------------------------------------------------


def test_fast_approach_into_the_inner_ring_is_critical() -> None:
    risk = run_track("T1", line(4_000, 1_300), None, None, CFG)

    assert risk.current.level == 3
    assert risk.current.code == "C2_approach_inner"


def test_vehicle_parked_inside_one_km_is_high_not_critical() -> None:
    """Üssün 1 km içinde park eden araç: yüksek (H2), hareket ederse kritik (C1)."""
    parked = [east(600 + 5 * i, 700) for i in range(25)]

    risk = run_track("T1", parked, None, None, CFG)

    assert risk.current.level == 2
    assert risk.current.code == "H2_near"
    assert risk.current.dwell_min >= 90


def test_vehicle_moving_inside_one_km_is_critical() -> None:
    pts = [east(600 + 5 * i, 700 + (150 if i % 2 else 0), 150 * (i % 3)) for i in range(25)]

    assert run_track("T1", pts, None, None, CFG).current.code == "C1_perimeter"


def test_heavy_vehicle_turns_approach_critical_further_out() -> None:
    pts = line(4_000, 1_800)

    car = run_track("T1", pts, "car", 0.9, CFG).current
    truck = run_track("T1", pts, "truck", 0.9, CFG).current

    assert (car.level, truck.level) == (2, 3)
    assert truck.code == "C3_heavy_approach"


def test_level_is_held_for_the_hold_time_after_the_condition_clears() -> None:
    """Kritik koşulu kalkınca bekleme sayacı işler; 15 dk dolunca (koşulun kalktığı üçüncü
    gözlem) seviye iner. Tutulurken öncelik skoru düşer."""
    approach = line(4_000, 1_300, minutes=60)
    retreat = [east(approach[-1].t + 5 * i, 1_300 + 800 * i) for i in range(1, 7)]

    steps = run_track("T1", approach + retreat, None, None, CFG).steps
    after = steps[len(approach) :]

    assert [s.level for s in after[:2]] == [3, 3]
    assert all(s.held and s.code.startswith("HOLD<") for s in after[:2])
    assert after[2].level < 3
    assert after[0].score < steps[len(approach) - 1].score


def test_priority_score_stays_inside_the_level_band() -> None:
    risk = run_track("T1", line(4_000, 1_300), "truck", 0.9, CFG)

    for s in risk.steps:
        assert 25 * s.level <= s.score < 25 * s.level + 25


def test_changed_engine_threshold_changes_the_level() -> None:
    pts = line(4_000, 1_800)
    wider = replace(CFG, critical=replace(CFG.critical, approach_m=2_000))

    assert run_track("T1", pts, None, None, CFG).current.level == 2
    assert run_track("T1", pts, None, None, wider).current.level == 3


# --- olaylar ve görüntü özeti --------------------------------------------------------


def test_events_record_entry_rule_and_closest_point() -> None:
    risk = run_track("T1", line(4_000, 1_300), None, None, CFG)

    [crit] = events(risk, 3)

    assert crit.open_at_capture
    assert crit.entry_code == "C2_approach_inner"
    assert crit.dmin == pytest.approx(1_300, abs=1)
    assert "C2" not in crit.reason() and "1,5 km" in crit.reason()


def test_image_summary_uses_capture_state_and_keeps_the_recent_peak() -> None:
    capture = 720.0
    approach = line(4_000, 1_300, minutes=60, t0=capture - 90)
    retreat = [east(approach[-1].t + 5 * i, 1_300 + 800 * i) for i in range(1, 7)]
    left = run_track("T1", approach + retreat, None, None, CFG)
    idle = run_track("T2", [east(capture - 120 + 5 * i, 5_000) for i in range(25)], None, None, CFG)

    summary = image_summary("img", capture, [left, idle])

    assert summary.level < 3
    assert summary.peak_120 is not None and summary.peak_120.level == 3
    assert summary.peak_120.track_id == "T1"
    assert summary.n_critical_events_120 == 1
    assert summary.recent_critical
    assert "son 2 sa tepe CRITICAL T1" in summary.brief_line()


# --- günün tamamı (scripts.compute_risk) ---------------------------------------------


class _NoDetections:
    version = "test"

    def detect(self, image: object) -> list[object]:
        return []


def test_compute_day_covers_every_image_and_uses_capture_state() -> None:

    package = read_package(Path(__file__).parent / "fixtures" / "mock_package")
    day = compute_day(InMemoryRepository(package), _NoDetections(), load_rules())  # type: ignore[arg-type]

    assert {i.image_id for i in day.images} == {m.image_id for m in package.images}
    assert day.step_count == sum(len(r.steps) for r in day.tracks.values())
    capture = {m.image_id: to_minutes(m.capture_time) for m in package.images}
    for summary in day.images:
        mine = [r for t, r in day.tracks.items() if day.image_of[t] == summary.image_id]
        at_capture = [r.current.level for r in mine if r.current.t == capture[summary.image_id]]
        assert summary.level == max(at_capture, default=0)
