import { screen, within } from "@testing-library/react"
import { http } from "msw"
import { describe, expect, it } from "vitest"

import type { Brief } from "@/lib/api/types"

import { API, fixtures, sseResponse, type SseEvent } from "./msw/handlers"
import { server } from "./msw/server"
import { renderEkran } from "./render"

const events = fixtures.evaluationEvents
const brief = events.at(-1)!.data as Brief

function withReports() {
  const patched: Brief = {
    ...structuredClone(brief),
    report_findings: [
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
    ],
  }
  const list: SseEvent[] = [...events.slice(0, -1), { event: "brief", data: patched }]
  server.use(http.post(`${API}/evaluations`, () => sseResponse(list)))
}

async function selectFrame() {
  const view = renderEkran()
  const strip = await screen.findByRole("list", { name: "Görüntüler, çekim anına göre" })
  await view.user.click(within(strip).getByRole("button", { name: /^img_000860/ }))
  return view
}

const band = () => screen.getByRole("region", { name: "Seçili karenin son iki saati" })

describe("Seçili karenin son iki saati", () => {
  it("kare seçilince 12:10–14:10 ekseni ve çekim anı görünür; çekim anından sonrası kapalı", async () => {
    await selectFrame()

    expect(band()).toHaveTextContent("Seçili kare · son 2 saat (12:10–14:10)")
    expect(within(band()).getByRole("img", { name: "Çekim anı 14:10" })).toBeInTheDocument()
    expect(within(band()).getByText("çekim anından sonrası yok")).toBeInTheDocument()
    expect(within(band()).queryByRole("list", { name: "Olaylar" })).not.toBeInTheDocument()
  })

  it("Temas seçilince rota saatleri, duraklamalar ve bağlı rapor saatleri şeritte", async () => {
    withReports()
    const { user } = await selectFrame()
    await user.click(screen.getByRole("button", { name: "Sonucu aç (önbellek)" }))
    await screen.findByLabelText("Görüntü risk seviyesi")
    expect(band()).toHaveTextContent("Ayrıntı için bir temas seçin")

    await user.click(screen.getByRole("button", { name: /· T0122 ·/ }))

    const items = within(within(band()).getByRole("list", { name: "Olaylar" })).getAllByRole("listitem")
    const labels = items.map((li) => li.getAttribute("aria-label"))
    expect(labels.filter((l) => l!.startsWith("Rota noktası"))).toHaveLength(25)
    expect(labels).toContain("Duraklama 13:15 · 45 dk")
    expect(labels).toContain("Rapor 12:35 · resmi · çelişkili")
    // Çekim anından (14:10) sonraki hiçbir olay yok.
    const times = labels.map((l) => l!.match(/\d{2}:\d{2}/)![0])
    expect(times.every((t) => t <= "14:10")).toBe(true)
    expect(band()).toHaveTextContent("T0122 için")
  })
})
