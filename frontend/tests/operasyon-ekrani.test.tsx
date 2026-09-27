import { fireEvent, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { drawerBounds } from "@/components/operasyon/cekmece"
import { useOperasyon } from "@/store/operasyon"

import { renderEkran as setup } from "./render"

const drawer = (name: string) => screen.queryByRole("region", { name })

describe("Operasyon ekranı kabuğu", () => {
  it("açılışta üst çubuk, harita paneli ve zaman akışı var; henüz kare seçilmedi", () => {
    setup()

    expect(screen.getByText("Zaman akışından bir kare seçin")).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Harita paneli" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Zaman akışı" })).toBeInTheDocument()
    expect(drawer("Risk & Araçlar")).not.toBeInTheDocument()
  })

  it("sekmeye tıklayınca çekmece yarım açılır, odak başlığa taşınır; Esc kapatır ve odağı geri verir", async () => {
    const { user } = setup()
    const tab = screen.getByRole("button", { name: "Risk & Araçlar" })

    await user.click(tab)

    const panel = drawer("Risk & Araçlar")!
    expect(panel).toHaveAttribute("data-state", "half")
    expect(within(panel).getByRole("heading", { name: "Risk & Araçlar" })).toHaveFocus()
    expect(within(panel).getByRole("tab", { name: "Araçlar" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    // Çekmece açıkken harita paneli yerinde kalır.
    expect(screen.getByRole("region", { name: "Harita paneli" })).toBeVisible()

    await user.keyboard("{Escape}")

    expect(drawer("Risk & Araçlar")).not.toBeInTheDocument()
    expect(tab).toHaveFocus()
  })

  it("kısayollar: R Risk & Araçlar, B Brief sekmesi, G Görüntü; aynı kısayol kapatır", async () => {
    const { user } = setup()

    await user.keyboard("b")
    expect(within(drawer("Risk & Araçlar")!).getByRole("tab", { name: "Brief" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    await user.keyboard("r")
    expect(within(drawer("Risk & Araçlar")!).getByRole("tab", { name: "Araçlar" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    await user.keyboard("r")
    expect(drawer("Risk & Araçlar")).not.toBeInTheDocument()

    await user.keyboard("g")
    expect(drawer("Görüntü")).toBeInTheDocument()
    await user.keyboard("g")
    expect(drawer("Görüntü")).not.toBeInTheDocument()
  })

  it("Sohbet çekmecesi yok: ne sekmesi ne kısayolu", async () => {
    const { user } = setup()

    expect(screen.queryByRole("button", { name: "Sohbet" })).not.toBeInTheDocument()
    await user.keyboard("s")
    expect(drawer("Sohbet")).not.toBeInTheDocument()
  })

  it("tema düğmesi üst çubuğun en sağında; koyu ↔ açık geçer, seçim saklanır ve harita da temaya uyar", async () => {
    const { user, map } = setup()
    const bar = screen.getByRole("banner")
    const button = within(bar).getByRole("button", { name: "Açık temaya geç" })
    // En sağda: üst çubuktaki son düğme.
    expect(within(bar).getAllByRole("button").at(-1)).toBe(button)
    expect(document.documentElement).toHaveClass("dark")

    await user.click(button)

    expect(document.documentElement).not.toHaveClass("dark")
    expect(localStorage.getItem("operasyon-tema")).toBe("acik")
    expect(map.theme).toBe("acik")

    await user.click(within(bar).getByRole("button", { name: "Koyu temaya geç" }))

    expect(document.documentElement).toHaveClass("dark")
    expect(localStorage.getItem("operasyon-tema")).toBe("koyu")
    expect(map.theme).toBe("koyu")
  })

  it("sağ ve sol çekmece birlikte açık kalabilir; Esc önce en son açılanı kapatır", async () => {
    const { user } = setup()

    await user.keyboard("r")
    await user.keyboard("g")
    await user.keyboard("{Escape}")

    expect(drawer("Görüntü")).not.toBeInTheDocument()
    expect(drawer("Risk & Araçlar")).toBeInTheDocument()
  })

  it("Genişlet çekmeceyi tam hâle, Daralt yarım hâle getirir", async () => {
    const { user } = setup()
    await user.keyboard("r")
    const panel = drawer("Risk & Araçlar")!

    await user.click(within(panel).getByRole("button", { name: "Genişlet" }))
    expect(panel).toHaveAttribute("data-state", "full")

    await user.click(within(panel).getByRole("button", { name: "Daralt" }))
    expect(panel).toHaveAttribute("data-state", "half")
  })

  it("kenar rayı ikonlu: adı erişilebilir ad ve ipucunda, kısayol ipucunda; Brief'in ayrı kenar düğmesi yok", async () => {
    const { user } = setup()
    const right = screen.getByRole("navigation", { name: "Sağ paneller" })

    expect(within(right).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "İz analizi",
      "Risk & Araçlar",
    ])
    expect(screen.queryByRole("button", { name: /^Brief/ })).not.toBeInTheDocument()

    await user.hover(within(right).getByRole("button", { name: "Risk & Araçlar" }))
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Risk & AraçlarR")
  })

  it("Brief'e Risk & Araçlar içindeki sekmeden geçilir", async () => {
    const { user } = setup()
    await user.click(screen.getByRole("button", { name: "Risk & Araçlar" }))

    await user.click(within(drawer("Risk & Araçlar")!).getByRole("tab", { name: "Brief" }))

    expect(within(drawer("Risk & Araçlar")!).getByRole("tab", { name: "Brief" })).toHaveAttribute("aria-selected", "true")
  })
})

describe("Çekmece genişliği", () => {
  const separator = () => screen.getByRole("separator", { name: "Risk & Araçlar genişliği" })
  const width = () => parseFloat(drawer("Risk & Araçlar")!.style.width)

  it("tutamaç sürüklenince genişlik imleci izler, bırakılınca olduğu yerde kalır ve saklanır", async () => {
    const { user } = setup()
    await user.keyboard("r")
    const before = width()

    // Sağ çekmece sola doğru büyür: tutamacı 120 px sola sürükle.
    fireEvent.pointerDown(separator(), { pointerId: 1, button: 0, clientX: 800 })
    fireEvent.pointerMove(separator(), { pointerId: 1, clientX: 740 })
    expect(width()).toBe(before + 60)
    fireEvent.pointerMove(separator(), { pointerId: 1, clientX: 680 })
    fireEvent.pointerUp(separator(), { pointerId: 1, clientX: 680 })

    expect(width()).toBe(before + 120)
    expect(drawer("Risk & Araçlar")).toHaveAttribute("data-state", "half")
    expect(JSON.parse(localStorage.getItem("operasyon-cekmece-genislik")!).right).toBe(before + 120)

    // Kapatıp açınca son genişlik geri gelir.
    await user.keyboard("r")
    await user.keyboard("r")
    expect(width()).toBe(before + 120)
  })

  it("saklanan genişlik sayfa açıldıktan sonra uygulanır (ilk çizim sunucu çıktısıyla aynı)", async () => {
    localStorage.setItem("operasyon-cekmece-genislik", JSON.stringify({ left: null, right: 350 }))
    const { user } = setup()
    await user.keyboard("r")
    expect(width()).toBe(350)
  })

  it("genişlik alt ve üst sınırın dışına çıkmaz; harita hiçbir zaman kapanmaz", async () => {
    const { user } = setup()
    await user.keyboard("r")
    const { min, max } = drawerBounds(window.innerWidth)

    fireEvent.pointerDown(separator(), { pointerId: 1, button: 0, clientX: 800 })
    fireEvent.pointerMove(separator(), { pointerId: 1, clientX: 800 + 5000 })
    fireEvent.pointerUp(separator(), { pointerId: 1, clientX: 800 + 5000 })
    expect(width()).toBe(min)

    fireEvent.pointerDown(separator(), { pointerId: 2, button: 0, clientX: 800 })
    fireEvent.pointerUp(separator(), { pointerId: 2, clientX: 800 - 5000 })
    expect(width()).toBe(Math.round(max))
    expect(separator()).toHaveAttribute("aria-valuemax", String(Math.round(max)))
  })

  it("tutamaç klavyeyle de ayarlanır: ← genişletir, → daraltır (sağ çekmece)", async () => {
    const { user } = setup()
    await user.keyboard("r")
    const before = width()
    separator().focus()

    await user.keyboard("{ArrowLeft}{ArrowLeft}")
    expect(width()).toBe(before + 32)
    await user.keyboard("{ArrowRight}")
    expect(width()).toBe(before + 16)
  })
})

describe("Günün görüntüleri", () => {
  it("başlangıçta kapalı: ince çubukta başlık ve kare sayısı; chevron açar ve kapatır", async () => {
    const { user } = setup({ timelineOpen: false })
    const toggle = screen.getByRole("button", { name: /Günün görüntüleri/ })

    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(await screen.findByText("40 kare")).toBeInTheDocument()
    expect(screen.queryByRole("list", { name: "Görüntüler, çekim anına göre" })).not.toBeInTheDocument()

    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("list", { name: "Görüntüler, çekim anına göre" })).toBeInTheDocument()

    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "false")
  })

  it("kapalıyken de → sonraki kareyi seçer", async () => {
    const { user } = setup({ timelineOpen: false })
    await screen.findByText("40 kare")

    await user.keyboard("{ArrowRight}")

    expect(useOperasyon.getState().selectedImageId).toBe("img_008333")
  })
})
