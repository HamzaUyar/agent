// MapLibre'nin web worker'ı ayrı bir dosyadan yüklenir; Turbopack onu pakete kopyalamaz.
// Worker ve bağlı olduğu paylaşılan modül public/maplibre/ altına kopyalanır (sürümle eş, repoya girmez).
import { copyFileSync, mkdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const root = join(dirname(fileURLToPath(import.meta.url)), "..")
const from = join(root, "node_modules", "maplibre-gl", "dist")
const to = join(root, "public", "maplibre")
mkdirSync(to, { recursive: true })
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(from, file), join(to, file))
}
console.log("MapLibre worker → public/maplibre/")
