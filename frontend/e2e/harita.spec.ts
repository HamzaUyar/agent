import { expect, test } from "@playwright/test"

import { mockApi as mockZones } from "./mock-api"

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
