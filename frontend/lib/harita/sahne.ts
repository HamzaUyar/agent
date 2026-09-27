/**
 * Sahne katmanları: Üs, 1/3 km halkaları, Bölge merkezleri ve yaklaşık bölge alanları.
 * Kaynak `GET /zones`; Bölge'lerin veride sınırı yok, alan yalnızca görsel bir yaklaşıklıktır:
 * Üs merkezli pasta dilimleri. Her Bölge, Üs'ten bakınca merkezine en yakın yön aralığını alır
 * (komşu merkezlerin yönlerinin ortası sınırdır). Dilimler 1 km halkasından başlar; Üs'ün dairesi boş kalır.
 */
import type { FeatureCollection } from "geojson"

import type { ImageDetail, ZonesResponse } from "@/lib/api/types"
import { formatDistance } from "@/lib/format"
import {
  approxZoneRadiiM,
  bearingDeg,
  boundsOf,
  circleRing,
  haversineM,
  sectorRing,
  toLngLat,
  type Bounds,
  type LngLat,
} from "@/lib/geo"

import type { AreaLayer, MapMarker, MarkerGroup } from "./types"

export const BASE_RINGS_M = [1000, 3000] as const
/** Kapsanması istenen noktanın dilim kenarına olan en az payı. */
const COVER_MARGIN_M = 150

export type Scene = {
  areas: Record<Extract<AreaLayer, "bolge-alanlari" | "us-halkalari">, FeatureCollection>
  markers: Record<Extract<MarkerGroup, "us" | "bolgeler" | "halka-etiketleri">, MapMarker[]>
  bounds: Bounds
}

/** Her Bölge'nin dilimi: yön aralığı [from, to) ve yön sırasındaki yeri (dolgu sırayla değişir). */
function zoneSectors(base: LngLat, centers: LngLat[]) {
  const bearings = centers.map((c) => bearingDeg(base, c))
  const order = bearings.map((_, i) => i).sort((a, b) => bearings[a] - bearings[b])
  const sectors = new Array<{ from: number; to: number; parity: number }>(centers.length)
  order.forEach((i, k) => {
    const prev = bearings[order[(k - 1 + order.length) % order.length]]
    const next = bearings[order[(k + 1) % order.length]]
    const own = bearings[i]
    // Komşuya olan açı farkı saat yönünde ölçülür; tek Bölge varsa dilim tam daire.
    const before = order.length > 1 ? ((own - prev + 360) % 360) / 2 : 180
    const after = order.length > 1 ? ((next - own + 360) % 360) / 2 : 180
    sectors[i] = { from: (own - before + 360) % 360, to: (own + after) % 360, parity: k % 2 }
  })
  return sectors
}

/**
 * `selectedZone`: seçili karenin Bölge'si; dilimi vurgulanır.
 * `cover`: dilimlerin mutlaka kapsaması gereken noktalar (seçili karenin köşeleri).
 */
export function buildScene(
  { base, zones }: ZonesResponse,
  selectedZone: string | null = null,
  cover: LngLat[] = [],
): Scene {
  const baseLngLat = toLngLat(base)
  const centers = zones.map((z) => toLngLat(z.center))
  const radii = approxZoneRadiiM(centers)
  const sectors = zoneSectors(baseLngLat, centers)
  // Bütün dilimler aynı dış yarıçapta. Backend kareyi en yakın Bölge merkezine atar, yani Bölge dışa
  // doğru sınırsızdır; kareler merkezden komşu merkez aralığı kadar (yaklaşık yarıçapın iki katı) uzağa
  // düşebilir. Dilim bu kadar uzanır; ayrıca verilen noktaları (seçili kare) her durumda kapsar.
  const outerM = Math.max(
    BASE_RINGS_M[1],
    ...centers.map((c, i) => haversineM(baseLngLat, c) + 2 * radii[i]),
    ...cover.map((p) => haversineM(baseLngLat, p) + COVER_MARGIN_M),
  )
  const innerM = BASE_RINGS_M[0]

  const zoneAreas: FeatureCollection = {
    type: "FeatureCollection",
    features: zones.map((zone, i) => ({
      type: "Feature",
      id: i,
      properties: {
        name: zone.name,
        approximate: true,
        parity: sectors[i].parity,
        selected: zone.name === selectedZone,
      },
      geometry: {
        type: "Polygon",
        coordinates: [sectorRing(baseLngLat, innerM, outerM, sectors[i].from, sectors[i].to)],
      },
    })),
  }

  const rings: FeatureCollection = {
    type: "FeatureCollection",
    features: BASE_RINGS_M.map((radius) => ({
      type: "Feature",
      properties: { radius_m: radius },
      geometry: { type: "LineString", coordinates: circleRing(baseLngLat, radius) },
    })),
  }

  // Halka etiketi halkanın kuzey ucunda: halka noktalarının en kuzeydekisi.
  const ringLabels: MapMarker[] = BASE_RINGS_M.map((radius) => {
    const top = circleRing(baseLngLat, radius).reduce((a, b) => (b[1] > a[1] ? b : a))
    return { id: `halka-${radius}`, lngLat: top, label: formatDistance(radius) }
  })

  return {
    areas: { "bolge-alanlari": zoneAreas, "us-halkalari": rings },
    markers: {
      us: [{ id: "us", lngLat: baseLngLat, label: base.name, description: `Üs: ${base.name}` }],
      bolgeler: zones.map((zone, i) => ({
        id: zone.name,
        ...(zone.name === selectedZone ? { variant: ["secili"] } : {}),
        lngLat: centers[i],
        label: zone.name,
        description: `Bölge: ${zone.name} · yaklaşık alan (Üs'ten yön dilimi), kesin sınır değil`,
      })),
      "halka-etiketleri": ringLabels,
    },
    // Üs ve bütün Bölge dilimleri görünsün.
    bounds: boundsOf(circleRing(baseLngLat, outerM, 16)),
  }
}

/** Karenin çevresinde bırakılan bağlam: ayak izi ~150 m, harita bölgeyi de göstersin. */
const FOOTPRINT_CONTEXT_M = 1200

/** Seçili karenin ayak izi (4 köşe) ve haritanın yaklaşacağı kutu. */
export function buildFootprint(image: ImageDetail): { area: FeatureCollection; bounds: Bounds } {
  const c = image.corner_coordinates
  const ring = [c.top_left, c.top_right, c.bottom_right, c.bottom_left, c.top_left].map(toLngLat)
  const center = toLngLat(image.center)
  return {
    area: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { image_id: image.image_id },
          geometry: { type: "Polygon", coordinates: [ring] },
        },
      ],
    },
    bounds: boundsOf([...ring, ...circleRing(center, FOOTPRINT_CONTEXT_M, 16)]),
  }
}
