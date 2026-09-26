import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterAll, afterEach, beforeAll } from "vitest"

import { resetOperasyonStreams, useOperasyon } from "@/store/operasyon"

import { server } from "./msw/server"

const initialState = useOperasyon.getState()

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => {
  cleanup()
  resetOperasyonStreams()
  server.resetHandlers()
  useOperasyon.setState(initialState, true)
})
afterAll(() => server.close())
