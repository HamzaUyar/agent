/**
 * Operasyon ekranının tek seçim deposu: sahne verisi ve harita zemini, Görüntü listesi ve
 * seçili Görüntü, aktif değerlendirme ve çekmecelerin hâli. Sonraki biletlerde seçili Temas da burada.
 */
import { create } from "zustand"

import { ApiError, getImage, getImages, getTracks, getZones, streamEvaluation } from "@/lib/api/client"
import type {
  Brief,
  Certainty,
  ImageDetail,
  ImageSummary,
  StepEvent,
  TrackOverview,
  ZonesResponse,
} from "@/lib/api/types"
import { IZ_SEVIYELERI, type IzHizi, type IzSeviyesi } from "@/lib/iz"
import type { Basemap } from "@/lib/harita/types"
import { uygulaTema, type Tema } from "@/lib/tema"

export type Side = "left" | "right"
/**
 * Kapalı: yalnız ray ikonu · yarım: kullanıcının ayarladığı (saklanan) genişlikte açık ·
 * tam: geniş görünüm. Genişlik ayrı tutulur (`drawerWidth`).
 */
export type DrawerState = "closed" | "half" | "full"
export type LeftPanel = "goruntu"
export type RightPanel = "risk"
export type RiskTab = "temaslar" | "brief"

export type Drawer<P extends string> = { panel: P | null; state: DrawerState }

/** İz analizi oynatması: hiç başlamadı (bütün yollar statik) · oynuyor · duraklatıldı. */
export type IzDurumu = "hazir" | "oynuyor" | "duraklatildi"

const GENISLIK_ANAHTARI = "operasyon-cekmece-genislik"
const ZAMAN_AKISI_ANAHTARI = "operasyon-zaman-akisi-acik"

