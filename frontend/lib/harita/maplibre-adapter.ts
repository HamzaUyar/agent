/**
 * Harita arayüzünün MapLibre GL uygulaması. Yalnızca tarayıcıda, dinamik olarak yüklenir.
 *
 * Zeminler anahtarsız: uydu Esri World Imagery (raster), sokak OpenFreeMap (vektör).
 * Kendi katmanlarımız `op-` önekiyle tutulur ve zemin değişince yeni stile taşınır.
 * Zemin yüklenemezse düz koyu zemine geçilir; katmanlar yerel GeoJSON'dan çizildiği için çalışmaya devam eder.
 */
import type { FeatureCollection } from "geojson"
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
  type LayerSpecification,
  type StyleSpecification,
} from "maplibre-gl"

import type { Bounds } from "@/lib/geo"

import {
  AREA_LAYERS,
  MARKER_GROUPS,
  type AreaLayer,
  type Basemap,
  type MapAdapter,
  type MapEvents,
  type MapMarker,
  type MarkerGroup,
} from "./types"

// Worker, Turbopack paketinin dışında sunulur (scripts/copy-maplibre-worker.mjs).
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs")

const PREFIX = "op-"
const DUZ_ZEMIN = "#141d31"

const ESRI_ATTRIBUTION =
  'Uydu: <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a>, Maxar, Earthstar Geographics'
const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty"

function rasterStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      zemin: {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        maxzoom: 19,
        attribution: ESRI_ATTRIBUTION,
      },
    },
    layers: [
      { id: "zemin-arka", type: "background", paint: { "background-color": DUZ_ZEMIN } },
      { id: "zemin", type: "raster", source: "zemin" },
    ],
  }
}

function plainStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [{ id: "zemin-arka", type: "background", paint: { "background-color": DUZ_ZEMIN } }],
  }
}

const css = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#94a3b8"

/**
 * Katman kimliği → MapLibre katmanları. Renkler tasarım token'larından okunur.
 * Çizgilerin altında koyu bir kılıf var: hem uydu görüntüsünde hem açık sokak haritasında seçilsinler.
 */
function overlayLayers(layer: AreaLayer): LayerSpecification[] {
  const source = PREFIX + layer
  const casing = (width: number): LayerSpecification => ({
    id: `${source}-kilif`,
    type: "line",
    source,
    paint: { "line-color": css("--zemin"), "line-opacity": 0.55, "line-width": width },
  })
  switch (layer) {
    case "bolge-alanlari":
      return [
        {
          id: `${source}-dolgu`,
          type: "fill",
          source,
          paint: { "fill-color": css("--metin"), "fill-opacity": 0.06 },
        },
        casing(3.5),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          paint: {
            "line-color": css("--metin"),
            "line-opacity": 0.9,
            "line-width": 1.5,
            "line-dasharray": [4, 3],
          },
        },
      ]
    case "ayak-izi":
      return [
        {
          id: `${source}-dolgu`,
          type: "fill",
          source,
          paint: { "fill-color": css("--secim"), "fill-opacity": 0.12 },
        },
        casing(4),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          paint: { "line-color": css("--secim"), "line-width": 2 },
        },
      ]
    case "rotalar":
      return [
        casing(5),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": [
              "match",
              ["get", "level"],
              "critical",
              css("--risk-kritik"),
              "high",
              css("--risk-yuksek"),
              "medium",
              css("--risk-orta"),
              css("--risk-dusuk"),
            ],
            "line-width": 2.5,
          },
        },
      ]
    case "us-halkalari":
      return [
        casing(4),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          paint: { "line-color": css("--metin"), "line-opacity": 0.95, "line-width": 1.75 },
        },
      ]
  }
}

function markerElement(group: MarkerGroup, marker: MapMarker, onClick?: () => void): HTMLElement {
  const el = document.createElement(onClick ? "button" : "div")
  el.className = [`harita-isaret`, `harita-isaret--${group}`, ...(marker.variant ?? []).map((v) => `harita-isaret--${v}`)].join(" ")
  el.setAttribute("aria-label", marker.description ?? marker.label)
  el.title = marker.description ?? marker.label
  if (onClick) {
    ;(el as HTMLButtonElement).type = "button"
    el.addEventListener("click", (e) => {
      e.stopPropagation()
      onClick()
    })
  }
  const icon = document.createElement("span")
  icon.className = "harita-isaret__simge"
  icon.setAttribute("aria-hidden", "true")
  const label = document.createElement("span")
  label.className = "harita-isaret__etiket"
  label.textContent = marker.label
  el.append(icon, label)
  if (marker.headingDeg !== undefined) {
    const arrow = document.createElement("span")
    arrow.className = "harita-isaret__yon"
    arrow.setAttribute("aria-hidden", "true")
    arrow.style.transform = `rotate(${marker.headingDeg}deg)`
    el.append(arrow)
  }
  return el
}

