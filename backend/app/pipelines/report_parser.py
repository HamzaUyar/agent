"""KOL C (önceden): raporları LLM ile iddialara ayırır ve kodla normalize eder.

LLM yalnızca metni anlamlandırır; koordinatlar rapor metninden kodla okunur ve
LLM'in verdiğinin yerine geçer, bölge adları bilinen bölgelerle eşlenir.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.data_package import format_hhmm
from app.llm.client import LLMRouter
from app.pipelines.geo import distance_m
from app.schemas.claims import ParsedReport, ReportClaim
from app.schemas.domain import FieldReport, GeoPoint, Zone

TASK = "report_parse"
PROMPT_PATH = Path(__file__).parents[1] / "agent" / "prompts" / "report_parse.md"

COORDINATE = re.compile(r"(\d{1,2}\.\d+)\s*°?\s*N[\s,;/-]+(\d{1,3}\.\d+)\s*°?\s*E", re.IGNORECASE)
_FOLD = str.maketrans("ıİşŞğĞüÜöÖçÇâÂîÎûÛ", "iissgguuooccaaiiuu")


def _fold(name: str) -> str:
    return " ".join(name.translate(_FOLD).lower().split())


def coordinates_in(text: str) -> list[GeoPoint]:
    return [GeoPoint(float(lat), float(lon)) for lat, lon in COORDINATE.findall(text)]


def rounding_error_m(text: str, point: GeoPoint) -> float:
    """Metinde `point`'e karşılık gelen koordinatın yuvarlama payı (m).

    "39.944N 32.863E" 3 ondalıklı: gerçek nokta her eksende ±0,0005° içinde, köşegende
    ~70 m. 5 ondalıklıda pay 1 m'nin altında. Koordinat metinde yoksa 0.
    """
    found = [
        (GeoPoint(float(lat), float(lon)), min(len(lat.split(".")[1]), len(lon.split(".")[1])))
        for lat, lon in COORDINATE.findall(text)
    ]
    if not found:
        return 0.0
    written, decimals = min(found, key=lambda f: distance_m(f[0], point))
    half = 0.5 * 10**-decimals
    return distance_m(written, GeoPoint(written.lat + half, written.lon + half))


@dataclass(frozen=True)
class ParseResult:
    claims: list[ReportClaim]
    model_id: str


class ReportParser:
    def __init__(self, router: LLMRouter, zones: list[Zone]) -> None:
        self._router = router
        self._zones = {_fold(z.name): z.name for z in zones}
        self._system = (
            PROMPT_PATH.read_text(encoding="utf-8")
            + "\nBilinen bölgeler: "
            + (", ".join(z.name for z in zones))
        )

    def parse(self, report: FieldReport) -> ParseResult:
        user = f"Rapor ({format_hhmm(report.time)}, kaynak: {report.source.value}):\n{report.text}"
        parsed, model_id = self._router.complete_json(TASK, self._system, user, ParsedReport)
        coords = coordinates_in(report.text)
        return ParseResult([self._normalize(c, coords) for c in parsed.claims], model_id)

    def _normalize(self, claim: ReportClaim, coords: list[GeoPoint]) -> ReportClaim:
        zone = self._zones.get(_fold(claim.zone)) if claim.zone else None
        lat = lon = None
        # Bölge adı tanınmadıysa metindeki koordinat konumu kurtarır.
        if coords and (claim.location_type != "zone" or zone is None):
            point = coords[0]
            if claim.lat is not None and claim.lon is not None:
                guess = GeoPoint(claim.lat, claim.lon)
                point = min(coords, key=lambda c: distance_m(c, guess))
            lat, lon = point.lat, point.lon

        if lat is not None:
            location_type = "coordinate"
        elif zone is not None:
            location_type = "zone"
        else:
            location_type = "none"

        count = claim.vehicle_count if claim.vehicle_count and claim.vehicle_count > 0 else None
        return claim.model_copy(
            update={
                "location_type": location_type,
                "lat": lat,
                "lon": lon,
                "zone": zone,
                "vehicle_count": count,
            }
        )
