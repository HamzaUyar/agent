import { screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { haversineM, toLngLat } from "@/lib/geo"

import { fixtures, API } from "./msw/handlers"
import { server } from "./msw/server"
import { renderEkran } from "./render"

const base = toLngLat(fixtures.zones.base)

/** Işın atma: nokta kapalı halkanın içinde mi. */
function inRing([x, y]: [number, number], ring: number[][]) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}
const centers = fixtures.zones.zones.map((z) => toLngLat(z.center as [number, number]))

describe("Açılış haritası: Üs, halkalar ve yaklaşık bölge alanları", () => {
  it("Üs'ü, 1 ve 3 km halkalarını ve 8 Bölge merkezini adlarıyla çizer; henüz analiz yok", async () => {
    const { map } = renderEkran()

    await waitFor(() => expect(map.markerLabels("us")).toEqual(["Merkez Us"]))
    expect(map.markers.get("us")![0].lngLat).toEqual(base)

    const rings = map.areas.get("us-halkalari")!.features
    expect(rings.map((f) => f.properties!.radius_m)).toEqual([1000, 3000])
    expect(map.markerLabels("halka-etiketleri")).toEqual(["1 km", "3 km"])

    expect(map.markerLabels("bolgeler")).toEqual(fixtures.zones.zones.map((z) => z.name))
    expect(map.markers.get("bolgeler")!.map((m) => m.lngLat)).toEqual(centers)

    expect(screen.getByText("Zaman akışından bir kare seçin")).toBeInTheDocument()
    expect(screen.getByText("Merkez Us")).toBeInTheDocument()
  })

  it("her Bölge'nin yaklaşık alanı Üs merkezli bir pasta dilimi: merkezi yalnızca kendi diliminde, Üs'ün 1 km dairesi boş", async () => {
    const { map } = renderEkran()
    await waitFor(() => expect(map.areas.get("bolge-alanlari")).toBeDefined())

    const areas = map.areas.get("bolge-alanlari")!.features
    const rings = areas.map((f) => (f.geometry as GeoJSON.Polygon).coordinates[0])
    expect(areas).toHaveLength(8)
    areas.forEach((area, i) => {
      expect(area.properties).toMatchObject({ name: fixtures.zones.zones[i].name, approximate: true, selected: false })
      rings.forEach((ring, j) => expect(inRing(centers[i], ring)).toBe(i === j))
      // Dilim 1 km halkasından başlar: Üs'ün dairesine taşmaz.
      expect(Math.min(...rings[i].map((p) => haversineM(base, p as [number, number])))).toBeGreaterThan(999)
    })
    // Komşu dilimler sırayla açık/koyu dolgu alır.
    expect(new Set(areas.map((a) => a.properties!.parity))).toEqual(new Set([0, 1]))

    // Bölge tooltip'i alanın kesin sınır olmadığını söyler.
    for (const marker of map.markers.get("bolgeler")!) {
      expect(marker.description).toMatch(/yaklaşık alan .*kesin sınır değil/)
    }
  })

  it("açılışta görünüm Üs'ü ve bütün Bölge merkezlerini yaklaşık alanlarıyla kapsar", async () => {
    const { map } = renderEkran()
    await waitFor(() => expect(map.fits).toHaveLength(1))
    await waitFor(() => expect(map.areas.get("bolge-alanlari")).toBeDefined())

    const [[west, south], [east, north]] = map.fits[0]
    const areaPoints = map.areas
      .get("bolge-alanlari")!
      .features.flatMap((f) => (f.geometry as GeoJSON.Polygon).coordinates[0])
    for (const [lon, lat] of [base, ...centers, ...areaPoints]) {
      expect(lon).toBeGreaterThanOrEqual(west)
      expect(lon).toBeLessThanOrEqual(east)
      expect(lat).toBeGreaterThanOrEqual(south)
      expect(lat).toBeLessThanOrEqual(north)
    }
  })

  it("seçili karenin Bölge dilimi vurgulanır; diğerleri vurgulanmaz", async () => {
    const { map, user } = renderEkran()
    const strip = await screen.findByRole("list", { name: "Görüntüler, çekim anına göre" })
    await user.click(within(strip).getByRole("button", { name: /^img_000860/ }))

    await waitFor(() =>
      expect(
        map.areas.get("bolge-alanlari")!.features.filter((f) => f.properties!.selected).map((f) => f.properties!.name),
      ).toEqual(["Dogu Yolu"]),
    )
  })

  it("varsayılan zemin sokak; Uydu'ya geçilebilir", async () => {
    const { map, user } = renderEkran()
    const group = screen.getByRole("group", { name: "Harita zemini" })
    await waitFor(() => expect(map.basemap).toBe("sokak"))
    expect(within(group).getByRole("button", { name: "Sokak" })).toHaveAttribute("aria-pressed", "true")

    await user.click(within(group).getByRole("button", { name: "Uydu" }))

    expect(map.basemap).toBe("uydu")
    expect(within(group).getByRole("button", { name: "Uydu" })).toHaveAttribute("aria-pressed", "true")
  })

  it("zemin yüklenemezse düz zemine düşer, bunu söyler ve katmanlar yerinde kalır", async () => {
    const { map, user } = renderEkran()
    await waitFor(() => expect(map.markerLabels("bolgeler")).toHaveLength(8))

    map.failBasemap()

    expect(await screen.findByText(/Harita zemini yüklenemedi; düz zemin gösteriliyor/)).toBeInTheDocument()
    expect(map.basemap).toBe("duz")
    expect(map.markerLabels("bolgeler")).toHaveLength(8)
    expect(map.areas.get("bolge-alanlari")!.features).toHaveLength(8)

    // Operatör zemini yeniden deneyebilir.
    await user.click(screen.getByRole("button", { name: "Uydu" }))
    expect(map.basemap).toBe("uydu")
    expect(screen.queryByText(/Harita zemini yüklenemedi/)).not.toBeInTheDocument()
  })

  it("üs ve bölge bilgisi alınamazsa hata ve Tekrar dene gösterir", async () => {
    server.use(http.get(`${API}/zones`, () => HttpResponse.json({ detail: "Sunucu hatası" }, { status: 500 })))
    const { map, user } = renderEkran()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Üs ve bölge bilgisi alınamadı.")
    expect(map.markerLabels("bolgeler")).toEqual([])

    server.resetHandlers()
    await user.click(within(alert).getByRole("button", { name: "Tekrar dene" }))

    await waitFor(() => expect(map.markerLabels("bolgeler")).toHaveLength(8))
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})

describe("Lejant", () => {
  it("sol altta her zaman görünür, katlanmaz; yalnızca araç sınıfı renklerini gösterir", async () => {
    renderEkran()
    const legend = await screen.findByRole("region", { name: "Lejant" })

    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "otomobil",
      "minibüs",
      "kamyon",
      "otobüs",
      "tip bilinmiyor",
    ])
    expect(within(legend).queryByRole("button")).not.toBeInTheDocument()
  })
})
