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

export type HaritaProps = {
  basemap: Basemap
  areas: Partial<Record<AreaLayer, FeatureCollection>>
  markers: Partial<Record<MarkerGroup, MapMarker[]>>
  /** Görünümün sığdırılacağı kutu; kutu değişince yeniden sığdırılır. */
  fitTo: Bounds | null
  onBasemapError: () => void
  onMarkerClick?: (group: MarkerGroup, id: string) => void
}

/**
 * Bildirimsel harita: prop'lar değiştikçe harita arayüzüne (`MapAdapter`) aktarılır.
 * Hangi sağlayıcının kullanılacağı `MapAdapterProvider`'dan gelir.
 */
export function Harita({ basemap, areas, markers, fitTo, onBasemapError, onMarkerClick }: HaritaProps) {
  const factory = useMapAdapterFactory()
  const containerRef = useRef<HTMLDivElement>(null)
  const [adapter, setAdapter] = useState<MapAdapter | null>(null)
  const handlers = useRef({ onBasemapError, onMarkerClick })

  useEffect(() => {
    handlers.current = { onBasemapError, onMarkerClick }
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
      }),
    ).then((a) => {
      if (cancelled) a.destroy()
      else setAdapter((created = a))
    })
    return () => {
      cancelled = true
      created?.destroy()
      setAdapter(null)
    }
  }, [factory])

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
    if (adapter && fitTo) adapter.fitBounds(fitTo, 48)
  }, [adapter, fitTo])

  return <div ref={containerRef} className="absolute inset-0" data-testid="harita" />
}
