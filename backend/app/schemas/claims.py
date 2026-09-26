"""İddia: bir Rapor'dan çıkarılmış tek, kontrol edilebilir önerme.

Aynı model hem LLM'den istenen yapılandırılmış çıktının şeması hem de
normalizasyondan sonraki iddianın kendisidir.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.domain import CargoState, FieldReport

LocationType = Literal["coordinate", "zone", "none"]
ClaimVehicleType = Literal["car", "van", "truck", "bus", "heavy", "light", "unknown"]
ClaimBehavior = Literal[
    "stationary", "moving", "transit", "approaching", "receding", "normal_traffic", "unknown"
]
ClaimType = Literal["observation", "friendly_claim", "threat_warning", "rumor", "irrelevant"]


class ReportClaim(BaseModel):
    location_type: LocationType = Field(
        description="Konum nasıl verilmiş: koordinat, bölge adı ya da hiç"
    )
    lat: float | None = Field(description="Enlem (metinde koordinat varsa)")
    lon: float | None = Field(description="Boylam (metinde koordinat varsa)")
    zone: str | None = Field(description="Metinde geçen bölge adı")
    vehicle_type: ClaimVehicleType | None = Field(
        description="Araç tipi; 'agir arac' → heavy, 'hafif arac' → light"
    )
    vehicle_count: int | None
    color: str | None = Field(description="Metinde geçen renk, olduğu gibi")
    cargo: CargoState | None = Field(
        default=None, description="Yük durumu: 'yuklu' → loaded, 'bos' → empty; yazmıyorsa boş"
    )
    behavior: ClaimBehavior | None
    claim_type: ClaimType = Field(
        description="observation: gözlem; friendly_claim: dost olduğu iddiası; "
        "threat_warning: tehdit uyarısı; rumor: doğrulanmamış ihbar/söylenti; "
        "irrelevant: üs güvenliğiyle ilgisiz"
    )
    time_reference: str | None = Field(
        description="Rapor saatinden farklı bir zaman ifadesi (ör. 'dun gece', 'gun icinde')"
    )
    is_verifiable: bool = Field(
        description="Konum ve zaman bir temasla karşılaştırılabilecek kadar belirli mi"
    )


class ParsedReport(BaseModel):
    claims: list[ReportClaim]


@dataclass(frozen=True)
class ClaimRecord:
    """Saklanmış bir iddia ve geldiği rapor."""

    claim_id: int
    report: FieldReport
    claim: ReportClaim
