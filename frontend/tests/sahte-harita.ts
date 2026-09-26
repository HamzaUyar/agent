/**
 * Testler için sahte harita: MapLibre jsdom'da çalışmaz. Sayfanın haritaya ne çizdirdiğini
 * (katmanlar, işaretler, zemin, görünüm) kaydeder; zemin hatası ve işaret tıklaması tetiklenebilir.
 */
import type { FeatureCollection } from "geojson"

import type { Bounds } from "@/lib/geo"
import type {
  AreaLayer,
  Basemap,
  MapAdapter,
  MapAdapterFactory,
  MapEvents,
  MapMarker,
  MarkerGroup,
} from "@/lib/harita/types"
import type { Tema } from "@/lib/tema"

export class FakeMap implements MapAdapter {
  basemap: Basemap = "uydu"
  theme: Tema | null = null
  areas = new Map<AreaLayer, FeatureCollection>()
  markers = new Map<MarkerGroup, MapMarker[]>()
  fits: Bounds[] = []
  destroyed = false
  events: MapEvents | null = null

  readonly factory: MapAdapterFactory = (_container, events) => {
    this.events = events
    this.destroyed = false
    return this
  }

  setBasemap(basemap: Basemap) {
    this.basemap = basemap
  }
  setTheme(theme: Tema) {
    this.theme = theme
  }
  setArea(layer: AreaLayer, data: FeatureCollection) {
    this.areas.set(layer, data)
  }
  setMarkers(group: MarkerGroup, markers: MapMarker[]) {
    this.markers.set(group, markers)
  }
  fitBounds(bounds: Bounds) {
    this.fits.push(bounds)
  }
  destroy() {
    this.destroyed = true
  }

  /** Zemin yüklenemedi (ör. internet yok): gerçek uygulama gibi düz zemine geçer ve bildirir. */
  failBasemap() {
    this.basemap = "duz"
    this.events?.onBasemapError()
  }

  clickMarker(group: MarkerGroup, id: string) {
    this.events?.onMarkerClick?.(group, id)
  }

  markerLabels(group: MarkerGroup) {
    return (this.markers.get(group) ?? []).map((m) => m.label)
  }
}
