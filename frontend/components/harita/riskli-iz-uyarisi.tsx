"use client"

import { SeviyeSimgesi } from "@/components/operasyon/seviye-rozeti"
import type { RiskLevel } from "@/lib/api/types"
import { gorunenler } from "@/lib/iz"
import { RISK } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

import { useIzTracks } from "./iz-katmani"

const WATCHED: RiskLevel[] = ["critical", "high"]

/**
 * İz analizi oynarken ekranda (süzgece uyan, o an kaydı olan) kritik ya da yüksek seviyeli iz varsa
 * haritanın sol üstünde, yakınlaştırma düğmelerinin altında yavaş yanıp sönen uyarı. Yalnızca oynarken.
 * Ekran okuyucuya seviye adı duyurulur; her dakika değişen sayı duyurulmaz.
 */
export function RiskliIzUyarisi() {
  const izOpen = useOperasyon((s) => s.izOpen)
  const status = useOperasyon((s) => s.izStatus)
  const time = useOperasyon((s) => s.izTime)
  const { filtered } = useIzTracks()
  if (!izOpen || status !== "oynuyor" || time === null) return null

  const active = gorunenler(filtered, time)
  const counts = WATCHED.map((level) => ({ level, n: active.filter((t) => t.level === level).length })).filter(
    (c) => c.n > 0,
  )
  if (counts.length === 0) return null

  return (
    <div
      role="status"
      aria-label="Riskli iz uyarısı"
      className="absolute top-[76px] left-2.5 z-20 flex flex-col items-start gap-1"
    >
      {counts.map(({ level, n }) => (
        <span
          key={level}
          className={cn(
            `seviye--${level}`,
            "riskli-iz-uyarisi inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-bold shadow-golge-yuksek",
            level === "critical"
              ? "border-seviye-kritik bg-seviye-kritik text-[color:var(--seviye-kritik-uzeri)] [--sv-dolgu:var(--seviye-kritik-uzeri)] [--sv-halka:none] [--sv:var(--seviye-kritik-uzeri)]"
              : "border-seviye-yuksek bg-[var(--seviye-yuksek-zemin)] text-seviye-yuksek",
          )}
        >
          <SeviyeSimgesi level={level} />
          {RISK[level].label} riskli iz
          <span aria-hidden className="font-mono font-normal">
            · {n}
          </span>
        </span>
      ))}
    </div>
  )
}
