"use client"

import { cn } from "@/lib/utils"
import { useOperasyon, type LeftPanel, type RiskTab, type Side } from "@/store/operasyon"

type Tab = { id: string; label: string; shortcut: string; active: boolean; onClick: () => void }

/** Kenardaki dikey çekmece sekmeleri; çekmece kapalıyken de görünür. */
export function SekmeRafi({ side }: { side: Side }) {
  const { left, right, riskTab, openLeft, openRight, close } = useOperasyon()

  const leftTab = (panel: LeftPanel, label: string, shortcut: string): Tab => ({
    id: panel,
    label,
    shortcut,
    active: left.panel === panel,
    onClick: () => (left.panel === panel ? close("left") : openLeft(panel)),
  })
  const rightTab = (tab: RiskTab, label: string, shortcut: string): Tab => ({
    id: tab,
    label,
    shortcut,
    active: right.panel !== null && riskTab === tab,
    onClick: () =>
      right.panel && right.state !== "peek" && riskTab === tab ? close("right") : openRight(tab),
  })

  const tabs =
    side === "left"
      ? [leftTab("goruntu", "Görüntü", "G")]
      : [rightTab("temaslar", "Risk & Temaslar", "R"), rightTab("brief", "Brief", "B")]

  return (
    <nav
      aria-label={side === "left" ? "Sol çekmeceler" : "Sağ çekmeceler"}
      className="flex w-[var(--cekmece-sekme-genislik)] shrink-0 flex-col items-center gap-2 py-3"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={tab.onClick}
          aria-pressed={tab.active}
          aria-keyshortcuts={tab.shortcut}
          title={`${tab.label} (${tab.shortcut})`}
          className={cn(
            "rounded-md border px-1.5 py-3 text-xs font-bold [writing-mode:vertical-rl]",
            side === "left" && "rotate-180",
            tab.active
              ? "border-secim bg-secim-zemin text-metin"
              : "border-cizgi bg-kart text-metin-ikincil hover:text-metin",
          )}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  )
}
