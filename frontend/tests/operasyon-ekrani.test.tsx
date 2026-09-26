import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { OperasyonEkrani } from "@/components/operasyon/operasyon-ekrani"

function setup() {
  const user = userEvent.setup()
  render(<OperasyonEkrani />)
  return { user }
}

const drawer = (name: string) => screen.queryByRole("region", { name })

describe("Operasyon ekranı kabuğu", () => {
  it("açılışta üst çubuk, harita paneli ve zaman akışı var; henüz kare seçilmedi", () => {
    setup()

    expect(screen.getByRole("status")).toHaveTextContent("Zaman akışından bir kare seçin")
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

  it("kısayollar: R Risk & Temaslar, B Brief sekmesi, G Görüntü, S Sohbet; aynı kısayol kapatır", async () => {
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
    await user.keyboard("s")
    // Solda aynı anda tek çekmece: Sohbet, Görüntü'nün yerini alır.
    expect(drawer("Sohbet")).toBeInTheDocument()
    expect(drawer("Görüntü")).not.toBeInTheDocument()
  })

  it("sağ ve sol çekmece birlikte açık kalabilir; Esc önce en son açılanı kapatır", async () => {
    const { user } = setup()

    await user.keyboard("r")
    await user.keyboard("g")
    await user.keyboard("{Escape}")

    expect(drawer("Görüntü")).not.toBeInTheDocument()
    expect(drawer("Risk & Temaslar")).toBeInTheDocument()
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
