/**
 * Görüntüleme için coğrafya hesapları. Risk hesabı burada yapılmaz; seviye ve bulgular backend'den gelir.
 * Backend `[lat, lon]` ya da `{lat, lon}` verir, harita `[lon, lat]` bekler: dönüşüm yalnızca burada.
 */

export type LatLonPair = readonly [number, number]
export type LngLat = [number, number]
export type Bounds = [LngLat, LngLat]

const EARTH_RADIUS_M = 6_371_008.8
const rad = (deg: number) => (deg * Math.PI) / 180

/** Backend'in `[lat, lon]` çiftini ya da `{lat, lon}` nesnesini haritanın `[lon, lat]` sırasına çevirir. */
export function toLngLat(point: LatLonPair | { lat: number; lon: number }): LngLat {
  return "lat" in point ? [point.lon, point.lat] : [point[1], point[0]]
}

/** İki nokta arası büyük çember uzaklığı (metre). */
export function haversineM(a: LngLat, b: LngLat): number {
  const dLat = rad(b[1] - a[1])
  const dLon = rad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))
}

/**
 * Yaklaşık bölge alanının yarıçapı: en yakın komşu Bölge merkezine uzaklığın yarısı.
 * Veride sınır yok; bu yalnızca görsel bir yaklaşıklıktır ve komşu daireler birbirine değer ama taşmaz.
 */
export function approxZoneRadiiM(centers: LngLat[]): number[] {
  return centers.map((c, i) => {
    let nearest = Infinity
    centers.forEach((other, j) => {
      if (j !== i) nearest = Math.min(nearest, haversineM(c, other))
    })
    return Number.isFinite(nearest) ? nearest / 2 : 0
  })
}

/** Merkez çevresinde `radiusM` yarıçaplı daireyi kapalı bir halka olarak döndürür. */
export function circleRing(center: LngLat, radiusM: number, steps = 64): LngLat[] {
  const [lon, lat] = center
  const dLat = radiusM / EARTH_RADIUS_M
  const dLon = radiusM / (EARTH_RADIUS_M * Math.cos(rad(lat)))
  const ring: LngLat[] = []
  for (let i = 0; i <= steps; i++) {
    const t = (2 * Math.PI * i) / steps
    ring.push([lon + (dLon * Math.cos(t) * 180) / Math.PI, lat + (dLat * Math.sin(t) * 180) / Math.PI])
  }
  return ring
}

/** Noktaları kapsayan en küçük kutu: [güneybatı, kuzeydoğu]. */
export function boundsOf(points: LngLat[]): Bounds {
  const lons = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ]
}
