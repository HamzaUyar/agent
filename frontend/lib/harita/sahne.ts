/**
 * Sahne katmanları: Üs, 1/3 km halkaları, Bölge merkezleri ve yaklaşık bölge alanları.
 * Kaynak `GET /zones`; Bölge'lerin veride sınırı yok, alan yalnızca görsel bir yaklaşıklıktır.
 */
import type { FeatureCollection } from "geojson"

import type { ZonesResponse } from "@/lib/api/types"
import { formatDistance } from "@/lib/format"
import { approxZoneRadiiM, boundsOf, circleRing, toLngLat, type Bounds } from "@/lib/geo"

import type { AreaLayer, MapMarker, MarkerGroup } from "./types"

export const BASE_RINGS_M = [1000, 3000] as const

export type Scene = {
  areas: Record<Extract<AreaLayer, "bolge-alanlari" | "us-halkalari">, FeatureCollection>
  markers: Record<Extract<MarkerGroup, "us" | "bolgeler" | "halka-etiketleri">, MapMarker[]>
  bounds: Bounds
}

export function buildScene({ base, zones }: ZonesResponse): Scene {
  const baseLngLat = toLngLat(base)
  const centers = zones.map((z) => toLngLat(z.center))
  const radii = approxZoneRadiiM(centers)

  const zoneAreas: FeatureCollection = {
    type: "FeatureCollection",
    features: zones.map((zone, i) => ({
      type: "Feature",
      id: i,
      properties: { name: zone.name, radius_m: radii[i], approximate: true },
      geometry: { type: "Polygon", coordinates: [circleRing(centers[i], radii[i])] },
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
        lngLat: centers[i],
        label: zone.name,
        description: `Bölge: ${zone.name} · yaklaşık alan, kesin sınır değil (yarıçap ~${formatDistance(radii[i])})`,
      })),
      "halka-etiketleri": ringLabels,
    },
    // Üs ve bütün Bölge'ler, yaklaşık alanlarıyla birlikte görünsün.
    bounds: boundsOf([baseLngLat, ...centers.flatMap((c, i) => circleRing(c, radii[i], 16))]),
  }
}
