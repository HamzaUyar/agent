import type { LineString, Point } from "geojson"
import { describe, expect, it } from "vitest"

import type { TrackOverview } from "@/lib/api/types"

import { gorunenler, hazirla, izKatmani, konum, sayilar, suz } from "./iz"

/** A aracı: 10:00–11:00, 15 dakikada bir kayıt; 10:15–10:30 arası yerinde duruyor. */
const A: TrackOverview = {
  track_id: "A",
  start: "10:00",
  end: "11:00",
  image_id: "img_a",
  level: "critical",
  label: "car",
  kind: "matched",
  points: [
    { time: "10:00", lat: 39.0, lon: 32.0 },
    { time: "10:15", lat: 39.0, lon: 32.1 },
    { time: "10:30", lat: 39.0, lon: 32.1 },
    { time: "11:00", lat: 39.2, lon: 32.1 },
  ],
}
const B: TrackOverview = { ...A, track_id: "B", level: "medium", start: "12:00", end: "12:30",
  points: [{ time: "12:00", lat: 40, lon: 33 }, { time: "12:30", lat: 40, lon: 33.2 }] }
const C: TrackOverview = { ...B, track_id: "C", level: null, label: null, kind: null }

const [a] = hazirla([A])
const at = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

describe("İz analizi: bir aracın görünürlüğü ve konumu", () => {
  it("yalnızca kendi kayıt aralığında görünür; bittiğinde son konumu ekranda kalmaz", () => {
    expect(konum(a, at("09:30"))).toBeNull()
    expect(konum(a, at("10:00"))).toEqual([32.0, 39.0])
    expect(konum(a, at("10:30"))).toEqual([32.1, 39.0])
    expect(konum(a, at("11:00"))).toEqual([32.1, 39.2])
    expect(konum(a, at("11:01"))).toBeNull()
    expect(konum(a, at("11:30"))).toBeNull()
  })

  it("iki kayıt arasında iki gerçek kaydın arasında doğrusal ara konum; duraklamada yerinde", () => {
    const [lon, lat] = konum(a, at("10:07") + 0.5)!
    expect(lon).toBeCloseTo(32.05, 10)
    expect(lat).toBe(39.0)
    expect(konum(a, at("10:20"))).toEqual([32.1, 39.0])
    expect(konum(a, at("10:45"))![1]).toBeCloseTo(39.1, 10)
  })
})

describe("İz analizi: harita katmanı", () => {
  const tracks = hazirla([A, B, C])

  it("zaman yokken süzgece uyan her track tam yoluyla, hareketsiz", () => {
    const layer = izKatmani(suz(tracks, ["critical", "medium"]), null)
    expect(layer.features.map((f) => [f.properties!.id, f.properties!.kind])).toEqual([
      ["A", "yol"],
      ["B", "yol"],
    ])
    expect((layer.features[0].geometry as LineString).coordinates).toHaveLength(4)
  })

  it("t anında yalnızca kaydı o anı kapsayanlar: baş noktası ve 15 dakikalık kuyruk", () => {
    const layer = izKatmani(tracks, at("10:40"))
    expect(layer.features.map((f) => [f.properties!.id, f.properties!.kind])).toEqual([
      ["A", "kuyruk"],
      ["A", "bas"],
    ])
    const tail = (layer.features[0].geometry as LineString).coordinates
    // 10:25'ten (ara konum) 10:30 kaydına, oradan 10:40'a.
    expect(tail).toHaveLength(3)
    expect((layer.features[1].geometry as Point).coordinates).toEqual(tail.at(-1))
  })

  it("12:00'ye atlayınca 11:00'de biten A yok, 12:00'de başlayan B ve C var", () => {
    expect(gorunenler(tracks, at("12:00")).map((t) => t.id)).toEqual(["B", "C"])
    expect(gorunenler(tracks, at("11:30"))).toEqual([])
  })

  it("vurgulanan track'in yolu başından t'ye kadar çizilir, diğerleri soluk işaretlenir", () => {
    const layer = izKatmani(tracks, at("12:15"), "B")
    const b = layer.features.find((f) => f.properties!.id === "B" && f.properties!.kind === "kuyruk")!
    expect((b.geometry as LineString).coordinates[0]).toEqual([33, 40])
    expect(layer.features.find((f) => f.properties!.id === "C")!.properties!.dimmed).toBe(true)
  })

  it("seviye sayıları; değerlendirilmemiş track 'yok' grubunda", () => {
    expect(sayilar(tracks)).toEqual({ critical: 1, high: 0, medium: 1, low: 0, yok: 1 })
  })
})
