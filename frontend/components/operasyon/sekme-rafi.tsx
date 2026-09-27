"use client"

import { Image as ImageIcon, Route, ShieldAlert, type LucideIcon } from "lucide-react"

import { SeviyeSimgesi } from "@/components/operasyon/seviye-rozeti"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { useOperasyon, type Side } from "@/store/operasyon"

type Item = {
  id: string
  label: string
  shortcut: string
  icon: LucideIcon
  active: boolean
  onClick: () => void
  /** İkonun köşesindeki küçük gösterge (ör. kapalı panelde yeni Brief'in seviyesi). */
  badge?: React.ReactNode
}

/**
 * Kenar ikon rayı; çekmece kapalıyken de görünür. İkonlar aynı çizgi kalınlığında (lucide),
 * adı ve kısayolu ipucunda; etkin olan ters renk (mürekkep). Mavi kullanılmaz: mavi seçili veri.
 */
export function SekmeRafi({ side }: { side: Side }) {
  const left = useOperasyon((s) => s.left)
  const right = useOperasyon((s) => s.right)
  const izOpen = useOperasyon((s) => s.izOpen)
  const brief = useOperasyon((s) => (s.evaluation?.status === "done" ? s.evaluation.brief : null))
  const { openLeft, openRight, close, toggleIz } = useOperasyon.getState()

  const items: Item[] =
    side === "left"
      ? [
          {
            id: "goruntu",
            label: "Görüntü",
            shortcut: "G",
            icon: ImageIcon,
            active: left.panel === "goruntu",
            onClick: () => (left.panel === "goruntu" ? close("left") : openLeft("goruntu")),
          },
        ]
      : [
          {
            id: "iz",
            label: "İz analizi",
            shortcut: "I",
            icon: Route,
            active: izOpen,
            onClick: () => toggleIz(),
          },
          {
            id: "risk",
            label: "Risk & Araçlar",
            shortcut: "R",
            icon: ShieldAlert,
            active: right.panel !== null,
            onClick: () => (right.panel ? close("right") : openRight("temaslar")),
            badge: brief && right.panel === null ? <SeviyeSimgesi level={brief.risk_level} /> : undefined,
          },
        ]

  return (
    <nav
      aria-label={side === "left" ? "Sol paneller" : "Sağ paneller"}
      className="flex w-[var(--cekmece-sekme-genislik)] shrink-0 flex-col items-center gap-1.5 py-3"
    >
      {items.map((item) => (
        <Tooltip key={item.id}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={item.onClick}
              aria-pressed={item.active}
              aria-label={item.label}
              aria-keyshortcuts={item.shortcut}
              className={cn(
                "relative flex size-9 items-center justify-center rounded-md border transition-colors [&_svg]:size-[18px]",
                item.active
                  ? "border-birincil bg-birincil text-birincil-uzeri"
                  : "border-transparent text-metin-ikincil hover:border-cizgi hover:bg-kart-hover hover:text-metin",
              )}
            >
              <item.icon aria-hidden strokeWidth={1.75} />
              {/* Etkin panel: ikonun çekmeceye bakan kenarında ince çizgi (renkten bağımsız ikinci işaret). */}
              {item.active && (
                <span
                  aria-hidden
                  className={cn(
                    "absolute inset-y-1.5 w-[3px] rounded-full bg-birincil",
                    side === "left" ? "-right-[7px]" : "-left-[7px]",
                  )}
                />
              )}
              {item.badge && (
                <span aria-hidden className="absolute -top-0.5 -right-0.5 [--sv-boyut:8px] [--sv-bosluk:var(--zemin)]">
                  {item.badge}
                </span>
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent side={side === "left" ? "right" : "left"} sideOffset={6}>
            {item.label}
            <kbd className="rounded border border-current/30 px-1 font-mono text-[10px]">{item.shortcut}</kbd>
          </TooltipContent>
        </Tooltip>
      ))}
    </nav>
  )
}
