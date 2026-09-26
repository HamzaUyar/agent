/**
 * Backend'i taklit eden MSW işleyicileri. Veri, backend'in gerçek kodundan üretilmiş
 * referans örnektir (tests/fixtures/README.md): img_000860, 14:10, Doğu Yolu, T0122.
 */
import { delay, http, HttpResponse } from "msw"

import imageDetails from "../fixtures/image_details.json"
import images from "../fixtures/images.json"
import evaluationEvents from "../fixtures/img_000860.events.json"
import zones from "../fixtures/zones.json"

export const API = "http://localhost:3000/api"

export type SseEvent = { event: string; data: unknown }

/** Olayları SSE gövdesi olarak, her olay ayrı bir parça hâlinde ve isteğe bağlı gecikmeyle akıtır. */
export function sseResponse(events: SseEvent[], { delayMs = 0 } = {}) {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const { event, data } of events) {
        if (delayMs) await delay(delayMs)
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`))
      }
      controller.close()
    },
  })
  return new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream" } })
}

export const fixtures = {
  zones,
  images,
  imageDetails: imageDetails as Record<string, unknown>,
  evaluationEvents: evaluationEvents as SseEvent[],
}

export const handlers = [
  http.get(`${API}/zones`, () => HttpResponse.json(fixtures.zones)),
  http.get(`${API}/images`, () => HttpResponse.json(fixtures.images)),
  http.get(`${API}/images/:imageId`, ({ params }) => {
    const detail = fixtures.imageDetails[params.imageId as string]
    return detail
      ? HttpResponse.json(detail)
      : HttpResponse.json({ detail: `Görüntü veri setinde yok: ${params.imageId}` }, { status: 404 })
  }),
  http.post(`${API}/evaluations`, async ({ request }) => {
    const body = (await request.json()) as { image_id: string }
    if (body.image_id !== "img_000860") {
      return HttpResponse.json(
        { detail: `Görüntü veri setinde yok: ${body.image_id}` },
        { status: 404 },
      )
    }
    return sseResponse(fixtures.evaluationEvents)
  }),
]
