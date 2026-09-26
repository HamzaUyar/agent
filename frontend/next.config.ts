import type { NextConfig } from "next"

/** Backend (FastAPI). Tarayıcı ona doğrudan gitmez; `/api/*` buradan yönlenir (backend'de CORS yok). */
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

const nextConfig: NextConfig = {
  experimental: {
    // Rewrite proxy'si varsayılan olarak 30 sn sonra bağlantıyı keser; yeniden hesaplanan bir
    // değerlendirme (birkaç LLM çağrısı) SSE akışında 30 sn'yi rahatça aşar.
    proxyTimeout: 180_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }]
  },
}

export default nextConfig
