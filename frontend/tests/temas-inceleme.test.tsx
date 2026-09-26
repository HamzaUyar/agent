import { screen, waitFor, within } from "@testing-library/react"
import { http } from "msw"
import { describe, expect, it } from "vitest"

import type { Brief, ReportFinding } from "@/lib/api/types"
import { formatSpeed } from "@/lib/format"
import { toLngLat } from "@/lib/geo"

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
  const drawer = screen.getByRole("region", { name: "Risk & Temaslar" })
  return { ...view, drawer }
}

const card = () => screen.queryByRole("article", { name: /^Temas: / })
const section = (name: string) => within(card()!).getByRole("region", { name })

describe("Temas listesi", () => {
  it("seviyeye göre sıralı; düşük seviyeliler katlanır grupta; satırda tür, sınıf, track, mesafe, seviye, kesinlik", async () => {
    const { drawer } = await evaluated()
    const list = within(drawer).getByRole("region", { name: "Temaslar" })

    expect(within(list).getByText("3 temas")).toBeInTheDocument()
    const rows = within(list).getAllByRole("button")
    expect(rows.map((r) => r.textContent)).toEqual([
      "T0122kamyon◆KritikEşleşmiş temasüsse 1,6 kmkesinlik: kesin",
      "T0032tip bilinmiyor◆OrtaKaçırılmış temasüsse 1,6 kmkesinlik: olası",
      "track yokotomobil◆DüşükKayıt dışı temasüsse 1,6 kmkesinlik: olası",
    ])
    // Düşük seviyeli Temas katlanır grupta.
    expect(within(list).getByText("1 düşük seviyeli temas, en yakını 1,6 km").closest("details")).toContainElement(rows[2])
  })
})

describe("Temas seçimi: üç görünüm aynı Temas'a odaklanır", () => {
  it("listeden seçim: detay kartı açılır, harita rotayı vurgulayıp ona yaklaşır, görüntü kutusu vurgulanır", async () => {
    const { drawer, user, map } = await evaluated()

    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))

    expect(card()).toHaveAccessibleName("Temas: T0122")
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

    await waitFor(() => expect(card()).toHaveAccessibleName("Temas: T0032"))
    expect(screen.getByRole("region", { name: "Risk & Temaslar" })).toHaveAttribute("data-state", "half")
    expect(within(screen.getByRole("list", { name: "Tespitler" })).getByRole("button", { name: /^T0032/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
  })

  it("görüntüdeki kutuya tıklamak aynı seçimi yapar; kayıt dışı Temas'a rapor bağlanamadığını söyler", async () => {
    const { user, map } = await evaluated()

    await user.click(screen.getByRole("button", { name: /^otomobil %83 · track yok/ }))

    expect(card()).toHaveAccessibleName("Temas: kayıt dışı otomobil")
    expect(map.markers.get("temaslar")!.find((m) => m.id === "kayit-disi-1")!.variant).toContain("secili")
    expect(section("Eşleşme")).toHaveTextContent("Kayıt dışı temas: track yok")
    expect(section("Rapor kararları")).toHaveTextContent("Bu temasa rapor bağlanamıyor")
  })
})

describe("Detay kartı", () => {
  it("tespit, eşleşme, hareket ve seviye bölümleri backend alanlarını Türkçe biçimde gösterir", async () => {
    const { drawer, user } = await evaluated()
    await user.click(within(drawer).getByRole("button", { name: /^T0122/ }))
    const m = truck.motion!

    expect(section("Tespit")).toHaveTextContent("Sınıfkamyon")
    expect(section("Tespit")).toHaveTextContent("Güven%91")
    expect(section("Tespit")).toHaveTextContent("Zayıf tespithayır")
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
