/**
 * Operasyon ekranının tek seçim deposu. Sonraki biletlerde seçili Görüntü, değerlendirme
 * ve seçili Temas da burada tutulur; şimdilik çekmecelerin hâli.
 */
import { create } from "zustand"

export type Side = "left" | "right"
/** Kapalı: yalnız sekme · göz atma: dar şerit · yarım: liste · tam: ayrıntı. */
export type DrawerState = "closed" | "peek" | "half" | "full"
export type LeftPanel = "goruntu" | "sohbet"
export type RightPanel = "risk"
export type RiskTab = "temaslar" | "brief"

export type Drawer<P extends string> = { panel: P | null; state: DrawerState }

type OperasyonState = {
  left: Drawer<LeftPanel>
  right: Drawer<RightPanel>
  riskTab: RiskTab
  /** En son açılan kenar; Esc önce onu kapatır. */
  lastSide: Side | null
  openLeft: (panel: LeftPanel, state?: DrawerState) => void
  openRight: (tab?: RiskTab, state?: DrawerState) => void
  setDrawerState: (side: Side, state: DrawerState) => void
  close: (side: Side) => void
  setRiskTab: (tab: RiskTab) => void
}

const closed = { panel: null, state: "closed" } as const

export const useOperasyon = create<OperasyonState>()((set) => ({
  left: closed,
  right: closed,
  riskTab: "temaslar",
  lastSide: null,
  openLeft: (panel, state = "half") => set({ left: { panel, state }, lastSide: "left" }),
  openRight: (tab, state = "half") =>
    set((s) => ({
      right: { panel: "risk", state },
      riskTab: tab ?? s.riskTab,
      lastSide: "right",
    })),
  setDrawerState: (side, state) =>
    set((s) =>
      state === "closed"
        ? { [side]: closed }
        : s[side].panel
          ? { [side]: { ...s[side], state } }
          : {},
    ),
  close: (side) => set((s) => ({ [side]: closed, lastSide: s.lastSide === side ? null : s.lastSide })),
  setRiskTab: (riskTab) => set({ riskTab }),
}))
