"use client"

import { useOperasyon } from "@/store/operasyon"

/** Üst durum çubuğu: seçili kare, seviye, önerilen eylem ve değerlendirme adımları burada akar. */
export function UstCubuk() {
  const zones = useOperasyon((s) => s.zones)

  return (
    <header className="flex h-[var(--ust-cubuk-yukseklik)] items-center gap-4 border-b border-cizgi bg-[var(--ust-cubuk-zemin)] px-4">
      <span className="text-xs font-bold tracking-wider text-metin uppercase">
        {zones.status === "ready" ? zones.data.base.name : "Üs"}
      </span>
      <p role="status" className="text-metin-soluk">
        Zaman akışından bir kare seçin
      </p>
    </header>
  )
}
