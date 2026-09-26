import { expect, test } from "@playwright/test"

import { mockApi } from "./mock-api"

test("sayfa açılır; çekmece klavyeyle açılıp harita panelini daraltır, Esc kapatır", async ({ page }) => {
  await mockApi(page)
  await page.goto("/")
  await expect(page.getByText("Zaman akışından bir kare seçin")).toBeVisible()

  const map = page.getByRole("region", { name: "Harita paneli" })
  const fullWidth = (await map.boundingBox())!.width

  await page.keyboard.press("r")
  const drawer = page.getByRole("region", { name: "Risk & Temaslar" })
  await expect(drawer).toHaveAttribute("data-state", "half")
  await expect.poll(async () => (await map.boundingBox())!.width).toBeLessThan(fullWidth - 200)
  await expect(map).toBeVisible()

  await page.keyboard.press("Escape")
  await expect(drawer).toBeHidden()
})
