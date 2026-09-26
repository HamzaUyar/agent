import { describe, expect, it } from "vitest"

import type { Brief } from "@/lib/api/types"
import events from "@/tests/fixtures/img_000860.events.json"
import zones from "@/tests/fixtures/zones.json"

import { bySeverity, contactKey, distanceSeries, keyedContacts, toPixel } from "./temas"

const brief = events.at(-1)!.data as unknown as Brief

describe("Temas yardımcıları", () => {
  it("anahtar: track'li Temas'ta track_id, kayıt dışında sırası", () => {
    expect(brief.contacts.map(contactKey)).toEqual(["T0122", "kayit-disi-1", "T0032"])
  })

  it("seviyeye göre sıralama (yüksekten düşüğe)", () => {
    expect(keyedContacts(brief).sort(bySeverity).map((k) => k.key)).toEqual(["T0122", "T0032", "kayit-disi-1"])
  })

  it("kutu merkezinin konumu tekrar piksele çevrilince kutu merkezine döner (referans: 756, 301)", () => {
    const image = {
      image_id: "img_000860",
      width_px: 960,
      height_px: 540,
      capture_time: "14:10",
      corner_coordinates: {
        top_left: [39.925651, 32.870729] as [number, number],
        top_right: [39.925651, 32.872131] as [number, number],
        bottom_left: [39.925045, 32.870729] as [number, number],
        bottom_right: [39.925045, 32.872131] as [number, number],
      },
      center: [39.925348, 32.87143] as [number, number],
      zone: "Dogu Yolu",
    }
    const { x, y } = toPixel(image, brief.contacts[0].location.lat, brief.contacts[0].location.lon)
    expect(x).toBeCloseTo(756, 0)
    expect(y).toBeCloseTo(301, 0)
  })

  it("üsse mesafe serisi: T0122 5,6 km'den 1,6 km'ye, çekim anından sonrası yok", () => {
    const route = [...brief.contacts[0].motion!.route!, { lat: 39.92, lon: 32.85, time: "14:15" }]
    const series = distanceSeries(route, zones.base, "14:10")

    expect(series).toHaveLength(25)
    expect(series[0].time).toBe("12:10")
    expect(series.at(-1)!.time).toBe("14:10")
    expect(series.at(-1)!.meters).toBeCloseTo(1646, -1)
  })
})