function oku<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}
function yaz(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Depolama kapalı: ayar bu oturumda geçerli.
  }
}

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
  /** Açık / koyu tema; değişince `<html>` sınıfı ve kayıt da güncellenir. */
  theme: Tema
  setTheme: (theme: Tema) => void

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
  /** Seçili kareyi bırakır (Görüntü çekmecesi kapanınca); süren analiz varsa bırakmaz. */
  clearImage: () => void
  /** Çekim anına göre önceki/sonraki kare. */
  stepImage: (delta: 1 | -1) => void

  evaluation: Evaluation | null
  startEvaluation: (recompute?: boolean) => Promise<void>

  /** Seçili Temas (lib/temas.ts `contactKey`); yalnızca o değerlendirme boyunca geçerli. */
  selectedContactKey: string | null
  /** Temas'ı seçer: harita, görüntü ve çekmece ona odaklanır; çekmece yarım açılır. */
  selectContact: (key: string | null) => void

  left: Drawer<LeftPanel>
  right: Drawer<RightPanel>
  /** Taraf başına kullanıcının ayarladığı genişlik (px); `null`: varsayılan. Tarayıcıda saklanır. */
  drawerWidth: Record<Side, number | null>
  setDrawerWidth: (side: Side, px: number) => void

  /**
   * Tarayıcıda saklanan tercihleri (çekmece genişliği, alt panel) uygular. Sayfa ilk çizimi sunucu
   * çıktısıyla aynı varsayılanlarla yapar (hidrasyon uyuşsun); tercihler bağlandıktan sonra gelir.
   */
  loadPreferences: () => void

  /** "Günün görüntüleri" alt paneli açık mı (varsayılan kapalı; saklanır). */
  timelineOpen: boolean
  setTimelineOpen: (open: boolean) => void

  /** Araçlar listesinin kesinlik süzgeci; `null`: hepsi. */
  certaintyFilter: Certainty | null
  setCertaintyFilter: (certainty: Certainty | null) => void

  /** İz analizi: günün bütün track'leri, seviye süzgeci ve zaman oynatması. */
  izOpen: boolean
  toggleIz: (open?: boolean) => void
  tracks: Load<TrackOverview[]>
  loadTracks: () => Promise<void>
  izLevels: IzSeviyesi[]
  setIzLevels: (levels: IzSeviyesi[]) => void
  izStatus: IzDurumu
  /** Simülasyon zamanı (dakika). Oynarken her karede değil, dakika değiştikçe yazılır. */
  izTime: number | null
  setIzTime: (minutes: number) => void
  izSpeed: IzHizi
  setIzSpeed: (speed: IzHizi) => void
  play: () => void
  pause: () => void
  resetIz: () => void
  izHighlight: string | null
  setIzHighlight: (trackId: string | null) => void
  /**
   * Bir track'in bittiği kareye geçer: kareyi seçer ve Görüntü çekmecesini açar; analizi başlatmaz
   * (operatör "Risk analizini başlat"a basar). Analiz bitince o track'in aracı seçili gelir.
   */
  gotoTrackImage: (imageId: string, trackId: string) => void
  /** Analiz bitince seçilecek araç (track kimliği); başka kare seçilince unutulur. */
  pendingContactKey: string | null
  /** Haritada boş bir yere tıklandı: araç seçimi ve iz vurgusu kalkar. */
  clearMapSelection: () => void
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
    theme: "koyu",
    setTheme: (theme) => {
      uygulaTema(theme)
      set({ theme })
    },

    zones: { status: "idle" },
    loadZones: async () => {
      set({ zones: { status: "loading" } })
      try {
        set({ zones: { status: "ready", data: await getZones() } })
      } catch (e) {
        set({ zones: { status: "error", message: errorMessage(e) } })
      }
    },
    basemap: "sokak",
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
      set({
        selectedImageId: imageId,
        imageDetail: { status: "loading" },
        evaluation: null,
        selectedContactKey: null,
        pendingContactKey: null,
        certaintyFilter: null,
      })
      getImage(imageId).then(
        (data) => get().selectedImageId === imageId && set({ imageDetail: { status: "ready", data } }),
        (e) =>
          get().selectedImageId === imageId &&
          set({ imageDetail: { status: "error", message: errorMessage(e) } }),
      )
    },
    clearImage: () => {
      if (get().evaluation?.status === "streaming") return
      stopStream()
      set({
        selectedImageId: null,
        imageDetail: { status: "idle" },
        evaluation: null,
        selectedContactKey: null,
        pendingContactKey: null,
      })
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
      // Analiz başlayınca adımlar görünsün: Risk & Temaslar kapalıysa yarım açılır (açıksa dokunulmaz).
      if (get().right.panel === null) get().openRight("temaslar")
      set({
        selectedContactKey: null,
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
              // "Görüntüye git" ile gelinen track'in aracı seçili gelir.
              const pending = get().pendingContactKey
              if (!signal.aborted && pending) {
                set({ pendingContactKey: null })
                if (event.data.contacts.some((c) => c.track_id === pending)) get().selectContact(pending)
              }
              // İz analizi açıksa track seviyeleri bu değerlendirmeyle yenilenir.
              if (!signal.aborted && get().izOpen) void get().loadTracks()
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

    selectedContactKey: null,
    selectContact: (key) =>
      set((s) =>
        key === null
          ? { selectedContactKey: null }
          : {
              selectedContactKey: key,
              riskTab: "temaslar",
              lastSide: "right",
              right: {
                panel: "risk",
                state: s.right.panel && s.right.state === "full" ? "full" : "half",
              },
            },
      ),

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
    close: (side) => {
      set((s) => ({ [side]: closed, lastSide: s.lastSide === side ? null : s.lastSide }))
      // Görüntü çekmecesi kapanınca seçili kare (ve haritadaki ayak izi) bırakılır.
      if (side === "left") get().clearImage()
    },
    setRiskTab: (riskTab) => set({ riskTab }),
    drawerWidth: { left: null, right: null },
    loadPreferences: () =>
      set((s) => ({
        drawerWidth: oku(GENISLIK_ANAHTARI, s.drawerWidth),
        timelineOpen: oku(ZAMAN_AKISI_ANAHTARI, s.timelineOpen),
      })),
    setDrawerWidth: (side, px) =>
      set((s) => {
        const drawerWidth = { ...s.drawerWidth, [side]: Math.round(px) }
        yaz(GENISLIK_ANAHTARI, drawerWidth)
        return { drawerWidth, [side]: { ...s[side], state: "half" } }
      }),

    timelineOpen: false,
    setTimelineOpen: (timelineOpen) => {
      yaz(ZAMAN_AKISI_ANAHTARI, timelineOpen)
      set({ timelineOpen })
    },

    certaintyFilter: null,
    setCertaintyFilter: (certaintyFilter) => set({ certaintyFilter }),

    // Açılışta İz analizi açık: günün bütün track'leri, hazır hâlinde.
    izOpen: true,
    toggleIz: (open) => {
      const next = open ?? !get().izOpen
      set({ izOpen: next, ...(next ? {} : { izStatus: "hazir", izTime: null, izHighlight: null }) })
      if (next && get().tracks.status !== "ready") void get().loadTracks()
    },
    tracks: { status: "idle" },
    loadTracks: async () => {
      if (get().tracks.status !== "ready") set({ tracks: { status: "loading" } })
      try {
        set({ tracks: { status: "ready", data: await getTracks() } })
      } catch (e) {
        // Yüklü veri varken arka plan yenilemesi başarısızsa eldeki track'ler kalır.
        if (get().tracks.status !== "ready") set({ tracks: { status: "error", message: errorMessage(e) } })
      }
    },
    izLevels: [...IZ_SEVIYELERI],
    setIzLevels: (izLevels) => set({ izLevels }),
    izStatus: "hazir",
    izTime: null,
    setIzTime: (izTime) =>
      set((s) => ({ izTime, izStatus: s.izStatus === "hazir" ? "duraklatildi" : s.izStatus })),
    izSpeed: 1,
    setIzSpeed: (izSpeed) => set({ izSpeed }),
    play: () => set({ izStatus: "oynuyor" }),
    pause: () => set({ izStatus: "duraklatildi" }),
    resetIz: () => set({ izStatus: "hazir", izTime: null }),
    izHighlight: null,
    setIzHighlight: (izHighlight) => set({ izHighlight }),
    pendingContactKey: null,
    gotoTrackImage: (imageId, trackId) => {
      get().selectImage(imageId)
      get().openLeft("goruntu")
      // Vurgu kalkar; harita seçili kareye geçer.
      set({ izHighlight: null })
      // Kare zaten değerlendirilmişse araç hemen seçilir; değilse analiz bitince.
      const brief = get().evaluation?.status === "done" ? get().evaluation?.brief : null
      if (brief?.image_id === imageId) {
        if (brief.contacts.some((c) => c.track_id === trackId)) get().selectContact(trackId)
      } else set({ pendingContactKey: trackId })
    },
    clearMapSelection: () => set({ selectedContactKey: null, izHighlight: null }),
  }
})

/** Testler için: akışı ve zamanlayıcıyı durdurur. */
export function resetOperasyonStreams() {
  stopStream()
}
