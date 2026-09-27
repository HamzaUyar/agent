import { act, screen, waitFor, within } from "@testing-library/react"
import { http } from "msw"
import { describe, expect, it } from "vitest"

import type { Brief, ReportFinding } from "@/lib/api/types"
import { formatSpeed } from "@/lib/format"
import { toLngLat } from "@/lib/geo"
import { useOperasyon } from "@/store/operasyon"

import { API, fixtures, sseResponse, type SseEvent } from "./msw/handlers"
import { server } from "./msw/server"
import { renderEkran } from "./render"

const events = fixtures.evaluationEvents
const brief = events.at(-1)!.data as Brief
const truck = brief.contacts[0]

const REPORTS: ReportFinding[] = [
  {
    claim_id: 7,
    report_time: "12:35",
    source: "official",
    text: "39.9253N 32.8718E cevresinde 1 agir arac bulunuyor, hareketleri olagan.",
    claim_type: "vehicle",
    track_id: "T0122",
    verdict: "contradicts",
    certainty: "likely",
    effect: "raises",
    needs_review: false,
    dangerous_reassurance: false,
    reasoning: "rapor saatinde noktanın 300 m içinde track yok",
  },
  {
    claim_id: 9,
    report_time: "09:00",
    source: "third_party",
    text: "Bolgede tatbikat var.",
    claim_type: "friendly",
    track_id: null,
    verdict: "unverifiable",
    certainty: "unverified",
    effect: "none",
    needs_review: false,
    dangerous_reassurance: false,
    reasoning: "zamanı ve konumu belirsiz",
  },
]

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
  // Analiz başlayınca Risk & Temaslar kendiliğinden yarım açılır.
  const drawer = screen.getByRole("region", { name: "Risk & Araçlar" })
  return { ...view, drawer }
}

const card = () => screen.queryByRole("article", { name: /^Araç: / })
const section = (name: string) => within(card()!).getByRole("region", { name })

describe("Temas listesi", () => {
  const rows = (list: HTMLElement) => within(list).getAllByRole("listitem").map((li) => within(li).getByRole("button"))

  it("seviyeye göre sıralı; düşük seviyeliler katlanır grupta; satırda track, sınıf, seviye ve mesafe (kesinlik ve tür sütunu yok)", async () => {
    const { drawer } = await evaluated()
    const list = within(drawer).getByRole("region", { name: "Araçlar" })

    expect(within(list).getByText("3 araç")).toBeInTheDocument()
    expect(rows(list).map((r) => r.textContent)).toEqual([
      "T0122kamyon◆Kritiküsse 1,6 km",
      "T0032tip bilinmiyor◆Ortaüsse 1,6 km",
      "track yokotomobil◆Düşüküsse 1,6 km",
    ])
    // Tür ve kesinlik erişilebilir adda kalır.
    expect(rows(list)[0]).toHaveAccessibleName("T0122 · kamyon · Eşleşmiş temas · Yüksek kesinlik")
    // Düşük seviyeli araç katlanır grupta.
    expect(within(list).getByText("1 düşük seviyeli araç, en yakını 1,6 km").closest("details")).toContainElement(rows(list)[2])
  })

  it("tespit güvenilirliği özeti kaç sonucun hangi kesinlikte olduğunu söyler; bir gruba tıklamak listeyi süzer", async () => {
    const { drawer, user } = await evaluated()
    const list = within(drawer).getByRole("region", { name: "Araçlar" })
    const summary = within(list).getByRole("group", { name: "Tespit güvenilirliği" })

    expect(within(summary).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "1Yüksek kesinlik",
      "2Orta kesinlik",
      "0Düşük kesinlik",
    ])
    expect(within(summary).getByRole("button", { name: "0Düşük kesinlik" })).toBeDisabled()

    await user.click(within(summary).getByRole("button", { name: "2Orta kesinlik" }))
    expect(within(list).getByText("2 / 3 araç")).toBeInTheDocument()
    expect(rows(list).map((r) => r.textContent?.slice(0, 5))).toEqual(["T0032", "track"])

    await user.click(within(summary).getByRole("button", { name: "2Orta kesinlik" }))
    expect(within(list).getByText("3 araç")).toBeInTheDocument()
  })
})

