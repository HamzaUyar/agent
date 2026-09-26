import { screen, waitFor, within } from "@testing-library/react"
import { http } from "msw"
import { describe, expect, it } from "vitest"

import type { Brief, ContactFinding } from "@/lib/api/types"
import { toLngLat } from "@/lib/geo"

import { API, fixtures, sseResponse, type SseEvent } from "./msw/handlers"
import { server } from "./msw/server"
import { renderEkran } from "./render"

const events = fixtures.evaluationEvents
const brief = events.at(-1)!.data as Brief
const UNEVALUATED = fixtures.images.find((i) => !i.last_risk_level)!.image_id

function withBrief(patch: (b: Brief) => Brief) {
  const list: SseEvent[] = [...events.slice(0, -1), { event: "brief", data: patch(structuredClone(brief)) }]
  server.use(http.post(`${API}/evaluations`, () => sseResponse(list)))
}

async function evaluated() {
  const view = renderEkran()
  const strip = await screen.findByRole("list", { name: "Görüntüler, çekim anına göre" })
  await view.user.click(within(strip).getByRole("button", { name: /^img_000860/ }))
  await view.user.click(screen.getByRole("button", { name: "Risk analizini başlat" }))
  await screen.findByLabelText("Görüntü risk seviyesi")
  return { ...view, strip }
}

const byKind = (kind: ContactFinding["kind"]) => brief.contacts.find((c) => c.kind === kind)!

describe("Temas'lar ve rotalar haritada", () => {
  it("her Temas çekim anındaki konumunda; tür ve seviye işaretin görünümünde, seviye etikette baklava + kelime", async () => {
    const { map } = await evaluated()

    const markers = map.markers.get("temaslar")!
    // Seviyeye göre sıralı (çakışan etiketlerde en önemlisi yerinde kalır).
    expect(markers.map((m) => m.id)).toEqual(["T0122", "T0032", "kayit-disi-1"])

    const [truck, missed, unregistered] = markers
    expect(truck).toMatchObject({
      lngLat: toLngLat(byKind("matched").location),
      label: "◆ T0122 · yaklaşıyor",
      variant: ["matched", "critical"],
    })
    expect(truck.description).toMatch(/Eşleşmiş temas · sınıf kamyon · seviye Kritik · kesinlik kesin · üsse 1,6 km/)
    expect(unregistered).toMatchObject({ label: "◆ kayıt dışı otomobil", variant: ["unregistered", "low"] })
    expect(missed).toMatchObject({ label: "◆ T0032 · duruyor", variant: ["missed", "medium"] })
    expect(missed.description).toMatch(/Kaçırılmış temas · sınıf tip bilinmiyor · seviye Orta/)
  })

  it("son yön okla, eğilim metinle; yönü bilinmeyen ya da duran Temas'ta ok yok, 'yön belirsiz' yazar", async () => {
    const { map } = await evaluated()
    const [truck, missed, unregistered] = map.markers.get("temaslar")!

    expect(truck.headingDeg).toBeCloseTo(byKind("matched").motion!.heading_deg!, 5)
    expect(truck.description).toMatch(/yaklaşıyor · yön 252°/)
    expect(unregistered.headingDeg).toBeUndefined()
    expect(missed.headingDeg).toBeUndefined()
    expect(missed.description).toMatch(/duruyor · yön belirsiz/)
  })

  it("track'i olan Temas'ların rotası saatleriyle, duraklamaları saat ve süreyle çizilir", async () => {
    const { map } = await evaluated()

    const routes = map.areas.get("rotalar")!.features
    expect(routes.map((f) => f.properties!.key)).toEqual(["T0122", "T0032"])
    const truckRoute = (routes[0].geometry as GeoJSON.LineString).coordinates
    expect(truckRoute).toHaveLength(25)
    expect(truckRoute.at(-1)).toEqual(toLngLat(byKind("matched").motion!.route!.at(-1)!))
    expect(routes[0].properties!.level).toBe("critical")

    const truckTimes = map.markers.get("rota-saatleri")!.filter((m) => m.id.startsWith("T0122"))
    expect(truckTimes.map((m) => m.label)).toEqual(["12:10", "12:40", "13:10", "13:40", "14:10"])

    expect(map.markerLabels("duraklamalar")).toEqual([
      "12:10 · 40 dk",
      "12:55 · 10 dk",
      "13:15 · 45 dk",
      "12:10 · 120 dk",
    ])
    expect(screen.getByText("Kaçırılmış temas (tespit yok)")).toBeInTheDocument()
    // Harita Temas'lara yaklaştığı için lejant katlanmış gelir (üstlerini örtmesin).
    expect(screen.getByRole("group", { name: "Lejant" })).not.toHaveAttribute("open")
  })

  it("çekim anından sonraki rota noktası ve duraklama çizilmez (ADR-0001)", async () => {
    withBrief((b) => {
      const m = b.contacts[0].motion!
      m.route = [...m.route!, { lat: 39.9, lon: 32.9, time: "14:15" }]
      m.stops = [...m.stops!, { ...m.stops![0], start: "14:20", end: "14:40" }]
      return b
    })
    const { map } = await evaluated()

    const truckRoute = (map.areas.get("rotalar")!.features[0].geometry as GeoJSON.LineString).coordinates
    expect(truckRoute).toHaveLength(25)
    expect(truckRoute).not.toContainEqual([32.9, 39.9])
    expect(map.markerLabels("rota-saatleri")).not.toContain("14:15")
    expect(map.markerLabels("duraklamalar").some((l) => l.startsWith("14:20"))).toBe(false)
  })

  it("eski önbellek kaydında rota saatleri yoksa rota saatsiz çizilir", async () => {
    withBrief((b) => {
      for (const c of b.contacts) c.motion?.route?.forEach((p) => (p.time = null))
      return b
    })
    const { map } = await evaluated()

    expect(map.areas.get("rotalar")!.features).toHaveLength(2)
    expect(map.markers.get("rota-saatleri")).toEqual([])
  })

  it("başka kare seçilince Temas'lar, rotalar ve duraklamalar kalkar", async () => {
    const { map, user, strip } = await evaluated()

    await user.click(within(strip).getByRole("button", { name: new RegExp(`^${UNEVALUATED}`) }))

    await waitFor(() => expect(map.markers.get("temaslar")).toEqual([]))
    expect(map.areas.get("rotalar")!.features).toEqual([])
    expect(map.markers.get("duraklamalar")).toEqual([])
  })
})

