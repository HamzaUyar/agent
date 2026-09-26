"""Supabase tablolarına okuma/yazma: kaynak verinin okunması ve değerlendirme kayıtları."""

import logging
from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.schemas.api import Brief, StepEvent
from app.schemas.chat import ChatMessage, Role
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import (
    Base,
    Corners,
    DataPackage,
    FieldReport,
    GeoPoint,
    ImageMeta,
    ReportSource,
    RiskLevel,
    TrackPoint,
    Zone,
)
from app.schemas.runs import RunStatus, StoredRun

logger = logging.getLogger(__name__)

_LAT = "extensions.st_y({0}::extensions.geometry)"
_LON = "extensions.st_x({0}::extensions.geometry)"


def _latlon(column: str) -> str:
    return f"{_LAT.format(column)}, {_LON.format(column)}"


def fetch_package(conn: psycopg.Connection) -> DataPackage:
    """Kaynak tabloları okuyup bir `DataPackage` kurar."""
    with conn.cursor() as cur:
        cur.execute(f"select name, {_latlon('location')} from public.bases order by id limit 1")
        base_row = cur.fetchone()
        if base_row is None:
            raise RuntimeError("Veritabanında üs yok; önce veri yükleyin (load-data)")
        base = Base(name=base_row[0], location=GeoPoint(base_row[1], base_row[2]))

        cur.execute(f"select name, {_latlon('center')} from public.zones order by id")
        zones = [Zone(name, GeoPoint(lat, lon)) for name, lat, lon in cur.fetchall()]

        cur.execute(
            """select id, width_px, height_px, capture_time,
                      tl_lat, tl_lon, tr_lat, tr_lon, bl_lat, bl_lon, br_lat, br_lon
               from public.images order by id"""
        )
        images = [
            ImageMeta(
                image_id=r[0],
                width_px=r[1],
                height_px=r[2],
                capture_time=r[3],
                corners=Corners(
                    top_left=GeoPoint(r[4], r[5]),
                    top_right=GeoPoint(r[6], r[7]),
                    bottom_left=GeoPoint(r[8], r[9]),
                    bottom_right=GeoPoint(r[10], r[11]),
                ),
            )
            for r in cur.fetchall()
        ]

        cur.execute(
            f"select track_id, time, {_latlon('location')} from public.track_points"
            " order by track_id, time"
        )
        points = [TrackPoint(tid, t, GeoPoint(lat, lon)) for tid, t, lat, lon in cur.fetchall()]

        cur.execute("select time, source::text, text from public.field_reports order by time, id")
        reports = [FieldReport(t, ReportSource(src), text) for t, src, text in cur.fetchall()]

    return DataPackage(base=base, zones=zones, images=images, track_points=points, reports=reports)


