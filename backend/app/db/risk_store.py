"""Risk motoru çıktılarının Supabase'e yazılması (migration 12_risk_engine).

Her koşu yeni bir `risk_engine_runs` satırıdır; eski koşular silinmez. En son koşu
`*_latest` görünümlerinden okunur.
"""

from dataclasses import asdict
from datetime import time
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.agent.risk_day import DayRisk
from app.agent.track_brief import TrackBrief
from app.data_package import from_minutes
from app.risk_engine import LEVEL_NAMES, EngineConfig
from app.risk_engine.summary import events

ENGINE_VERSION = "risk-engine-orta-a-1"


def _time(minutes: float) -> time:
    return from_minutes(int(round(minutes)))


def _eta(value: float) -> float | None:
    return None if value >= 1e8 else round(value, 2)


def save_day(
    conn: psycopg.Connection,
    day: DayRisk,
    cfg: EngineConfig,
    detections_source: str | None,
) -> UUID:
    """Koşuyu tek işlemde yazar ve koşu kimliğini döndürür."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """insert into public.risk_engine_runs
                 (engine_version, config, detections_source, track_count, step_count)
               values (%s, %s, %s, %s, %s) returning id""",
            (
                ENGINE_VERSION,
                Jsonb(asdict(cfg)),
                detections_source,
                len(day.tracks),
                day.step_count,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        run_id: UUID = row[0]

        timeline = []
        event_rows = []
        notice_rows = []
        for tid, risk in day.tracks.items():
            img = day.image_of.get(tid)
            for i, s in enumerate(risk.steps):
                f = s.features
                timeline.append(
                    (
                        run_id, tid, i, img, _time(s.t), LEVEL_NAMES[s.level],
                        LEVEL_NAMES[s.level_raw], s.code, s.code_raw, s.held, s.crit_static,
                        round(s.score, 2), f.d, f.dmin120, f.dd30, f.dd60, _eta(f.eta),
                        f.stop_now, f.bearing, s.tags, Jsonb(asdict(s.parts)),
                    )
                )  # fmt: skip
            for level in (2, 3):
                for e in events(risk, level):
                    event_rows.append(
                        (
                            run_id, tid, img, LEVEL_NAMES[level], _time(e.t_in),
                            None if e.t_out is None else _time(e.t_out), e.dur_min,
                            e.open_at_capture, e.censored_start, e.entry_code, e.d_in, e.dmin,
                            _time(e.t_dmin), e.codes, e.tags, e.crit_static_min,
                            None if e.exit_to is None else LEVEL_NAMES[e.exit_to], e.exit_code,
                            e.reason(),
                        )
                    )  # fmt: skip
            for n in risk.notices:
                notice_rows.append(
                    (run_id, tid, img, _time(n.t), n.kind, n.change or None, n.code, n.d)
                )

        cur.executemany(
            """insert into public.risk_timeline
                 (run_id, track_id, step_no, image_id, t, level, level_raw, code, code_raw, held,
                  crit_static, priority_score, dist_to_base_m, dmin_120_m, approach_30_m,
                  approach_60_m, eta_min, stop_now_min, bearing_deg, tags, score_parts)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s)""",
            timeline,
        )
        cur.executemany(
            """insert into public.risk_events
                 (run_id, track_id, image_id, level, t_in, t_out, dur_min, open_at_capture,
                  censored_start, entry_code, d_in_m, dmin_m, t_dmin, codes, tags,
                  crit_static_min, exit_to, exit_code, reason)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s)""",
            event_rows,
        )
        cur.executemany(
            """insert into public.risk_notices
                 (run_id, track_id, image_id, t, kind, change, code, d_m)
               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
            notice_rows,
        )
        cur.executemany(
            """insert into public.image_risk
                 (run_id, image_id, capture_time, level, level_raw, held, top_track_id, top_code,
                  top_score, top_distance_m, n_tracks, n_critical, n_critical_active,
                  n_high_plus, unregistered_level, peak120_level, peak120_track_id,
                  peak120_code, peak120_start, peak120_end, n_critical_events_120,
                  recent_critical, brief_line)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s)""",
            [
                (
                    run_id, im.image_id, _time(im.capture), LEVEL_NAMES[im.level],
                    LEVEL_NAMES[im.level_raw], im.held, im.top_track, im.top_code, im.top_score,
                    im.top_distance_m, im.n_tracks, im.n_critical, im.n_critical_active,
                    im.n_high_plus, LEVEL_NAMES[im.unregistered_level],
                    LEVEL_NAMES[im.peak_120.level] if im.peak_120 else None,
                    im.peak_120.track_id if im.peak_120 else None,
                    im.peak_120.code if im.peak_120 else None,
                    _time(im.peak_120.start) if im.peak_120 else None,
                    _time(im.peak_120.end) if im.peak_120 and im.peak_120.end else None,
                    im.n_critical_events_120, im.recent_critical, im.brief_line(),
                )
                for im in day.images
            ],
        )  # fmt: skip
    return run_id


def latest_run_id(conn: psycopg.Connection) -> UUID | None:
    row = conn.execute("select id from public.risk_latest_run").fetchone()
    return None if row is None else UUID(str(row[0]))


def save_track_briefs(
    conn: psycopg.Connection,
    run_id: UUID,
    rules_version: str,
    briefs: list[tuple[TrackBrief, float]],
) -> None:
    """Görüntüsüz track değerlendirmeleri; `briefs`: (değerlendirme, kaydın son anı dk)."""
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """insert into public.track_assessments
                 (risk_run_id, track_id, rules_version, end_time, level, code, priority_score,
                  facts, assessment, is_fallback, rejected, model)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                (
                    run_id, b.track_id, rules_version, _time(end), b.level, b.code,
                    b.priority_score, b.facts, b.text, b.is_fallback, b.rejected, b.model,
                )
                for b, end in briefs
            ],
        )  # fmt: skip