const DECLUTTERED: MarkerGroup[] = ["temaslar"]
const LABEL_GAP_PX = 3

/** Etiketleri verilen sırayla (önce en önemli) yerleştirir; çakışan etiket aşağı kaydırılır. */
function declutter(map: MapLibreMap, list: Marker[]) {
  type Box = { left: number; top: number; right: number; bottom: number }
  const placed: Box[] = []
  const overlaps = (a: Box) =>
    placed.some((b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)
  for (const marker of list) {
    const el = marker.getElement()
    const label = el.querySelector<HTMLElement>(".harita-isaret__etiket")
    if (!label) continue
    const { x, y } = map.project(marker.getLngLat())
    const width = label.offsetWidth || 80
    const height = label.offsetHeight || 18
    let shift = 0
    let box: Box = { left: x + 10, top: y - height / 2, right: x + 10 + width, bottom: y + height / 2 }
    for (let i = 0; i < 8 && overlaps(box); i++) {
      shift += height + LABEL_GAP_PX
      box = { ...box, top: box.top + height + LABEL_GAP_PX, bottom: box.bottom + height + LABEL_GAP_PX }
    }
    placed.push(box)
    el.style.setProperty("--etiket-kayma", `${shift}px`)
  }
}

export function createMapLibreAdapter(container: HTMLElement, events: MapEvents): MapAdapter {
  let basemap: Basemap = "uydu"
  const markers = new Map<MarkerGroup, Marker[]>()

  const map = new MapLibreMap({
    container,
    style: rasterStyle(),
    center: [32.853, 39.922],
    zoom: 12,
    attributionControl: { compact: false },
    dragRotate: false,
    pitchWithRotate: false,
  })
  map.touchZoomRotate.disableRotation()
  map.addControl(new NavigationControl({ showCompass: false }), "top-left")
  map.addControl(new ScaleControl({ unit: "metric" }), "bottom-right")

  /** Zemin kaynaklarından gelen hata (bizim `op-` kaynaklarımız değil) → düz zemin. */
  map.on("error", (event) => {
    const sourceId = (event as { sourceId?: string }).sourceId
    if (basemap === "duz" || (sourceId && sourceId.startsWith(PREFIX))) return
    basemap = "duz"
    applyStyle(plainStyle())
    events.onBasemapError()
  })

  function applyStyle(style: StyleSpecification | string) {
    map.setStyle(style, {
      transformStyle: (previous, next) => {
        if (!previous) return next
        const ours = Object.fromEntries(
          Object.entries(previous.sources).filter(([id]) => id.startsWith(PREFIX)),
        )
        return {
          ...next,
          sources: { ...next.sources, ...ours },
          layers: [...next.layers, ...previous.layers.filter((l) => l.id.startsWith(PREFIX))],
        }
      },
    })
  }

  // Temas'lar aynı karede birkaç metre arayla durur: nokta gerçek konumda kalır, etiketler
  // çakışıyorsa aşağı kaydırılır ve noktaya ince bir çizgiyle bağlanır.
  map.on("zoom", () => DECLUTTERED.forEach((g) => declutter(map, markers.get(g) ?? [])))

  function withStyle(fn: () => void) {
    if (map.isStyleLoaded()) fn()
    else map.once("idle", fn)
  }

  return {
    setBasemap(next) {
      if (next === basemap) return
      basemap = next
      applyStyle(next === "uydu" ? rasterStyle() : next === "sokak" ? OPENFREEMAP_STYLE : plainStyle())
    },

    setArea(layer, data: FeatureCollection) {
      withStyle(() => {
        const id = PREFIX + layer
        const existing = map.getSource(id) as GeoJSONSource | undefined
        if (existing) {
          existing.setData(data)
          return
        }
        map.addSource(id, { type: "geojson", data })
        // Alan katmanları sabit sırayla: listede kendinden sonra gelen ilk katmanın altına.
        const after = AREA_LAYERS.slice(AREA_LAYERS.indexOf(layer) + 1)
          .flatMap((l) => overlayLayers(l).map((s) => s.id))
          .find((layerId) => map.getLayer(layerId))
        for (const spec of overlayLayers(layer)) map.addLayer(spec, after)
      })
    },

    setMarkers(group, next) {
      for (const m of markers.get(group) ?? []) m.remove()
      const created = next.map((marker) => {
        const click = events.onMarkerClick ? () => events.onMarkerClick?.(group, marker.id) : undefined
        const el = markerElement(group, marker, click)
        el.style.zIndex = String(MARKER_GROUPS.indexOf(group) + 1)
        return new Marker({ element: el, anchor: "center" }).setLngLat(marker.lngLat).addTo(map)
      })
      markers.set(group, created)
      if (DECLUTTERED.includes(group)) declutter(map, created)
    },

    fitBounds(bounds: Bounds, paddingPx) {
      map.fitBounds(bounds, { padding: paddingPx, duration: 0 })
    },

    destroy() {
      map.remove()
    },
  }
}
