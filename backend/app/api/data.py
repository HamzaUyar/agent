"""Arayüz için veri listeleri."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.api.stores import Stores
from app.core.config import get_settings
from app.data_package import IMAGES_DIR, find_image_file, format_hhmm
from app.db.repositories import DataRepository
from app.pipelines.geo import nearest_zone
from app.schemas.api import (
    BaseInfo,
    CornerCoordinates,
    ImageDetail,
    ImageSummary,
    Pair,
    ZoneInfo,
    ZonesResponse,
)
from app.schemas.domain import GeoPoint, ImageMeta, RiskLevel

router = APIRouter(tags=["data"])

IMAGE_CACHE_CONTROL = "public, max-age=86400"
"""Veri paketi demo boyunca değişmez; önizlemeler bir gün önbellekte kalabilir."""


def get_repository(request: Request) -> DataRepository:
    repo: DataRepository = request.app.state.repository
    return repo


def get_images_dir() -> Path:
    return get_settings().resolved_data_dir / IMAGES_DIR


RepoDep = Annotated[DataRepository, Depends(get_repository)]
ImagesDirDep = Annotated[Path, Depends(get_images_dir)]


def get_stores(request: Request) -> Stores:
    stores: Stores = request.app.state.stores
    return stores


def _latest_levels(stores: Stores) -> dict[str, RiskLevel]:
    with stores.open() as (runs, _):
        return runs.latest_levels()


def _pair(p: GeoPoint) -> Pair:
    return (p.lat, p.lon)


def _image_or_404(repo: DataRepository, image_id: str) -> ImageMeta:
    image = repo.get_image(image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Görüntü veri setinde yok: {image_id}")
    return image


@router.get("/zones", response_model=ZonesResponse)
def get_zones(repo: RepoDep) -> ZonesResponse:
    """Üs ve bölge merkezleri. Bölgelerin sınırı veride yok."""
    base = repo.base()
    return ZonesResponse(
        base=BaseInfo(name=base.name, lat=base.location.lat, lon=base.location.lon),
        zones=[ZoneInfo(name=z.name, center=_pair(z.center)) for z in repo.zones()],
    )


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


@router.get(
    "/images/{image_id}",
    response_model=ImageDetail,
    responses={404: {"description": "Görüntü veri setinde yok"}},
)
def get_image(image_id: str, repo: RepoDep) -> ImageDetail:
    """Görüntünün boyutu, çekim saati, köşe koordinatları, merkezi ve bölgesi."""
    m = _image_or_404(repo, image_id)
    c = m.corners
    return ImageDetail(
        image_id=m.image_id,
        width_px=m.width_px,
        height_px=m.height_px,
        capture_time=format_hhmm(m.capture_time),
        corner_coordinates=CornerCoordinates(
            top_left=_pair(c.top_left),
            top_right=_pair(c.top_right),
            bottom_left=_pair(c.bottom_left),
            bottom_right=_pair(c.bottom_right),
        ),
        center=_pair(c.center),
        zone=nearest_zone(c.center, repo.zones()).name,
    )


@router.get(
    "/images/{image_id}/file",
    response_class=FileResponse,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}, "description": "Görüntü dosyası"},
        404: {"description": "Görüntü veri setinde yok ya da dosyası bulunamadı"},
    },
)
def get_image_file(image_id: str, repo: RepoDep, images_dir: ImagesDirDep) -> FileResponse:
    """Görüntü dosyası. Ad veri setindeki kimlikten kurulur, istekten gelen yol kullanılmaz."""
    m = _image_or_404(repo, image_id)
    path = find_image_file(images_dir, m.image_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Görüntü dosyası bulunamadı: {image_id}")
    return FileResponse(path, headers={"Cache-Control": IMAGE_CACHE_CONTROL})