describe("Temas seçimi: üç görünüm aynı Temas'a odaklanır", () => {
  it("listeden seçim: detay kartı açılır, harita rotayı vurgulayıp ona yaklaşır, görüntü kutusu vurgulanır", async () => {
    const { drawer, user, map } = await evaluated()

    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))

    expect(card()).toHaveAccessibleName("Araç: T0122")
    expect(drawer).toHaveAttribute("data-state", "half")
    // Harita
    const truckMarker = map.markers.get("temaslar")!.find((m) => m.id === "T0122")!
    expect(truckMarker.variant).toContain("secili")
    const routes = map.areas.get("rotalar")!.features
    expect(routes.find((f) => f.properties!.key === "T0122")!.properties).toMatchObject({ selected: true, dimmed: false })
    expect(routes.find((f) => f.properties!.key === "T0032")!.properties).toMatchObject({ selected: false, dimmed: true })
    const [[west, south], [east, north]] = map.fits.at(-1)!
    for (const [lon, lat] of [toLngLat(truck.location), toLngLat(truck.motion!.route![0])]) {
      expect(lon).toBeGreaterThanOrEqual(west)
      expect(lon).toBeLessThanOrEqual(east)
      expect(lat).toBeGreaterThanOrEqual(south)
      expect(lat).toBeLessThanOrEqual(north)
    }
    // Görüntü
    const image = screen.getByRole("list", { name: "Tespitler" })
    expect(within(image).getByRole("button", { name: /· T0122 ·/ })).toHaveAttribute("aria-pressed", "true")

    // Aynı satıra tekrar tıklamak seçimi kaldırır.
    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))
    expect(card()).not.toBeInTheDocument()
  })

  it("haritadaki işarete tıklamak aynı seçimi yapar ve çekmeceyi yarım açar", async () => {
    const { map, user } = await evaluated()
    await user.keyboard("r") // çekmeceyi kapat

    map.clickMarker("temaslar", "T0032")

    await waitFor(() => expect(card()).toHaveAccessibleName("Araç: T0032"))
    expect(screen.getByRole("region", { name: "Risk & Araçlar" })).toHaveAttribute("data-state", "half")
    expect(within(screen.getByRole("list", { name: "Tespitler" })).getByRole("button", { name: /^T0032/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
  })

  it("görüntüdeki kutuya tıklamak aynı seçimi yapar; kayıt dışı Temas'a rapor bağlanamadığını söyler", async () => {
    const { user, map } = await evaluated()

    await user.click(screen.getByRole("button", { name: /^otomobil %83 · track yok/ }))

    expect(card()).toHaveAccessibleName("Araç: kayıt dışı otomobil")
    expect(map.markers.get("temaslar")!.find((m) => m.id === "kayit-disi-1")!.variant).toContain("secili")
    expect(section("Eşleşme")).toHaveTextContent("Kayıt dışı temas: track yok")
    expect(section("Rapor kararları")).toHaveTextContent("Bu araca rapor bağlanamıyor")
  })
})

describe("Detay kartı", () => {
  it("tespit, eşleşme, hareket ve seviye bölümleri backend alanlarını Türkçe biçimde gösterir", async () => {
    const { drawer, user } = await evaluated()
    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))
    const m = truck.motion!

    expect(section("Tespit")).toHaveTextContent("Sınıfkamyon")
    expect(section("Tespit")).toHaveTextContent("Güven%91")
    expect(section("Tespit")).toHaveTextContent("KesinlikYüksek kesinlik")
    expect(section("Eşleşme")).toHaveTextContent("TrackT0122")
    expect(section("Eşleşme")).toHaveTextContent("Eşleşme mesafesi0,4 m")
    expect(section("Eşleşme")).toHaveTextContent("İkinci adayT0032 · 41 m")
    expect(section("Hareket")).toHaveTextContent("30 dk önce 5,5 km → şimdi 1,6 km · yaklaşıyor")
    expect(section("Hareket")).toHaveTextContent(`son ${formatSpeed(m.recent_speed_mps)} · ortalama ${formatSpeed(m.avg_speed_mps)}`)
    expect(section("Hareket")).toHaveTextContent("Yön252°")
    expect(section("Hareket")).toHaveTextContent("12:10 (40 dk, Kuzeydogu Kavsagi) · 12:55 (10 dk")
    expect(section("Hareket")).toHaveTextContent("Kuzeydogu Kavsagi → Dogu Yolu")
    expect(within(section("Hareket")).getByRole("img")).toHaveAccessibleName(/^Üsse mesafe 12:10'da .* km, 14:10'da 1,6 km$/)
    expect(section("Seviye")).toHaveTextContent("temel ◆Kritik → nihai ◆Kritik")
    for (const reason of truck.level_reasons ?? []) expect(section("Seviye")).toHaveTextContent(reason)
  })

  it("bu Temas'a bağlı Rapor kararları: karar, riske etkisi, gerekçe; başka Temas'ın raporu görünmez", async () => {
    withBrief((b) => ({ ...b, report_findings: REPORTS }))
    const { drawer, user } = await evaluated()
    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))

    const reports = within(section("Rapor kararları")).getAllByRole("listitem")
    expect(reports).toHaveLength(1)
    expect(reports[0]).toHaveTextContent("12:35resmiÇELİŞKİLİriske etkisi: ↑ yükseltir")
    expect(reports[0]).toHaveTextContent("Gerekçe: rapor saatinde noktanın 300 m içinde track yok")
    expect(section("Rapor kararları")).not.toHaveTextContent("tatbikat")
  })

  it("belirsiz eşleşme uyarısı, LLM ayarı ve reddedilen öneri görünür", async () => {
    withBrief((b) => {
      Object.assign(b.contacts[0], {
        is_ambiguous: true,
        base_level: "high",
        adjustment_reason: "Rapor ağır aracın yaklaştığını doğruluyor",
        adjustment_rejected: "İki kademe yükseltme önerisi: en fazla ±1 kademe",
      })
      return b
    })
    const { drawer, user } = await evaluated()
    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))

    expect(within(section("Eşleşme")).getByRole("note")).toHaveTextContent("Belirsiz eşleşme")
    expect(section("Seviye")).toHaveTextContent("temel ◆Yüksek → nihai ◆Kritik")
    expect(section("Seviye")).toHaveTextContent("LLM ayarı: Rapor ağır aracın yaklaştığını doğruluyor")
    expect(section("Seviye")).toHaveTextContent("Reddedilen öneri: İki kademe yükseltme önerisi")
  })

  it("eski önbellek kaydında rota saati yoksa mesafe grafiği sıra ekseniyle çizilir", async () => {
    withBrief((b) => {
      b.contacts[0].motion!.route!.forEach((p) => (p.time = null))
      return b
    })
    const { drawer, user } = await evaluated()
    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))

    expect(within(section("Hareket")).getByRole("img")).toHaveAccessibleName(/\(saat bilgisi yok\)$/)
  })
})