class RunRecorder:
    """Kayıt deposu (`RunStore`): `analysis_runs` ve `agent_steps` tabloları."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def start(self, image_id: str, detector_version: str, models: Mapping[str, Any]) -> str:
        with self._conn.transaction():
            row = self._conn.execute(
                """insert into public.analysis_runs (image_id, detector_version, models)
                   values (%s, %s, %s) returning id""",
                (image_id, detector_version, Jsonb(dict(models))),
            ).fetchone()
        assert row is not None
        return str(row[0])

    def add_step(self, run_id: str, event: StepEvent) -> None:
        with self._conn.transaction():
            self._conn.execute(
                """insert into public.agent_steps (run_id, step_no, step_name, output)
                   values (%s, %s, %s, %s)""",
                (run_id, event.step_no, event.name, Jsonb(event.model_dump(mode="json"))),
            )

    def finish(self, run_id: str, brief: Brief) -> None:
        with self._conn.transaction():
            self._conn.execute(
                """update public.analysis_runs set
                       status = 'done', finished_at = now(), overall_risk_level = %s,
                       brief = %s, brief_json = %s, is_fallback = %s
                   where id = %s""",
                (
                    brief.risk_level,
                    brief.text,
                    Jsonb(brief.model_dump(mode="json")),
                    brief.is_fallback,
                    run_id,
                ),
            )

    def fail(self, run_id: str, error: str) -> None:
        with self._conn.transaction():
            self._conn.execute(
                """update public.analysis_runs set status = 'failed', finished_at = now(),
                       error = %s where id = %s""",
                (error, run_id),
            )

    def get(self, run_id: str) -> StoredRun | None:
        try:
            uid = UUID(run_id)
        except ValueError:
            return None
        row = self._conn.execute(
            """select id, image_id, status::text, brief_json, error
               from public.analysis_runs where id = %s""",
            (uid,),
        ).fetchone()
        if row is None:
            return None
        steps = self._conn.execute(
            "select output from public.agent_steps where run_id = %s order by step_no", (uid,)
        ).fetchall()
        return StoredRun(
            run_id=str(row[0]),
            image_id=row[1],
            status=cast(RunStatus, row[2]),
            steps=[StepEvent.model_validate(s[0]) for s in steps],
            brief=Brief.model_validate(row[3]) if row[3] else None,
            error=row[4],
        )

    def latest_cached(self, image_id: str, detector_version: str) -> StoredRun | None:
        """Aynı tespit bileşeniyle yapılmış son başarılı değerlendirme; LLM'in yazdığı brief
        otomatik özete tercih edilir."""
        rows = self._conn.execute(
            """select id from public.analysis_runs
               where image_id = %s and detector_version = %s and status = 'done'
                 and brief_json is not null
               order by is_fallback asc, finished_at desc""",
            (image_id, detector_version),
        ).fetchall()
        for (run_id,) in rows:
            try:
                return self.get(str(run_id))
            except ValidationError:
                # Eski bir kod sürümünün kaydı; güncel şemaya uymuyor, önbellek sayılmaz.
                logger.info("Önbellek atlandı, şema eski: %s", run_id)
        return None

    def latest_levels(self) -> dict[str, RiskLevel]:
        """Her görüntünün tamamlanmış son değerlendirmesinin seviyesi."""
        rows = self._conn.execute(
            """select distinct on (image_id) image_id, overall_risk_level::text
               from public.analysis_runs where status = 'done'
               order by image_id, finished_at desc"""
        ).fetchall()
        return {image_id: cast(RiskLevel, level) for image_id, level in rows}


def reports_to_parse(conn: psycopg.Connection, *, force: bool) -> list[tuple[int, FieldReport]]:
    """İddiası henüz çıkarılmamış raporlar (`force` ile hepsi)."""
    where = (
        ""
        if force
        else ("where not exists (select 1 from public.report_claims c where c.report_id = r.id)")
    )
    rows = conn.execute(
        f"select r.id, r.time, r.source::text, r.text from public.field_reports r {where}"
        " order by r.time, r.id"
    ).fetchall()
    return [(rid, FieldReport(t, ReportSource(src), text)) for rid, t, src, text in rows]


def replace_claims(
    conn: psycopg.Connection, report_id: int, claims: list[ReportClaim], model_id: str
) -> None:
    """Raporun iddialarını tek transaction içinde yenileriyle değiştirir."""
    with conn.transaction():
        conn.execute("delete from public.report_claims where report_id = %s", (report_id,))
        for c in claims:
            conn.execute(
                """insert into public.report_claims (
                       report_id, location_type, location, zone_id, vehicle_type,
                       vehicle_count, color, cargo, behavior, claim_type, time_reference,
                       is_verifiable, extractor_model)
                   values (
                       %s, %s,
                       case when %s::float8 is null then null else
                           extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)
                           ::extensions.geography end,
                       (select id from public.zones where name = %s),
                       %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    report_id,
                    c.location_type,
                    c.lon,
                    c.lon,
                    c.lat,
                    c.zone,
                    c.vehicle_type,
                    c.vehicle_count,
                    c.color,
                    c.cargo,
                    c.behavior,
                    c.claim_type,
                    c.time_reference,
                    c.is_verifiable,
                    model_id,
                ),
            )


def fetch_claims(conn: psycopg.Connection) -> list[ClaimRecord]:
    """Saklanmış iddialar, raporlarıyla birlikte."""
    rows = conn.execute(
        f"""select c.id, r.time, r.source::text, r.text,
                   c.location_type::text, {_latlon("c.location")},
                   (select name from public.zones z where z.id = c.zone_id),
                   c.vehicle_type::text, c.vehicle_count, c.color, c.behavior::text,
                   c.claim_type::text, c.time_reference, c.is_verifiable, c.cargo
            from public.report_claims c join public.field_reports r on r.id = c.report_id
            order by r.time, c.id"""
    ).fetchall()
    return [
        ClaimRecord(
            claim_id=row[0],
            report=FieldReport(row[1], ReportSource(row[2]), row[3]),
            claim=ReportClaim(
                location_type=row[4],
                lat=row[5],
                lon=row[6],
                zone=row[7],
                vehicle_type=row[8],
                vehicle_count=row[9],
                color=row[10],
                behavior=row[11],
                claim_type=row[12],
                time_reference=row[13],
                is_verifiable=row[14],
                cargo=row[15],
            ),
        )
        for row in rows
    ]


class ChatRecorder:
    """Sohbet deposu (`ChatStore`): `chat_messages` tablosu."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def history(self, run_id: str) -> list[ChatMessage]:
        rows = self._conn.execute(
            """select role, content, tool_calls from public.chat_messages
               where run_id = %s order by id""",
            (run_id,),
        ).fetchall()
        return [ChatMessage(cast(Role, role), content, tools) for role, content, tools in rows]

    def append(self, run_id: str, message: ChatMessage) -> None:
        with self._conn.transaction():
            self._conn.execute(
                """insert into public.chat_messages (run_id, role, content, tool_calls)
                   values (%s, %s, %s, %s)""",
                (
                    run_id,
                    message.role,
                    message.content,
                    Jsonb(message.tool_calls) if message.tool_calls is not None else None,
                ),
            )
