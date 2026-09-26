import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { toLngLat } from "@/lib/geo"

import { fixtures } from "./msw/handlers"
import { renderEkran } from "./render"

const UNEVALUATED = fixtures.images.find((i) => !i.last_risk_level)!.image_id

const detail860 = fixtures.imageDetails.img_000860 as {
  corner_coordinates: Record<"top_left" | "top_right" | "bottom_left" | "bottom_right", [number, number]>
}

async function openGoruntu() {
  const view = renderEkran()
  await view.user.keyboard("g")
  const drawer = screen.getByRole("region", { name: "Görüntü" })
  await within(drawer).findByText("40 / 40 görüntü")
  return { ...view, drawer }
}

const cards = (drawer: HTMLElement) =>
  within(within(drawer).getByRole("list", { name: "Görüntüler" })).getAllByRole("button")

describe("40 Görüntü'den seçim", () => {
  it("çekmecede 40 kare önizlemeyle; her kartta kimlik, Bölge, çekim anı ve varsa son seviye var", async () => {
    const { drawer, container } = await openGoruntu()

    expect(cards(drawer)).toHaveLength(40)
    const card = within(drawer).getByRole("button", { name: /^img_000860/ })
    expect(card).toHaveAccessibleName("img_000860 · Dogu Yolu · 14:10 · son seviye Yüksek")
    expect(within(card).getByText("Yüksek")).toBeInTheDocument()
    expect(card.querySelector("img")).toHaveAttribute("src", "/api/images/img_000860/file")
    // Dosya yükleme yok: yalnızca veri setindeki kareler.
    expect(container.querySelector('input[type="file"]')).toBeNull()
  })

  it("dosyası yüklenemeyen karede kırık simge yerine 'önizleme yok' yazar", async () => {
    const { drawer } = await openGoruntu()
    const card = within(drawer).getByRole("button", { name: /^img_000860/ })

    fireEvent.error(card.querySelector("img")!)

    expect(within(card).getByText("önizleme yok")).toBeInTheDocument()
  })

  it("Bölge'ye ve son seviyeye göre filtrelenir, çekim anına göre sıralanır", async () => {
    const { drawer, user } = await openGoruntu()
    const zone = within(drawer).getByLabelText("Bölge")
    const level = within(drawer).getByLabelText("Son seviye")

    await user.selectOptions(zone, "Dogu Yolu")
    expect(cards(drawer)).toHaveLength(5)
    expect(within(drawer).getByText("5 / 40 görüntü")).toBeInTheDocument()

    await user.selectOptions(zone, "")
    await user.selectOptions(level, "Değerlendirilmedi")
    expect(cards(drawer)).toHaveLength(37)

    await user.selectOptions(level, "◆ Yüksek")
    expect(cards(drawer).map((c) => c.textContent)).toEqual([expect.stringContaining("img_000860")])

    await user.selectOptions(level, "")
    expect(cards(drawer)[0]).toHaveAccessibleName(/^img_008333 · .* · 10:10/)
    await user.click(within(drawer).getByRole("button", { name: /Çekim anı: eskiden yeniye/ }))
    expect(cards(drawer)[0]).toHaveAccessibleName(/^img_004423 · .* · 15:50/)
  })

  it("zaman akışında 40 kare çekim anına göre dizili; tıklamak kareyi seçer, ayak izini çizer ve haritayı yaklaştırır", async () => {
    const { user, map } = renderEkran()
    const strip = await screen.findByRole("list", { name: "Görüntüler, çekim anına göre" })
    const frames = within(strip).getAllByRole("button")
    expect(frames).toHaveLength(40)
    expect(frames[0]).toHaveAccessibleName(/^img_008333 · .* · 10:10 · son seviye Düşük$/)

    await user.click(within(strip).getByRole("button", { name: /^img_000860/ }))

    expect(screen.getByLabelText("Seçili kare")).toHaveTextContent("img_000860 · Dogu Yolu · 14:10")
    expect(within(strip).getByRole("button", { name: /^img_000860/ })).toHaveAttribute("aria-pressed", "true")
    // Önizleme ve analiz düğmesi için Görüntü çekmecesi açılır.
    const drawer = screen.getByRole("region", { name: "Görüntü" })
    expect(within(drawer).getByRole("img", { name: "img_000860 drone karesi" })).toBeInTheDocument()
    expect(within(drawer).getByRole("button", { name: /^img_000860/ })).toHaveAttribute("aria-pressed", "true")

    const c = detail860.corner_coordinates
    await waitFor(() => expect(map.areas.get("ayak-izi")?.features).toHaveLength(1))
    const ring = (map.areas.get("ayak-izi")!.features[0].geometry as GeoJSON.Polygon).coordinates[0]
    expect(ring).toEqual([c.top_left, c.top_right, c.bottom_right, c.bottom_left, c.top_left].map(toLngLat))

    const [[west, south], [east, north]] = map.fits.at(-1)!
    for (const [lon, lat] of ring) {
      expect(lon).toBeGreaterThan(west)
      expect(lon).toBeLessThan(east)
      expect(lat).toBeGreaterThan(south)
      expect(lat).toBeLessThan(north)
    }
    // Karenin çevresi de görünür ama bütün sahne değil: ~2,4 km'lik bir pencere.
    expect(east - west).toBeLessThan(0.05)
  })

  it("ızgaradan seçim zaman akışıyla aynı sonucu verir; ←/→ önceki/sonraki kareye geçer", async () => {
    const { drawer, user } = await openGoruntu()

    await user.click(within(drawer).getByRole("button", { name: /^img_000860/ }))
    expect(screen.getByLabelText("Seçili kare")).toHaveTextContent("img_000860 · Dogu Yolu · 14:10")

    const strip = screen.getByRole("list", { name: "Görüntüler, çekim anına göre" })
    const frames = within(strip).getAllByRole("button")
    const index = frames.findIndex((f) => f.getAttribute("aria-pressed") === "true")
    expect(frames[index]).toHaveAccessibleName(/^img_000860/)

    await user.keyboard("{ArrowRight}")
    expect(frames[index + 1]).toHaveAttribute("aria-pressed", "true")
    await user.keyboard("{ArrowLeft}{ArrowLeft}")
    expect(frames[index - 1]).toHaveAttribute("aria-pressed", "true")
  })

  it("seçim analizi başlatmaz; önceden değerlendirilmiş karede de düğme canlı analiz başlatır", async () => {
    const { drawer, user } = await openGoruntu()

    await user.click(within(drawer).getByRole("button", { name: new RegExp(`^${UNEVALUATED}`) }))
    expect(screen.getByRole("button", { name: "Risk analizini başlat" })).toBeInTheDocument()

    await user.click(within(drawer).getByRole("button", { name: /^img_000860/ }))
    expect(screen.getByRole("button", { name: "Risk analizini başlat" })).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "Değerlendirme adımları" })).not.toBeInTheDocument()
  })
})
