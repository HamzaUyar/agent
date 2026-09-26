import { expect, test } from "@playwright/test"

import { mockApi } from "./mock-api"

test("zaman akışından kare seç → ayak izine yaklaş → analiz akar → seviye ve eylem üst çubukta", async ({ page }) => {
  await mockApi(page)
  await page.goto("/")

  await page.getByRole("list", { name: "Görüntüler, çekim anına göre" }).getByRole("button", { name: /^img_000860/ }).click()
  await expect(page.getByLabel("Seçili kare", { exact: true })).toHaveText("img_000860 · Dogu Yolu · 14:10")

  await page.getByRole("button", { name: "Risk analizini başlat" }).click()
  const level = page.getByLabel("Görüntü risk seviyesi", { exact: true })
  await expect(level).toContainText("Kritik")
  await expect(page.getByRole("region", { name: "Risk & Temaslar" })).toHaveAttribute("data-state", "half")
})
