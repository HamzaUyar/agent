import { http } from "msw"
import { describe, expect, it } from "vitest"

import { API, sseResponse } from "@/tests/msw/handlers"
import { server } from "@/tests/msw/server"

import { ApiError, getImage, getZones, streamEvaluation } from "./client"

describe("API istemcisi (MSW ile taklit edilen backend)", () => {
  it("üs ve 8 bölgeyi zones.json biçiminde okur", async () => {
    const zones = await getZones()

    expect(zones.base.name).toBe("Merkez Us")
    expect(zones.zones).toHaveLength(8)
    expect(zones.zones[0].center).toHaveLength(2)
  })

  it("veri setinde olmayan görüntüde backend'in mesajıyla ApiError fırlatır", async () => {
    await expect(getImage("img_999999")).rejects.toMatchObject({
      status: 404,
      message: "Görüntü veri setinde yok: img_999999",
    })
  })

  it("değerlendirme akışını run → step… → brief olarak verir", async () => {
    const events = []
    for await (const e of streamEvaluation("img_000860", false)) events.push(e)

    expect(events[0]).toMatchObject({ event: "run", data: { image_id: "img_000860", cached: false } })
    expect(events.filter((e) => e.event === "step")).toHaveLength(8)
    const last = events.at(-1)
    expect(last?.event).toBe("brief")
    if (last?.event === "brief") expect(last.data.risk_level).toBe("critical")
  })

  it("akış başlamadan dönen 404'ü ApiError'a çevirir", async () => {
    await expect(async () => {
      for await (const _ of streamEvaluation("img_999999", false)) void _
    }).rejects.toBeInstanceOf(ApiError)
  })

  it("recompute bayrağını gövdeye koyar ve iptal edilebilir", async () => {
    let body: unknown
    server.use(
      http.post(`${API}/evaluations`, async ({ request }) => {
        body = await request.json()
        return sseResponse([{ event: "run", data: { run_id: "r", image_id: "x", cached: false } }], {
          delayMs: 50,
        })
      }),
    )
    const controller = new AbortController()
    const stream = streamEvaluation("img_000860", true, controller.signal)
    const first = stream.next()
    controller.abort()

    await expect(first).rejects.toThrow()
    expect(body).toEqual({ image_id: "img_000860", recompute: true })
  })
})
