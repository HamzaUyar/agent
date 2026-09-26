"""Sohbet agent'ının salt okuma araçları.

Bütün araçlar aktif değerlendirmenin çekim anıyla sınırlıdır (ADR-0001): çekim anından
sonraki bir kayıt ya da rapor, varlığı dahil, görünmez. Bu yüzden sonraki bir iddia
sorulduğunda "bulunamadı" denir; "var ama gösterilemez" demek varlığını ele verirdi.
Araçlar hata fırlatmaz; sorun olursa `{"hata": ...}` döndürür ki model düzeltebilsin.
"""

from collections.abc import Callable
from datetime import time
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.core.rules import RiskRules, default_rules
from app.data_package import format_hhmm, parse_hhmm
from app.db.repositories import DataRepository
from app.pipelines.geo import distance_m, in_footprint, nearest_zone
from app.pipelines.motion import analyze_motion, positions_at
from app.schemas.api import Brief
from app.schemas.domain import GeoPoint, ImageMeta

EvaluateImage = Callable[[str], Brief]


class ContactHistoryArgs(BaseModel):
    track_id: str = Field(description="Track kimliği, ör. T0122")


class ReportSearchArgs(BaseModel):
    lat: float | None = Field(None, description="Arama merkezi enlemi")
    lon: float | None = Field(None, description="Arama merkezi boylamı")
    yaricap_m: float = Field(500, description="Merkeze en fazla uzaklık (m)")
    bolge: str | None = Field(None, description="Bölge adı, ör. Dogu Yolu")
    baslangic: str | None = Field(None, description="En erken rapor saati (SS:DD)")
    bitis: str | None = Field(None, description="En geç rapor saati (SS:DD)")


class ReportDecisionArgs(BaseModel):
    claim_id: int = Field(description="İddia kimliği (brief'teki claim_id)")


class EvaluateImageArgs(BaseModel):
    image_id: str = Field(description="Görüntü kimliği, ör. img_000100")


class TrackFramesArgs(BaseModel):
    track_id: str = Field(description="Track kimliği, ör. T0122")


TOOLS: dict[str, tuple[type[BaseModel], str]] = {
    "temas_gecmisi": (
        ContactHistoryArgs,
        "Bir track'in çekim anına kadarki konum geçmişi, hareket eğilimi, hızı ve duraklamaları.",
    ),
    "raporlari_ara": (
        ReportSearchArgs,
        "Çekim anına kadarki saha raporlarını konuma, bölgeye ya da saat aralığına göre arar.",
    ),
    "rapor_degerlendirmesi": (
        ReportDecisionArgs,
        "Bir iddianın bu değerlendirmede neden kabul ya da reddedildiğini açıklar.",
    ),
    "goruntu_degerlendir": (
        EvaluateImageArgs,
        "Çekim saati aktif görüntüden önce olan başka bir görüntüyü değerlendirir.",
    ),
    "track_diger_goruntulerde": (
        TrackFramesArgs,
        "Bir track'in çekim anına kadarki hangi görüntülerin alanında göründüğünü bulur.",
    ),
}


def _clip(value: str | None, now: time) -> time | None:
    if value is None:
        return None
    t = parse_hhmm(value)
    return min(t, now)


