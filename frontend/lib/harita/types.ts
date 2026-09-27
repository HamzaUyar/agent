/**
 * Sağlayıcıdan bağımsız harita arayüzü. Sayfa haritaya yalnızca bu arayüzle konuşur;
 * MapLibre bir uygulamadır (maplibre-adapter.ts), testlerde yerine kayıt tutan sahte bir
 * uygulama geçer. Başka bir harita sağlayıcısına geçmek için yeni bir `MapAdapterFactory` yeterli.
 */
import type { FeatureCollection } from "geojson"

import type { Bounds, LngLat } from "@/lib/geo"
import type { Tema } from "@/lib/tema"

/** Zemin: uydu görüntüsü, sokak haritası ya da (internet yoksa) düz koyu zemin. */
export type Basemap = "uydu" | "sokak" | "duz"

/** GeoJSON alan/çizgi katmanları; çizim sırası bu listenin sırasıdır. */
export const AREA_LAYERS = ["bolge-alanlari", "ayak-izi", "us-halkalari", "izler", "rotalar"] as const
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
  /** Renk tonu (araç sınıfı: car/van/truck/bus/diger); `harita-isaret--sinif-<ton>` sınıfı olur. */
  tone?: string
  /** Varsa işaretin yanında bu yöne dönük ok (derece, kuzeyden saat yönünde). */
  headingDeg?: number
}

export type MapEvents = {
  /** Zemin yüklenemedi (ör. internet yok); harita düz zemine geçti. */
  onBasemapError: () => void
  onMarkerClick?: (group: MarkerGroup, id: string) => void
  /** Etkileşimli bir alan katmanındaki (şimdilik `izler`) özelliğe tıklandı; boşluğa tıklamada `null`. */
  onAreaClick?: (layer: AreaLayer, id: string | null) => void
  /** Haritada hiçbir işarete ya da etkileşimli katmana denk gelmeyen tıklama. */
  onMapClick?: () => void
}

export interface MapAdapter {
  setBasemap(basemap: Basemap): void
  /** Tema değişti: katman renkleri token'lardan yeniden okunur, sokak zemini temaya uyar. */
  setTheme(theme: Tema): void
  setArea(layer: AreaLayer, data: FeatureCollection): void
  setMarkers(group: MarkerGroup, markers: MapMarker[]): void
  /** `insetRight`: sağda haritanın üstünde duran bir kartın payı (px); dar haritada küçültülür. */
  fitBounds(bounds: Bounds, paddingPx: number, insetRight?: number): void
  destroy(): void
}

export type MapAdapterFactory = (
  container: HTMLElement,
  events: MapEvents,
) => MapAdapter | Promise<MapAdapter>
