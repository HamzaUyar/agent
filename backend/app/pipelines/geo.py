"""Coğrafi hesaplar: mesafe ve en yakın bölge."""

from math import asin, atan2, cos, degrees, radians, sin, sqrt

from app.schemas.domain import GeoPoint, ImageMeta, Zone

EARTH_RADIUS_M = 6_371_008.8


def pixel_to_geo(image: ImageMeta, x: float, y: float) -> GeoPoint:
    """Pikseli köşe koordinatlarıyla doğrusal oranlayarak konuma çevirir.

    Kare kuzeye hizalı kabul edilir: üst kenar kuzey, sol kenar batı.
    """
    c = image.corners
    lon = c.top_left.lon + (x / image.width_px) * (c.top_right.lon - c.top_left.lon)
    lat = c.top_left.lat - (y / image.height_px) * (c.top_left.lat - c.bottom_left.lat)
    return GeoPoint(lat=lat, lon=lon)


def distance_m(a: GeoPoint, b: GeoPoint) -> float:
    """İki nokta arasındaki büyük daire mesafesi (haversine), metre."""
    dlat = radians(b.lat - a.lat)
    dlon = radians(b.lon - a.lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))


def bearing_deg(a: GeoPoint, b: GeoPoint) -> float:
    """`a`'dan `b`'ye başlangıç yönü, derece (kuzey = 0, saat yönünde)."""
    lat1, lat2 = radians(a.lat), radians(b.lat)
    dlon = radians(b.lon - a.lon)
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360


def in_footprint(image: ImageMeta, point: GeoPoint) -> bool:
    """Nokta görüntünün kapladığı alanın içinde mi (kuzeye hizalı dikdörtgen kabulü)."""
    c = image.corners
    lats = (c.top_left.lat, c.bottom_left.lat)
    lons = (c.top_left.lon, c.top_right.lon)
    return min(lats) <= point.lat <= max(lats) and min(lons) <= point.lon <= max(lons)


def distance_to_footprint_m(image: ImageMeta, point: GeoPoint) -> float:
    """Noktanın görüntünün kapladığı alana uzaklığı; içindeyse 0."""
    c = image.corners
    lats = sorted((c.top_left.lat, c.bottom_left.lat))
    lons = sorted((c.top_left.lon, c.top_right.lon))
    edge = GeoPoint(min(max(point.lat, lats[0]), lats[1]), min(max(point.lon, lons[0]), lons[1]))
    return distance_m(point, edge)


def nearest_zone(point: GeoPoint, zones: list[Zone]) -> Zone:
    """Merkezi `point`'e en yakın bölge."""
    if not zones:
        raise ValueError("Bölge listesi boş")
    return min(zones, key=lambda z: distance_m(point, z.center))
