import { screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { haversineM, toLngLat } from "@/lib/geo"

import { fixtures, API } from "./msw/handlers"
import { server } from "./msw/server"
import { renderEkran } from "./render"

const base = toLngLat(fixtures.zones.base)
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

  it("her Bölge'nin yaklaşık alanı: yarıçap en yakın komşu merkeze uzaklığın yarısı, 'yaklaşık' olarak işaretli", async () => {
    const { map } = renderEkran()
    await waitFor(() => expect(map.areas.get("bolge-alanlari")).toBeDefined())

    const areas = map.areas.get("bolge-alanlari")!.features
    expect(areas).toHaveLength(8)
    areas.forEach((area, i) => {
      const nearest = Math.min(...centers.filter((_, j) => j !== i).map((c) => haversineM(centers[i], c)))
      expect(area.properties).toMatchObject({ name: fixtures.zones.zones[i].name, approximate: true })
      expect(area.properties!.radius_m).toBeCloseTo(nearest / 2, 3)
    })

    // Tooltip ve lejant alanın kesin sınır olmadığını söyler.
    for (const marker of map.markers.get("bolgeler")!) {
      expect(marker.description).toMatch(/yaklaşık alan, kesin sınır değil/)
    }
    const legend = screen.getByRole("region", { name: "Lejant" })
    expect(within(legend).getByText("Yaklaşık bölge alanı (kesin sınır değil)")).toBeInTheDocument()
    expect(within(legend).getByText("Üsse 1 km ve 3 km mesafe halkaları")).toBeInTheDocument()
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

  it("varsayılan zemin uydu; Sokak'a geçilebilir", async () => {
    const { map, user } = renderEkran()
    const group = screen.getByRole("group", { name: "Harita zemini" })
    expect(map.basemap).toBe("uydu")
    expect(within(group).getByRole("button", { name: "Uydu" })).toHaveAttribute("aria-pressed", "true")

    await user.click(within(group).getByRole("button", { name: "Sokak" }))

    expect(map.basemap).toBe("sokak")
    expect(within(group).getByRole("button", { name: "Sokak" })).toHaveAttribute("aria-pressed", "true")
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
