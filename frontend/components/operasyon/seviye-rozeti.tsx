import type { RiskLevel } from "@/lib/api/types"
import { RISK } from "@/lib/labels"
import { cn } from "@/lib/utils"

const TONE: Record<RiskLevel, string> = {
  low: "text-risk-dusuk border-risk-dusuk/50 bg-risk-dusuk/10",
  medium: "text-risk-orta border-risk-orta/50 bg-risk-orta/10",
  high: "text-risk-yuksek border-risk-yuksek/50 bg-risk-yuksek/10",
  critical: "text-risk-kritik border-risk-kritik/60 bg-risk-kritik/15",
}

export const levelText = (level: RiskLevel) => `${RISK[level].shape} ${RISK[level].label}`

/** Risk seviyesi: renk + şekil + kelime; hiçbir zaman yalnızca renk. */
export function SeviyeRozeti({ level, className }: { level: RiskLevel; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-bold whitespace-nowrap",
        TONE[level],
        className,
      )}
    >
      <span aria-hidden>{RISK[level].shape}</span>
      {RISK[level].label}
    </span>
  )
}

/** Yalnızca şekil (dar yerler için); erişilebilir adı kelimedir. */
export function SeviyeSekli({ level, className }: { level: RiskLevel; className?: string }) {
  return (
    <span role="img" aria-label={RISK[level].label} className={cn(TONE[level], "border-0 bg-transparent", className)}>
      {RISK[level].shape}
    </span>
  )
}
