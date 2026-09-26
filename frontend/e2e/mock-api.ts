import type { Page } from "@playwright/test"

import imageDetails from "../tests/fixtures/image_details.json" with { type: "json" }
import images from "../tests/fixtures/images.json" with { type: "json" }
import evaluationEvents from "../tests/fixtures/img_000860.events.json" with { type: "json" }
import zones from "../tests/fixtures/zones.json" with { type: "json" }

/** 1×1 gri JPEG; görüntü dosyalarının yerine (veri paketi repoda yok). */
const PIXEL = Buffer.from(
  "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=",
  "base64",
)

/**
 * Backend'siz: `/api/*` backend'den üretilmiş referans veriyle (tests/fixtures) cevaplanır.
 * Gerçek backend'le koşan testler bunu çağırmaz.
 */
export async function mockApi(page: Page) {
  await page.route("**/api/zones", (route) => route.fulfill({ json: zones }))
  await page.route("**/api/images", (route) => route.fulfill({ json: images }))
  await page.route(/\/api\/images\/[^/]+\/file$/, (route) =>
    route.fulfill({ body: PIXEL, contentType: "image/jpeg" }),
  )
  await page.route(/\/api\/images\/[^/]+$/, (route) => {
    const id = route.request().url().split("/").pop()!
    const detail = (imageDetails as Record<string, unknown>)[id]
    return detail
      ? route.fulfill({ json: detail })
      : route.fulfill({ status: 404, json: { detail: `Görüntü veri setinde yok: ${id}` } })
  })
  await page.route("**/api/evaluations", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: evaluationEvents.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join(""),
    }),
  )
}