describe("Görüntü üzerinde tespitler", () => {
  it("kutular sınıf, güven ve track'le; kaçırılmış Temas kutusuz işaretle; altında özet", async () => {
    // Zaman akışından seçim Görüntü çekmecesini zaten açtı.
    await evaluated()
    const drawer = screen.getByRole("region", { name: "Görüntü" })

    const list = within(drawer).getByRole("list", { name: "Tespitler" })
    const boxes = within(list).getAllByRole("button")
    expect(boxes.map((b) => b.getAttribute("aria-label"))).toEqual([
      "kamyon %91 · T0122 · Kritik",
      "otomobil %83 · track yok · Düşük",
      "T0032 · kaçırılmış temas, kutu yok · Orta",
    ])
    // Kutu, karenin yüzdesi olarak: (727, 284, 58, 34) / (960 × 540).
    expect(within(list).getAllByRole("listitem")[0]).toHaveStyle({ left: `${(727 / 960) * 100}%`, top: `${(284 / 540) * 100}%` })
    expect(within(drawer).getByText(/2 tespit · 1 track'le eşleşti/)).toHaveTextContent(
      "kaçırılmış: T0032 (model görmedi)",
    )
  })

  it("zayıf tespit kesikli kutuyla ve 'zayıf tespit' olarak gösterilir", async () => {
    withBrief((b) => {
      b.contacts[1].is_weak = true
      return b
    })
    await evaluated()

    const weak = screen.getByRole("button", { name: /otomobil %83 · track yok · Düşük · zayıf tespit/ })
    expect(weak).toHaveClass("border-dashed")
  })
})
