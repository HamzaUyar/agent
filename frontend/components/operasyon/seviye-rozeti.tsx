import type { RiskLevel } from "@/lib/api/types"
import { RISK } from "@/lib/labels"
import { cn } from "@/lib/utils"

/**
 * Rozet vurgusu seviyeyle artar (renkten bağımsız ikinci kanal): düşük yalnız çerçeve, orta ve yüksek
 * açık dolgu, kritik tam dolgu. Değerlendirilmedi kesikli ve gri.
 */
const TONE: Record<RiskLevel, string> = {
  low: "border-seviye-dusuk text-seviye-dusuk",
  medium: "border-seviye-orta/70 bg-[var(--seviye-orta-zemin)] text-seviye-orta",
  high: "border-seviye-yuksek/70 bg-[var(--seviye-yuksek-zemin)] text-seviye-yuksek",
  // Tam dolgu; içindeki baklava dolgu renginin üstünde okunsun diye ters renkte.
  critical:
    "border-seviye-kritik bg-seviye-kritik text-[color:var(--seviye-kritik-uzeri)] [--sv-dolgu:var(--seviye-kritik-uzeri)] [--sv-halka:none] [--sv:var(--seviye-kritik-uzeri)]",
}

export const levelText = (level: RiskLevel) => `${RISK[level].shape} ${RISK[level].label}`

/** Seviye simgesi: baklava, dolgusu seviyeyle artar. `level` yoksa "değerlendirilmedi" (kesikli gri). */
export function SeviyeSimgesi({ level, className }: { level: RiskLevel | null; className?: string }) {
  return (
    <span aria-hidden className={cn("seviye-simge", `seviye--${level ?? "none"}`, className)}>
      {level && RISK[level].shape}
    </span>
  )
}

/** Risk seviyesi: renk + simge dolgusu + kelime; hiçbir zaman yalnızca renk. */
export function SeviyeRozeti({ level, className }: { level: RiskLevel; className?: string }) {
  return (
    <span
      className={cn(
        `seviye--${level}`,
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs leading-none font-bold whitespace-nowrap",
        TONE[level],
        className,
      )}
    >
      <span aria-hidden className="seviye-simge">
        {RISK[level].shape}
      </span>
      {RISK[level].label}
    </span>
  )
}

/** Henüz değerlendirilmemiş kare: kesikli, gri; seviye rozetleriyle aynı yapıda. */
export function DegerlendirilmediRozeti({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "seviye--none inline-flex items-center gap-1 rounded border border-dashed border-cizgi-guclu px-1.5 py-0.5 text-xs leading-none whitespace-nowrap text-metin-soluk",
        className,
      )}
    >
      <span aria-hidden className="seviye-simge" />
      değerlendirilmedi
    </span>
  )
}

/** Yalnızca simge (dar yerler için); erişilebilir adı kelimedir. */
export function SeviyeSekli({ level, className }: { level: RiskLevel; className?: string }) {
  return (
    <span role="img" aria-label={RISK[level].label} className={cn("inline-flex", `seviye--${level}`, className)}>
      <span aria-hidden className="seviye-simge">
        {RISK[level].shape}
      </span>
    </span>
  )
}
