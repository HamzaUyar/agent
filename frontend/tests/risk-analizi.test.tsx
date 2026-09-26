import { act, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { Brief } from "@/lib/api/types"
import { SLOW_AFTER_MS } from "@/store/operasyon"

import { API, fixtures, sseResponse, type SseEvent } from "./msw/handlers"
import { server } from "./msw/server"
import { renderEkran } from "./render"

const UNEVALUATED = fixtures.images.find((i) => !i.last_risk_level)!.image_id
const events = fixtures.evaluationEvents
const brief = events.at(-1)!.data as Brief
const steps = events.filter((e) => e.event === "step")

async function selectAndStart(imageId = "img_000860") {
  const view = renderEkran()
  const strip = await screen.findByRole("list", { name: "Görüntüler, çekim anına göre" })
  await view.user.click(within(strip).getByRole("button", { name: new RegExp(`^${imageId}`) }))
  const start = screen.getByRole("button", { name: "Risk analizini başlat" })
  await view.user.click(start)
  return view
}

function useEvaluationStream(list: SseEvent[], opts?: { delayMs?: number }) {
  const bodies: unknown[] = []
  server.use(
    http.post(`${API}/evaluations`, async ({ request }) => {
      bodies.push(await request.json())
      return sseResponse(list, opts)
    }),
  )
  return bodies
}

const stepsList = () => screen.getByRole("region", { name: "Değerlendirme adımları" })

afterEach(() => {
  vi.useRealTimers()
})

describe("Risk analizi akışı", () => {
  it("adımlar geldikçe üst çubukta ve Risk & Temaslar çekmecesinde görünür; sabit bir adım listesi yok", async () => {
    useEvaluationStream(events, { delayMs: 15 })
    await selectAndStart()

    // İlk adım geldiğinde son adım henüz yok: liste gelen olaylardan oluşuyor.
    await within(stepsList()).findByText("goruntu")
    expect(within(stepsList()).queryByText("karar")).not.toBeInTheDocument()
    expect(screen.getByText(/^Adım \d · /)).toBeInTheDocument()

    await screen.findByLabelText("Görüntü risk seviyesi", {}, { timeout: 2000 })
    // Brief gelince adımlar katlanır bir gruba geçer; sıraları aynı kalır.
    const done = screen.getByRole("group", { name: "Değerlendirme adımları" })
    expect(within(done).getByText("Değerlendirme adımları (8)")).toBeInTheDocument()
    const items = within(done).getAllByRole("listitem")
    expect(items.map((li) => li.textContent)).toEqual(
      steps.map((s) => `${(s.data as { step_no: number }).step_no}${(s.data as { name: string }).name}${(s.data as { summary: string }).summary}`),
    )
  })

  it("analiz başlayınca kapalı Risk & Temaslar yarım açılır; Brief gelince üst çubukta seviye (baklava + kelime) ve önerilen eylem", async () => {
    expect(screen.queryByRole("region", { name: "Risk & Temaslar" })).not.toBeInTheDocument()
    await selectAndStart()

    const drawer = screen.getByRole("region", { name: "Risk & Temaslar" })
    expect(drawer).toHaveAttribute("data-state", "half")

    const level = await screen.findByLabelText("Görüntü risk seviyesi")
    expect(level).toHaveTextContent("◆Kritik")
    expect(level).toHaveTextContent(`→ ${brief.recommended_action}`)
    expect(drawer).toHaveAttribute("data-state", "half")

    // Otomatik özet rozeti ve sebebi.
    expect(screen.getAllByText("otomatik özet")[0]).toBeInTheDocument()
  })

  it("değerlendirilen karenin son seviyesi zaman akışında ve kartta güncellenir", async () => {
    useEvaluationStream(events)
    await selectAndStart(UNEVALUATED)
    await screen.findByLabelText("Görüntü risk seviyesi")

    const strip = screen.getByRole("list", { name: "Görüntüler, çekim anına göre" })
    expect(within(strip).getByRole("button", { name: new RegExp(`^${UNEVALUATED}`) })).toHaveAccessibleName(
      /son seviye Kritik$/,
    )
  })

  it("Brief sekmesi metni, önerilen eylemi ve kaynakları gösterir", async () => {
    const { user } = await selectAndStart()
    await screen.findByLabelText("Görüntü risk seviyesi")

    await user.keyboard("b")

    const article = screen.getByRole("article", { name: "Brief" })
    expect(article).toHaveTextContent(brief.text.split("\n")[0])
    expect(article).toHaveTextContent(`Önerilen eylem: ${brief.recommended_action}`)
    expect(within(article).getByText("otomatik özet: LLM yapılandırılmadı")).toBeInTheDocument()
    const sources = within(within(article).getByRole("region", { name: "Kaynaklar" })).getAllByRole("listitem")
    expect(sources.map((li) => li.textContent)).toEqual(brief.sources)
  })

  it("önbellekten gelen sonuçta rozet ve Yeniden değerlendir (recompute: true); LLM Brief'inde model adı", async () => {
    const llmBrief = { ...brief, is_fallback: false, fallback_reason: null, model: "evren/glm-5.3" }
    const bodies = useEvaluationStream([
      { event: "run", data: { run_id: "r-cached", image_id: "img_000860", cached: true } },
      ...steps,
      { event: "brief", data: llmBrief },
    ])
    const { user } = await selectAndStart()

    expect(await screen.findByText("önbellek")).toBeInTheDocument()
    expect(screen.getByText("LLM: evren/glm-5.3")).toBeInTheDocument()
    expect(screen.queryByText("otomatik özet")).not.toBeInTheDocument()

    await user.click(screen.getAllByRole("button", { name: "Yeniden değerlendir" })[0])

    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies).toEqual([
      { image_id: "img_000860", recompute: true },
      { image_id: "img_000860", recompute: true },
    ])
  })

  it("error olayında kısa Türkçe mesaj ve Tekrar dene; tekrar deneme başarılı olur", async () => {
    useEvaluationStream([
      events[0],
      steps[0],
      { event: "error", data: { run_id: "run-fixture-1", message: "Değerlendirme başarısız" } },
    ])
    const { user } = await selectAndStart()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Değerlendirme başarısız")

    server.resetHandlers()
    await user.click(within(alert).getByRole("button", { name: "Tekrar dene" }))

    expect(await screen.findByLabelText("Görüntü risk seviyesi")).toHaveTextContent("Kritik")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("404'te (görüntü backend'de yok) aynı hata durumuna düşer", async () => {
    await selectAndStart(UNEVALUATED)

    expect(await screen.findByRole("alert")).toHaveTextContent("Görüntü veri setinde bulunamadı.")
    expect(screen.getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument()
  })

  it("15 sn yeni olay gelmezse 'Model yanıtı bekleniyor' yazar; ekran boş kalmaz", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    server.use(
      http.post(`${API}/evaluations`, () => {
        const encoder = new TextEncoder()
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(encoder.encode(`event: run\ndata: ${JSON.stringify(events[0].data)}\n\n`))
            // Akış açık kalır: LLM cevabı bekleniyor.
          },
        })
        return new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream" } })
      }),
    )
    const view = renderEkran()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const strip = await screen.findByRole("list", { name: "Görüntüler, çekim anına göre" })
    await user.click(within(strip).getByRole("button", { name: /^img_000860/ }))
    await user.click(screen.getByRole("button", { name: "Risk analizini başlat" }))
    await screen.findByText("Değerlendirme başladı")
    expect(screen.queryByText(/Model yanıtı bekleniyor/)).not.toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(SLOW_AFTER_MS + 10)
    })

    expect(screen.getAllByText("Model yanıtı bekleniyor (en fazla 45 sn)")[0]).toBeInTheDocument()
    view.unmount()
  })

  it("akış sürerken başka kare seçilince eski akış iptal edilir, sonucu ekrana düşmez", async () => {
    useEvaluationStream(events, { delayMs: 25 })
    const { user } = await selectAndStart()
    await screen.findByText(/^Adım 1 · goruntu/)

    const strip = screen.getByRole("list", { name: "Görüntüler, çekim anına göre" })
    await user.click(within(strip).getByRole("button", { name: new RegExp(`^${UNEVALUATED}`) }))

    expect(screen.getByLabelText("Seçili kare")).toHaveTextContent(UNEVALUATED)
    await new Promise((r) => setTimeout(r, 400))
    expect(screen.queryByLabelText("Görüntü risk seviyesi")).not.toBeInTheDocument()
    expect(screen.queryByText(/^Adım \d/)).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Risk analizini başlat" })).toBeEnabled()
  })
})
