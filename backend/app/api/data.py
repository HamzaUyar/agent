"""Arayüz için veri listeleri."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.stores import Stores
from app.data_package import format_hhmm
from app.db.repositories import DataRepository
from app.pipelines.geo import nearest_zone
from app.schemas.api import ImageSummary
from app.schemas.domain import RiskLevel

router = APIRouter(tags=["data"])


def get_repository(request: Request) -> DataRepository:
    repo: DataRepository = request.app.state.repository
    return repo


RepoDep = Annotated[DataRepository, Depends(get_repository)]


def get_stores(request: Request) -> Stores:
    stores: Stores = request.app.state.stores
    return stores


def _latest_levels(stores: Stores) -> dict[str, RiskLevel]:
    with stores.open() as (runs, _):
        return runs.latest_levels()


@router.get("/images", response_model=list[ImageSummary])
def list_images(repo: RepoDep, request: Request) -> list[ImageSummary]:
    """Veri setindeki görüntüler: bölge, çekim saati ve varsa son değerlendirmenin seviyesi."""
    levels = _latest_levels(get_stores(request))
    zones = repo.zones()
    return [
        ImageSummary(
            image_id=m.image_id,
            zone=nearest_zone(m.corners.center, zones).name,
            capture_time=format_hhmm(m.capture_time),
            last_risk_level=levels.get(m.image_id),
        )
        for m in repo.list_images()
    ]
