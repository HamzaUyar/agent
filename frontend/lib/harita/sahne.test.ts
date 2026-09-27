import type { Polygon } from "geojson"
import { describe, expect, it } from "vitest"

import type { ImageDetail, ZonesResponse } from "@/lib/api/types"
import { toLngLat, type LngLat } from "@/lib/geo"

import imageDetails from "../../tests/fixtures/image_details.json"
import zones from "../../tests/fixtures/zones.json"
import { buildScene } from "./sahne"

/** Işın atma: nokta halkanın içinde mi. */
function inside([x, y]: LngLat, ring: number[][]): boolean {
  let hit = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit
  }
  return hit
}

const details = Object.values(imageDetails as unknown as Record<string, ImageDetail>)
const sectorOf = (scene: ReturnType<typeof buildScene>, zone: string) =>
  (scene.areas["bolge-alanlari"].features.find((f) => f.properties!.name === zone)!.geometry as Polygon).coordinates[0]

describe("yaklaşık bölge alanı", () => {
  it("veri setindeki her karenin dört köşesi kendi Bölge diliminin içinde", () => {
    const scene = buildScene(zones as unknown as ZonesResponse)
    const outside = details.flatMap((image) =>
      Object.entries(image.corner_coordinates)
        .filter(([, corner]) => !inside(toLngLat(corner), sectorOf(scene, image.zone)))
        .map(([name]) => `${image.image_id} ${name}`),
    )
    expect(outside).toEqual([])
  })

  it("verilen noktalar (seçili kare) dilimin dışına düşse bile dilim onları kapsayacak kadar uzar", () => {
    const base = toLngLat(zones.base)
    // Doğu Yolu yönünde, Üs'ten ~8 km.
    const far: LngLat = [base[0] + 0.094, base[1]]
    expect(inside(far, sectorOf(buildScene(zones as unknown as ZonesResponse), "Dogu Yolu"))).toBe(false)
    expect(inside(far, sectorOf(buildScene(zones as unknown as ZonesResponse, null, [far]), "Dogu Yolu"))).toBe(true)
  })
})
