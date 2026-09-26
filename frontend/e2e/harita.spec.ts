import { expect, test, type Page } from "@playwright/test"

import zones from "../tests/fixtures/zones.json" with { type: "json" }

/** Backend'siz: `/api/zones` backend'den üretilmiş referans veriyle cevaplanır. */
async function mockZones(page: Page) {
  await page.route("**/api/zones", (route) => route.fulfill({ json: zones }))
}

test("gerçek MapLibre: Üs, halka etiketleri ve 8 Bölge işaretle görünür; zemin atfı var", async ({ page }) => {
  await mockZones(page)
  await page.goto("/")

  const panel = page.getByRole("region", { name: "Harita paneli" })
  await expect(panel.locator("canvas.maplibregl-canvas")).toBeVisible()
  await expect(panel.getByRole("button", { name: "Üs: Merkez Us" })).toBeVisible()
  await expect(panel.getByRole("button", { name: /^Bölge: / })).toHaveCount(8)
  await expect(panel.getByText("3 km", { exact: true })).toBeVisible()
  await expect(panel.locator(".maplibregl-ctrl-attrib")).toContainText("Esri")
  await page.waitForTimeout(1500)
  await expect(panel.getByText(/Harita zemini yüklenemedi/)).toHaveCount(0)
})

test("zemin yüklenemezse düz zemine düşer, katmanlar kalır", async ({ page }) => {
  await mockZones(page)
  await page.route(/arcgisonline\.com|openfreemap\.org/, (route) => route.abort("internetdisconnected"))
  await page.goto("/")

  const panel = page.getByRole("region", { name: "Harita paneli" })
  await expect(panel.getByText(/Harita zemini yüklenemedi; düz zemin gösteriliyor/)).toBeVisible()
  await expect(panel.getByRole("button", { name: /^Bölge: / })).toHaveCount(8)
  await expect(panel.getByRole("button", { name: "Üs: Merkez Us" })).toBeVisible()
})
