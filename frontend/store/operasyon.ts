/**
 * Operasyon ekranının tek seçim deposu: sahne verisi, harita zemini ve çekmecelerin hâli.
 * Sonraki biletlerde seçili Görüntü, değerlendirme ve seçili Temas da burada tutulur.
 */
import { create } from "zustand"

import { getZones } from "@/lib/api/client"
import type { ZonesResponse } from "@/lib/api/types"
import type { Basemap } from "@/lib/harita/types"

export type Side = "left" | "right"
/** Kapalı: yalnız sekme · göz atma: dar şerit · yarım: liste · tam: ayrıntı. */
export type DrawerState = "closed" | "peek" | "half" | "full"
export type LeftPanel = "goruntu" | "sohbet"
export type RightPanel = "risk"
export type RiskTab = "temaslar" | "brief"

export type Drawer<P extends string> = { panel: P | null; state: DrawerState }

export type Load<T> =
  | { status: "idle" | "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string }

type OperasyonState = {
  zones: Load<ZonesResponse>
  loadZones: () => Promise<void>
  basemap: Basemap
  basemapFailed: boolean
  setBasemap: (basemap: Basemap) => void
  basemapError: () => void
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

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : "Bilinmeyen hata")

export const useOperasyon = create<OperasyonState>()((set) => ({
  zones: { status: "idle" },
  loadZones: async () => {
    set({ zones: { status: "loading" } })
    try {
      set({ zones: { status: "ready", data: await getZones() } })
    } catch (e) {
      set({ zones: { status: "error", message: errorMessage(e) } })
    }
  },
  basemap: "uydu",
  basemapFailed: false,
  setBasemap: (basemap) => set({ basemap, basemapFailed: false }),
  basemapError: () => set({ basemap: "duz", basemapFailed: true }),
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