describe("Kesinlik süzgeci", () => {
  it("etkin süzgecin grubunda sonuç kalmasa da düğmesi kapatılabilir; kare değişince süzgeç sıfırlanır", async () => {
    const { drawer, user } = await evaluated()
    act(() => useOperasyon.getState().setCertaintyFilter("weak"))
    const summary = within(drawer).getByRole("group", { name: "Tespit güvenilirliği" })
    const weak = within(summary).getByRole("button", { name: "0Düşük kesinlik" })

    expect(weak).toBeEnabled()
    await user.click(weak)
    expect(useOperasyon.getState().certaintyFilter).toBeNull()

    act(() => useOperasyon.getState().setCertaintyFilter("likely"))
    act(() => useOperasyon.getState().selectImage("img_008333"))
    expect(useOperasyon.getState().certaintyFilter).toBeNull()
  })
})

describe("Seçimi kaldırma", () => {
  it("seçili aracın haritadaki işaretine tekrar tıklamak ya da haritada boş yere tıklamak seçimi kaldırır", async () => {
    const { map } = await evaluated()

    act(() => map.events!.onMarkerClick?.("temaslar", "T0122"))
    expect(useOperasyon.getState().selectedContactKey).toBe("T0122")
    act(() => map.events!.onMarkerClick?.("temaslar", "T0122"))
    expect(useOperasyon.getState().selectedContactKey).toBeNull()

    act(() => map.events!.onMarkerClick?.("temaslar", "T0122"))
    act(() => map.events!.onMapClick?.())
    expect(useOperasyon.getState().selectedContactKey).toBeNull()
  })

  it("Görüntü çekmecesi kapanınca seçili kare bırakılır: ayak izi kalkar, üst çubuk kare beklemeye döner", async () => {
    const { map, user } = await evaluated()
    expect(map.areas.get("ayak-izi")!.features).toHaveLength(1)

    await user.click(within(screen.getByRole("region", { name: "Görüntü" })).getByRole("button", { name: "Kapat (Esc)" }))

    expect(useOperasyon.getState().selectedImageId).toBeNull()
    expect(map.areas.get("ayak-izi")!.features).toEqual([])
    expect(screen.getByText("Zaman akışından bir kare seçin")).toBeInTheDocument()
  })
})
