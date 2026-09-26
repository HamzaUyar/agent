import { act, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { useOperasyon } from "@/store/operasyon"

import { renderEkran as setup } from "./render"

const drawer = (name: string) => screen.queryByRole("region", { name })

describe("Operasyon ekranı kabuğu", () => {
  it("açılışta üst çubuk, harita paneli ve zaman akışı var; henüz kare seçilmedi", () => {
    setup()

    expect(screen.getByText("Zaman akışından bir kare seçin")).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Harita paneli" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Zaman akışı" })).toBeInTheDocument()
    expect(drawer("Risk & Temaslar")).not.toBeInTheDocument()
  })

  it("sekmeye tıklayınca çekmece yarım açılır, odak başlığa taşınır; Esc kapatır ve odağı geri verir", async () => {
    const { user } = setup()
    const tab = screen.getByRole("button", { name: "Risk & Temaslar" })

    await user.click(tab)

    const panel = drawer("Risk & Temaslar")!
    expect(panel).toHaveAttribute("data-state", "half")
    expect(within(panel).getByRole("heading", { name: "Risk & Temaslar" })).toHaveFocus()
    expect(within(panel).getByRole("tab", { name: "Temaslar" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    // Çekmece açıkken harita paneli yerinde kalır.
    expect(screen.getByRole("region", { name: "Harita paneli" })).toBeVisible()

    await user.keyboard("{Escape}")

    expect(drawer("Risk & Temaslar")).not.toBeInTheDocument()
    expect(tab).toHaveFocus()
  })

  it("kısayollar: R Risk & Temaslar, B Brief sekmesi, G Görüntü; aynı kısayol kapatır", async () => {
    const { user } = setup()

    await user.keyboard("b")
    expect(within(drawer("Risk & Temaslar")!).getByRole("tab", { name: "Brief" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    await user.keyboard("r")
    expect(within(drawer("Risk & Temaslar")!).getByRole("tab", { name: "Temaslar" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    await user.keyboard("r")
    expect(drawer("Risk & Temaslar")).not.toBeInTheDocument()

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
    expect(drawer("Risk & Temaslar")).toBeInTheDocument()
  })

  it("göz atma hâlindeki çekmece kısayolla önce yarım açılır, sonra kapanır", async () => {
    const { user } = setup()
    act(() => useOperasyon.setState({ right: { panel: "risk", state: "peek" } }))

    await user.keyboard("r")
    expect(drawer("Risk & Temaslar")).toHaveAttribute("data-state", "half")
    await user.keyboard("r")
    expect(drawer("Risk & Temaslar")).not.toBeInTheDocument()
  })

  it("Genişlet çekmeceyi tam hâle, Daralt yarım hâle getirir", async () => {
    const { user } = setup()
    await user.keyboard("r")
    const panel = drawer("Risk & Temaslar")!

    await user.click(within(panel).getByRole("button", { name: "Genişlet" }))
    expect(panel).toHaveAttribute("data-state", "full")

    await user.click(within(panel).getByRole("button", { name: "Daralt" }))
    expect(panel).toHaveAttribute("data-state", "half")
  })
})
