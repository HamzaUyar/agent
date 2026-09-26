import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterAll, afterEach, beforeAll } from "vitest"

import { resetOperasyonStreams, useOperasyon } from "@/store/operasyon"

import { server } from "./msw/server"

// Radix Select jsdom'da olmayan işaretçi yakalama ve kaydırma API'lerini çağırır.
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
Element.prototype.scrollIntoView ??= () => {}

const initialState = useOperasyon.getState()

/** Sayfa düzeni (app/layout.tsx) gibi koyu temayla başlar. */
function resetTheme() {
  document.documentElement.classList.add("dark")
  localStorage.clear()
}
resetTheme()

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => {
  cleanup()
  resetOperasyonStreams()
  server.resetHandlers()
  useOperasyon.setState(initialState, true)
  resetTheme()
})
afterAll(() => server.close())
