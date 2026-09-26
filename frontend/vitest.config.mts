import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

const NODE_MAJOR = Number(process.versions.node.split(".")[0])

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:3000" } },
    setupFiles: ["./tests/setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "e2e", ".next"],
    restoreMocks: true,
    // Node 25+ kendi (deneysel) localStorage'ını tanımlıyor ve jsdom'unkini gölgeliyor;
    // dosya yolu verilmeyince clear() gibi metodları yok. Testlerde jsdom'unki kullanılsın.
    // Bayrak Node 22'de geldi; eski sürümler tanımıyor.
    execArgv: NODE_MAJOR >= 22 ? ["--no-experimental-webstorage"] : [],
  },
})
