/**
 * Operasyon ekranının tek seçim deposu: sahne verisi ve harita zemini, Görüntü listesi ve
 * seçili Görüntü, aktif değerlendirme ve çekmecelerin hâli. Sonraki biletlerde seçili Temas da burada.
 */
import { create } from "zustand"

import { ApiError, getImage, getImages, getZones, streamEvaluation } from "@/lib/api/client"
import type {
  Brief,
  ImageDetail,
  ImageSummary,
  StepEvent,
  ZonesResponse,
} from "@/lib/api/types"
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

/** Bu süre boyunca yeni olay gelmezse "model yanıtı bekleniyor" gösterilir. */
export const SLOW_AFTER_MS = 15_000

export type Evaluation = {
  imageId: string
  status: "streaming" | "done" | "error"
  runId: string | null
  cached: boolean
  steps: StepEvent[]
  brief: Brief | null
  error: string | null
  /** Son olaydan beri SLOW_AFTER_MS geçti. */
  slow: boolean
}

type OperasyonState = {
  zones: Load<ZonesResponse>
  loadZones: () => Promise<void>
  basemap: Basemap
  basemapFailed: boolean
  setBasemap: (basemap: Basemap) => void
  basemapError: () => void

  images: Load<ImageSummary[]>
  loadImages: () => Promise<void>
  selectedImageId: string | null
  imageDetail: Load<ImageDetail>
  /** Kare seçer; aktif değerlendirme iptal edilir ve temizlenir. */
  selectImage: (imageId: string) => void
  /** Çekim anına göre önceki/sonraki kare. */
  stepImage: (delta: 1 | -1) => void

  evaluation: Evaluation | null
  startEvaluation: (recompute?: boolean) => Promise<void>

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

const byCaptureTime = (a: ImageSummary, b: ImageSummary) =>
  a.capture_time.localeCompare(b.capture_time) || a.image_id.localeCompare(b.image_id)

/** Aktif akışın iptali ve bekleme zamanlayıcısı; durumda değil, çünkü görüntülenmiyorlar. */
let streamAbort: AbortController | null = null
let slowTimer: ReturnType<typeof setTimeout> | undefined

function stopStream() {
  streamAbort?.abort()
  streamAbort = null
  clearTimeout(slowTimer)
}

export const useOperasyon = create<OperasyonState>()((set, get) => {
  /** Yalnızca hâlâ aktif olan değerlendirmeyi günceller (iptal edilmiş akışın geç olayları yok sayılır). */
  const patchEvaluation = (signal: AbortSignal, patch: Partial<Evaluation>) => {
    if (signal.aborted) return
    set((s) => (s.evaluation ? { evaluation: { ...s.evaluation, ...patch } } : {}))
  }

  return {
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

    images: { status: "idle" },
    loadImages: async () => {
      set({ images: { status: "loading" } })
      try {
        set({ images: { status: "ready", data: (await getImages()).sort(byCaptureTime) } })
      } catch (e) {
        set({ images: { status: "error", message: errorMessage(e) } })
      }
    },
    selectedImageId: null,
    imageDetail: { status: "idle" },
    selectImage: (imageId) => {
      if (get().selectedImageId === imageId) return
      stopStream()
      set({ selectedImageId: imageId, imageDetail: { status: "loading" }, evaluation: null })
      getImage(imageId).then(
        (data) => get().selectedImageId === imageId && set({ imageDetail: { status: "ready", data } }),
        (e) =>
          get().selectedImageId === imageId &&
          set({ imageDetail: { status: "error", message: errorMessage(e) } }),
      )
    },
    stepImage: (delta) => {
      const { images, selectedImageId, selectImage } = get()
      if (images.status !== "ready" || images.data.length === 0) return
      const index = images.data.findIndex((i) => i.image_id === selectedImageId)
      const next =
        index === -1
          ? delta === 1
            ? 0
            : images.data.length - 1
          : Math.min(images.data.length - 1, Math.max(0, index + delta))
      selectImage(images.data[next].image_id)
    },

    evaluation: null,
    startEvaluation: async (recompute = false) => {
      const imageId = get().selectedImageId
      if (!imageId) return
      stopStream()
      const controller = new AbortController()
      streamAbort = controller
      const { signal } = controller
      const armSlowTimer = () => {
        clearTimeout(slowTimer)
        slowTimer = setTimeout(() => patchEvaluation(signal, { slow: true }), SLOW_AFTER_MS)
      }
      set({
        evaluation: {
          imageId,
          status: "streaming",
          runId: null,
          cached: false,
          steps: [],
          brief: null,
          error: null,
          slow: false,
        },
      })
      armSlowTimer()
      try {
        for await (const event of streamEvaluation(imageId, recompute, signal)) {
          if (signal.aborted) return
          armSlowTimer()
          switch (event.event) {
            case "run":
              patchEvaluation(signal, { runId: event.data.run_id, cached: event.data.cached, slow: false })
              break
            case "step":
              patchEvaluation(signal, {
                steps: [...(get().evaluation?.steps ?? []), event.data],
                slow: false,
              })
              break
            case "brief": {
              patchEvaluation(signal, { status: "done", brief: event.data, slow: false })
              // Listedeki son seviye bu değerlendirmeyle güncellenir (zaman akışı, kartlar, filtre).
              const level = event.data.risk_level
              if (!signal.aborted)
                set((s) =>
                  s.images.status === "ready"
                    ? {
                        images: {
                          status: "ready",
                          data: s.images.data.map((i) =>
                            i.image_id === imageId ? { ...i, last_risk_level: level } : i,
                          ),
                        },
                      }
                    : {},
                )
              // Brief gelince sağ çekmece kendiliğinden göz atma hâlinde belirir (açıksa dokunulmaz).
              if (!signal.aborted && get().right.panel === null) set({ right: { panel: "risk", state: "peek" } })
              break
            }
            case "error":
              patchEvaluation(signal, { status: "error", error: event.data.message, slow: false })
              break
          }
        }
        const current = get().evaluation
        if (!signal.aborted && current?.status === "streaming") {
          patchEvaluation(signal, { status: "error", error: "Değerlendirme yarıda kesildi", slow: false })
        }
      } catch (e) {
        if (signal.aborted) return
        const message =
          e instanceof ApiError && e.status === 404
            ? "Görüntü veri setinde bulunamadı."
            : "Değerlendirme başlatılamadı. Backend'e ulaşılamıyor olabilir."
        patchEvaluation(signal, { status: "error", error: message, slow: false })
      } finally {
        if (streamAbort === controller) {
          clearTimeout(slowTimer)
          streamAbort = null
        }
      }
    },

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
  }
})

/** Testler için: akışı ve zamanlayıcıyı durdurur. */
export function resetOperasyonStreams() {
  stopStream()
}
