import { describe, expect, it } from "vitest"

import { approxZoneRadiiM, boundsOf, circleRing, haversineM, toLngLat } from "./geo"

describe("coğrafya yardımcıları", () => {
  it("backend'in [lat, lon] ve {lat, lon} biçimlerini [lon, lat] sırasına çevirir", () => {
    expect(toLngLat([39.92184, 32.85306])).toEqual([32.85306, 39.92184])
    expect(toLngLat({ lat: 39.92531, lon: 32.87183 })).toEqual([32.87183, 39.92531])
  })

  it("referans örnek: img_000860'taki kamyon üsse ~1,6 km", () => {
    const base = toLngLat([39.92184, 32.85306])
    const truck = toLngLat([39.92531, 32.87183])

    expect(haversineM(base, truck)).toBeCloseTo(1647, -1)
  })

  it("yaklaşık bölge yarıçapı en yakın komşu merkezin yarı uzaklığı", () => {
    const a: [number, number] = [32.85, 39.92]
    const b: [number, number] = [32.87, 39.92]
    const far: [number, number] = [32.95, 39.92]

    const [ra, rb, rFar] = approxZoneRadiiM([a, b, far])

    expect(ra).toBeCloseTo(haversineM(a, b) / 2, 3)
    expect(rb).toBeCloseTo(haversineM(a, b) / 2, 3)
    expect(rFar).toBeCloseTo(haversineM(b, far) / 2, 3)
  })

  it("daire halkası kapalıdır ve her noktası merkezden yarıçap kadar uzaktadır", () => {
    const center: [number, number] = [32.85306, 39.92184]
    const ring = circleRing(center, 3000, 32)

    expect(ring[0]).toEqual(ring.at(-1))
    for (const p of ring) expect(haversineM(center, p)).toBeCloseTo(3000, -1)
  })

  it("noktaları kapsayan kutu", () => {
    expect(boundsOf([[1, 5], [3, 2], [2, 9]])).toEqual([[1, 2], [3, 9]])
  })
})
