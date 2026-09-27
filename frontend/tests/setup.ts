import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterAll, afterEach, beforeAll } from "vitest"

import { resetOperasyonStreams, useOperasyon } from "@/store/operasyon"

import { server } from "./msw/server"

// Radix Select jsdom'da olmayan işaretçi yakalama ve kaydırma API'lerini çağırır.
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
Element.prototype.setPointerCapture ??= () => {}
Element.prototype.scrollIntoView ??= () => {}
// Radix ipucu (ok boyutu) ResizeObserver ister; jsdom'da yok.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver
// jsdom'da PointerEvent yok: fireEvent.pointer* çağrılarında pointerId ve clientX taşınsın.
if (typeof globalThis.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    readonly pointerId: number
    readonly pointerType: string
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init)
      this.pointerId = init.pointerId ?? 1
      this.pointerType = init.pointerType ?? "mouse"
    }
  }
  globalThis.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent
}

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
