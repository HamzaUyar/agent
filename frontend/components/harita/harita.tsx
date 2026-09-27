"use client"

import type { FeatureCollection } from "geojson"
import { useEffect, useRef, useState } from "react"

import type { Bounds } from "@/lib/geo"
import { useMapAdapterFactory } from "@/lib/harita/context"
import type {
  AreaLayer,
  Basemap,
  MapAdapter,
  MapMarker,
  MarkerGroup,
} from "@/lib/harita/types"
import type { Tema } from "@/lib/tema"

export type HaritaProps = {
  basemap: Basemap
  theme: Tema
  areas: Partial<Record<AreaLayer, FeatureCollection>>
  markers: Partial<Record<MarkerGroup, MapMarker[]>>
  /** Görünümün sığdırılacağı kutu; kutu değişince yeniden sığdırılır. */
  fitTo: Bounds | null
  /** Sağda haritanın üstünde duran kartın payı (px); sığdırılan kutu onun altında kalmaz. */
  fitInsetRight?: number
  onBasemapError: () => void
  onMarkerClick?: (group: MarkerGroup, id: string) => void
  onAreaClick?: (layer: AreaLayer, id: string | null) => void
  onMapClick?: () => void
  /**
   * Harita arayüzü hazır (ya da kaldırıldı: `null`). Her karede güncellenen katmanlar (İz analizi
   * oynatması) React'i yeniden çizdirmeden doğrudan bu arayüze yazar.
   */
  onReady?: (adapter: MapAdapter | null) => void
}

/**
 * Bildirimsel harita: prop'lar değiştikçe harita arayüzüne (`MapAdapter`) aktarılır.
 * Hangi sağlayıcının kullanılacağı `MapAdapterProvider`'dan gelir.
 */
export function Harita({
  basemap,
  theme,
  areas,
  markers,
  fitTo,
  fitInsetRight = 0,
  onBasemapError,
  onMarkerClick,
  onAreaClick,
  onMapClick,
  onReady,
}: HaritaProps) {
  const factory = useMapAdapterFactory()
  const containerRef = useRef<HTMLDivElement>(null)
  const [adapter, setAdapter] = useState<MapAdapter | null>(null)
  const handlers = useRef({ onBasemapError, onMarkerClick, onAreaClick, onMapClick, onReady })

  useEffect(() => {
    handlers.current = { onBasemapError, onMarkerClick, onAreaClick, onMapClick, onReady }
  })

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let created: MapAdapter | null = null
    let cancelled = false
    Promise.resolve(
      factory(container, {
        onBasemapError: () => handlers.current.onBasemapError(),
        onMarkerClick: (group, id) => handlers.current.onMarkerClick?.(group, id),
        onAreaClick: (layer, id) => handlers.current.onAreaClick?.(layer, id),
        onMapClick: () => handlers.current.onMapClick?.(),
      }),
    ).then((a) => {
      if (cancelled) a.destroy()
      else {
        setAdapter((created = a))
        handlers.current.onReady?.(a)
      }
    })
    return () => {
      cancelled = true
      handlers.current.onReady?.(null)
      created?.destroy()
      setAdapter(null)
    }
  }, [factory])

  useEffect(() => adapter?.setTheme(theme), [adapter, theme])
  useEffect(() => adapter?.setBasemap(basemap), [adapter, basemap])

  useEffect(() => {
    if (!adapter) return
    for (const [layer, data] of Object.entries(areas)) adapter.setArea(layer as AreaLayer, data)
  }, [adapter, areas])

  useEffect(() => {
    if (!adapter) return
    for (const [group, list] of Object.entries(markers)) adapter.setMarkers(group as MarkerGroup, list)
  }, [adapter, markers])

  useEffect(() => {
    if (adapter && fitTo) adapter.fitBounds(fitTo, 48, fitInsetRight)
  }, [adapter, fitTo, fitInsetRight])

  return <div ref={containerRef} className="absolute inset-0" data-testid="harita" />
}
