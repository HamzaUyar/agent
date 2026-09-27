"use client"

import type { FeatureCollection } from "geojson"
import { useEffect, useMemo } from "react"

import type { MapAdapter } from "@/lib/harita/types"
import { aralik, DAKIKA_PER_SANIYE, hazirla, izKatmani, suz, type IzTrack } from "@/lib/iz"
import { useOperasyon } from "@/store/operasyon"

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] }

/** Depodaki track listesinden hazır track'ler ve süzülmüşleri; bileşenler arasında paylaşılır. */
export function useIzTracks() {
  const tracks = useOperasyon((s) => s.tracks)
  const levels = useOperasyon((s) => s.izLevels)
  const all = useMemo<IzTrack[]>(() => (tracks.status === "ready" ? hazirla(tracks.data) : []), [tracks])
  const filtered = useMemo(() => suz(all, levels), [all, levels])
  const range = useMemo(() => aralik(all), [all])
  return { all, filtered, range }
}

/**
 * İz analizi katmanını haritaya yazar; bir şey render etmez.
 * - Oynamıyorken: depo değiştikçe (süzgeç, zaman, vurgu) bir kez.
 * - Oynarken: `requestAnimationFrame` döngüsü zamanı kendi içinde ilerletir ve katmanı her karede
 *   doğrudan harita arayüzüne yazar. Depoya (ve React'e) yalnızca gösterilen dakika değişince yazılır;
 *   böylece bileşen ağacı her karede yeniden çizilmez. Kaydın sonunda durur.
 */
export function IzKatmani({ adapter }: { adapter: MapAdapter | null }) {
  const izOpen = useOperasyon((s) => s.izOpen)
  const status = useOperasyon((s) => s.izStatus)
  const time = useOperasyon((s) => s.izTime)
  const speed = useOperasyon((s) => s.izSpeed)
  const highlight = useOperasyon((s) => s.izHighlight)
  // Bir kare seçiliyken izler geri planda (soluk); ön planda o karenin araçları.
  const background = useOperasyon((s) => s.selectedImageId !== null)
  const { filtered, range } = useIzTracks()

  useEffect(() => {
    if (!adapter) return
    if (!izOpen) adapter.setArea("izler", EMPTY)
    else if (status !== "oynuyor")
      adapter.setArea("izler", izKatmani(filtered, status === "hazir" ? null : time, highlight, background))
  }, [adapter, izOpen, status, time, filtered, highlight, background])

  useEffect(() => {
    if (!adapter || !izOpen || status !== "oynuyor" || !range) return
    const initial = useOperasyon.getState().izTime
    let t = initial === null || initial >= range.end ? range.start : initial
    let written = t
    useOperasyon.setState({ izTime: t })
    let last = performance.now()
    let raf = 0

    const frame = (now: number) => {
      // Oynatma bu kare çalışmadan önce durdurulduysa (duraklat/sıfırla/kapat) hiçbir şey yazma.
      const current = useOperasyon.getState()
      if (!current.izOpen || current.izStatus !== "oynuyor") return
      // Zaman çizgisi kullanıcı tarafından değiştirildiyse oradan devam.
      const external = useOperasyon.getState().izTime
      if (external !== null && external !== written) t = external
      t = Math.min(range.end, t + ((now - last) / 1000) * DAKIKA_PER_SANIYE * speed)
      last = now
      adapter.setArea("izler", izKatmani(filtered, t, highlight, background))
      if (Math.floor(t) !== Math.floor(written) || t >= range.end) {
        written = t
        useOperasyon.setState({ izTime: t })
      }
      if (t >= range.end) {
        useOperasyon.setState({ izStatus: "duraklatildi" })
        return
      }
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      // Duraklatınca kesin zaman korunur (sıfırlama ya da kapatma zamanı zaten temizler).
      const s = useOperasyon.getState()
      if (s.izOpen && s.izStatus === "duraklatildi") useOperasyon.setState({ izTime: t })
    }
  }, [adapter, izOpen, status, speed, filtered, highlight, background, range])

  return null
}
