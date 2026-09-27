"""Arayüz için veri listeleri."""

from collections import defaultdict
from datetime import time
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response

from app.api.stores import Stores
from app.core.config import get_settings
from app.core.rules import default_rules, rules_version
from app.data_package import IMAGES_DIR, find_image_file, format_hhmm
from app.db.repositories import DataRepository
from app.pipelines.geo import distance_to_footprint_m, nearest_zone
from app.schemas.api import (
    BaseInfo,
    CornerCoordinates,
    ImageDetail,
    ImageSummary,
    Pair,
    RoutePoint,
    TrackOverview,
    ZoneInfo,
    ZonesResponse,
)
from app.schemas.domain import GeoPoint, ImageMeta, RiskLevel, TrackPoint
from app.storage import StorageError, SupabaseStorage

router = APIRouter(tags=["data"])

IMAGE_CACHE_CONTROL = "public, max-age=86400"
"""Veri paketi demo boyunca değişmez; önizlemeler bir gün önbellekte kalabilir."""


def get_repository(request: Request) -> DataRepository:
    repo: DataRepository = request.app.state.repository
    return repo


def get_images_dir() -> Path:
    return get_settings().resolved_data_dir / IMAGES_DIR


def get_image_storage(request: Request) -> SupabaseStorage | None:
    """Görüntü dosyalarının bucket'ı; `None` ise dosyalar yerel klasörden (ağsız demo)."""
    storage: SupabaseStorage | None = getattr(request.app.state, "image_storage", None)
    return storage


RepoDep = Annotated[DataRepository, Depends(get_repository)]
ImagesDirDep = Annotated[Path, Depends(get_images_dir)]
ImageStorageDep = Annotated[SupabaseStorage | None, Depends(get_image_storage)]


def get_stores(request: Request) -> Stores:
    stores: Stores = request.app.state.stores
    return stores


StoresDep = Annotated[Stores, Depends(get_stores)]

TRACK_IMAGE_REACH_M = 50.0
"""Track'in bittiği görüntü: son konumu karesine en fazla bu kadar uzak. Değerlendirme
yalnızca 6 m'ye kadarkileri temas sayar; daha uzakta bitenin görüntüsü bilinir, seviyesi yok."""


def _latest_levels(stores: Stores) -> dict[str, RiskLevel]:
    """Güncel kural sürümüyle yapılmış son değerlendirmelerin seviyesi."""
    with stores.open() as (runs, _):
        return runs.latest_levels(rules_version(default_rules()))


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


@router.get("/tracks", response_model=list[TrackOverview])
def list_tracks(repo: RepoDep, stores: StoresDep) -> list[TrackOverview]:
    """Bütün track'ler, kayıtları olduğu gibi. Her track'in bittiği görüntü, o görüntünün son
    tamamlanmış değerlendirmesindeki temasın seviyesi ve sınıfıyla. Hiçbir görüntünün teması
    olmayan (görüntüsüz) track'in seviyesi ve kısa değerlendirmesi `scripts.assess_tracks`'in
    kaydından okunur. Hesap yapılmaz, LLM ya da tespit çağrılmaz; değerlendirmesi olmayan
    track'in seviyesi `None` kalır."""
    by_track: dict[str, list[TrackPoint]] = defaultdict(list)
    for point in repo.track_points_between(time(0, 0), time(23, 59)):
        by_track[point.track_id].append(point)
    with stores.open() as (runs, _):
        contacts_of = runs.latest_contacts(rules_version(default_rules()))
        unframed_of = runs.latest_track_assessments()
    images_at: dict[time, list[ImageMeta]] = defaultdict(list)
    for meta in repo.list_images():
        images_at[meta.capture_time].append(meta)

    overviews: list[TrackOverview] = []
    for track_id in sorted(by_track):
        points = by_track[track_id]
        last = points[-1]
        near = [
            (distance_to_footprint_m(meta, last.location), meta)
            for meta in images_at.get(last.time, [])
        ]
        # Track'in bittiği görüntü: son kaydın saatinde çekilmiş, son konumu karesinde olan.
        distance, ending = min(near, key=lambda d: d[0]) if near else (0.0, None)
        if distance > TRACK_IMAGE_REACH_M:
            ending = None
        contacts = contacts_of.get(ending.image_id, []) if ending is not None else []
        contact = next((c for c in contacts if c.track_id == track_id), None)
        assessed = unframed_of.get(track_id) if contact is None else None
        overviews.append(
            TrackOverview(
                track_id=track_id,
                start=format_hhmm(points[0].time),
                end=format_hhmm(last.time),
                points=[
                    RoutePoint(lat=p.location.lat, lon=p.location.lon, time=format_hhmm(p.time))
                    for p in points
                ],
                image_id=ending.image_id if ending is not None else None,
                level=contact.final_level if contact else (assessed.level if assessed else None),
                label=(contact.effective_label or contact.label) if contact else None,
                kind=contact.kind if contact else None,
                unframed=assessed is not None,
                assessment=assessed.assessment if assessed else None,
            )
        )
    return overviews


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
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}, "description": "Görüntü dosyası"},
        404: {"description": "Görüntü veri setinde yok ya da dosyası bulunamadı"},
        502: {"description": "Storage'a ulaşılamadı"},
    },
)
def get_image_file(
    image_id: str, repo: RepoDep, images_dir: ImagesDirDep, storage: ImageStorageDep
) -> Response:
    """Görüntü dosyası: Supabase modunda `images.file_path` ile bucket'tan, ağsız demoda
    yerel klasörden. Yol veri setindeki kayıttan kurulur, istekten gelen yol kullanılmaz."""
    m = _image_or_404(repo, image_id)
    headers = {"Cache-Control": IMAGE_CACHE_CONTROL}
    if storage is None:
        path = find_image_file(images_dir, m.image_id)
        if path is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Görüntü dosyası bulunamadı: {image_id}"
            )
        return FileResponse(path, headers=headers)
    if not m.file_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Görüntü dosyası bulunamadı: {image_id}")
    try:
        data, content_type = storage.fetch(m.file_path)
    except StorageError as exc:
        if exc.not_found:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Görüntü dosyası bulunamadı: {image_id}"
            ) from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Storage'a ulaşılamadı") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Storage'a ulaşılamadı") from exc
    return Response(data, media_type=content_type, headers=headers)