class ChatTools:
    def __init__(
        self,
        repo: DataRepository,
        image: ImageMeta,
        brief: Brief,
        *,
        evaluate_image: EvaluateImage,
        rules: RiskRules | None = None,
    ) -> None:
        self._repo = repo
        self._image = image
        self._now = image.capture_time
        self._brief = brief
        self._evaluate_image = evaluate_image
        self._rules = rules or default_rules()

    def specs(self) -> list[dict[str, Any]]:
        """OpenAI biçiminde araç tanımları."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": model.model_json_schema(),
                },
            }
            for name, (model, description) in TOOLS.items()
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in TOOLS:
            return {"hata": f"bilinmeyen araç: {name}"}
        model, _ = TOOLS[name]
        try:
            args = model.model_validate(arguments)
        except ValidationError as exc:
            return {"hata": f"geçersiz argüman: {exc.errors()[0]['msg']}"}
        try:
            result: dict[str, Any] = getattr(self, f"_{name}")(args)
        except ValueError as exc:
            return {"hata": str(exc)}
        return result

    # --- araçlar ------------------------------------------------------------------

    def _temas_gecmisi(self, args: ContactHistoryArgs) -> dict[str, Any]:
        history = self._repo.track_history(args.track_id, until=self._now)
        if not history:
            return {"hata": f"{args.track_id} için {format_hhmm(self._now)} öncesine ait kayıt yok"}
        base = self._repo.base().location
        motion = analyze_motion(
            history, base, self._now, self._repo.zones(), self._rules.trend, self._rules.motion
        )
        return {
            "track_id": args.track_id,
            "as_of": format_hhmm(self._now),
            "points": [
                {
                    "time": format_hhmm(p.time),
                    "lat": round(p.location.lat, 6),
                    "lon": round(p.location.lon, 6),
                    "distance_to_base_m": round(distance_m(p.location, base)),
                }
                for p in history
            ],
            "trend": motion.trend,
            "recent_speed_mps": round(motion.recent_speed_mps, 1),
            "heading_deg": round(motion.heading_deg) if motion.heading_deg is not None else None,
            "total_distance_m": round(motion.total_distance_m),
            "stops": [
                {"start": format_hhmm(s.start), "minutes": s.minutes, "zone": s.zone}
                for s in motion.stops
            ],
            "zones_passed": motion.zones_passed,
        }

    def _raporlari_ara(self, args: ReportSearchArgs) -> dict[str, Any]:
        since = _clip(args.baslangic, self._now)
        until = _clip(args.bitis, self._now) or self._now
        center: GeoPoint | None = None
        if args.lat is not None and args.lon is not None:
            center = GeoPoint(args.lat, args.lon)
        reports = []
        for r in self._repo.claims_until(until):
            if since is not None and r.report.time < since:
                continue
            c = r.claim
            if args.bolge is not None and c.zone != args.bolge:
                continue
            if center is not None:
                if c.lat is None or c.lon is None:
                    continue
                if distance_m(center, GeoPoint(c.lat, c.lon)) > args.yaricap_m:
                    continue
            reports.append(
                {
                    "claim_id": r.claim_id,
                    "time": format_hhmm(r.report.time),
                    "source": r.report.source.value,
                    "text": r.report.text,
                    "claim_type": c.claim_type,
                    "lat": c.lat,
                    "lon": c.lon,
                    "zone": c.zone,
                }
            )
        return {"as_of": format_hhmm(self._now), "reports": reports}

    def _rapor_degerlendirmesi(self, args: ReportDecisionArgs) -> dict[str, Any]:
        for f in self._brief.report_findings:
            if f.claim_id == args.claim_id:
                return f.model_dump()
        if any(r.claim_id == args.claim_id for r in self._repo.claims_until(self._now)):
            return {
                "claim_id": args.claim_id,
                "not": "Bu iddia bu değerlendirmede ele alınmadı: görüntüyle ilgili değil ya da "
                "zaman penceresinin dışında.",
            }
        return {"hata": f"{args.claim_id} kimlikli iddia bulunamadı"}

    def _goruntu_degerlendir(self, args: EvaluateImageArgs) -> dict[str, Any]:
        image = self._repo.get_image(args.image_id)
        if image is None or image.capture_time > self._now:
            # Sonraki bir kare de yokmuş gibi davranılır (ADR-0001).
            return {
                "hata": f"{args.image_id}: {format_hhmm(self._now)} öncesine ait böyle bir "
                "görüntü yok"
            }
        brief = self._evaluate_image(args.image_id)
        return {
            "image_id": brief.image_id,
            "zone": brief.zone,
            "capture_time": brief.capture_time,
            "risk_level": brief.risk_level,
            "recommended_action": brief.recommended_action,
            "contacts": [
                {
                    "track_id": c.track_id,
                    "kind": c.kind,
                    "type": c.effective_label,
                    "level": c.final_level,
                }
                for c in brief.contacts
            ],
        }

    def _track_diger_goruntulerde(self, args: TrackFramesArgs) -> dict[str, Any]:
        zones = self._repo.zones()
        frames = []
        for frame in self._repo.list_images():
            if frame.capture_time > self._now:
                continue
            points = self._repo.track_history(args.track_id, until=frame.capture_time)
            if not points:
                continue
            here = positions_at(points, frame.capture_time)
            position = next((p for p in here if p.track_id == args.track_id), None)
            if position is not None and in_footprint(frame, position.location):
                frames.append(
                    {
                        "image_id": frame.image_id,
                        "capture_time": format_hhmm(frame.capture_time),
                        "zone": nearest_zone(frame.corners.center, zones).name,
                    }
                )
        return {"track_id": args.track_id, "as_of": format_hhmm(self._now), "frames": frames}
