/**
 * Sağlayıcıdan bağımsız harita arayüzü. Sayfa haritaya yalnızca bu arayüzle konuşur;
 * MapLibre bir uygulamadır (maplibre-adapter.ts), testlerde yerine kayıt tutan sahte bir
 * uygulama geçer. Başka bir harita sağlayıcısına geçmek için yeni bir `MapAdapterFactory` yeterli.
 */
import type { FeatureCollection } from "geojson"

import type { Bounds, LngLat } from "@/lib/geo"

/** Zemin: uydu görüntüsü, sokak haritası ya da (internet yoksa) düz koyu zemin. */
export type Basemap = "uydu" | "sokak" | "duz"

/** GeoJSON alan/çizgi katmanları; çizim sırası bu listenin sırasıdır. */
export const AREA_LAYERS = ["bolge-alanlari", "ayak-izi", "us-halkalari", "rotalar"] as const
export type AreaLayer = (typeof AREA_LAYERS)[number]

/** Etiketli nokta işaretleri (erişilebilir düğmeler); gruplar üst üste bu sırayla çizilir. */
export const MARKER_GROUPS = [
  "halka-etiketleri",
  "bolgeler",
  "rota-saatleri",
  "duraklamalar",
  "us",
  "temaslar",
] as const
export type MarkerGroup = (typeof MARKER_GROUPS)[number]

export type MapMarker = {
  id: string
  lngLat: LngLat
  /** Görünür etiket. */
  label: string
  /** Erişilebilir ad ve tooltip; yoksa etiket. */
  description?: string
  /** Görünüm değişkenleri (ör. Temas türü ve seviyesi); `harita-isaret--<değişken>` sınıfı olur. */
  variant?: string[]
  /** Varsa işaretin yanında bu yöne dönük ok (derece, kuzeyden saat yönünde). */
  headingDeg?: number
}

export type MapEvents = {
  /** Zemin yüklenemedi (ör. internet yok); harita düz zemine geçti. */
  onBasemapError: () => void
  onMarkerClick?: (group: MarkerGroup, id: string) => void
}

export interface MapAdapter {
  setBasemap(basemap: Basemap): void
  setArea(layer: AreaLayer, data: FeatureCollection): void
  setMarkers(group: MarkerGroup, markers: MapMarker[]): void
  fitBounds(bounds: Bounds, paddingPx: number): void
  destroy(): void
}

export type MapAdapterFactory = (
  container: HTMLElement,
  events: MapEvents,
) => MapAdapter | Promise<MapAdapter>
