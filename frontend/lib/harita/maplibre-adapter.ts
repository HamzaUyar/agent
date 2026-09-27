/**
 * Harita arayüzünün MapLibre GL uygulaması. Yalnızca tarayıcıda, dinamik olarak yüklenir.
 *
 * Zeminler anahtarsız: uydu Esri World Imagery (raster), sokak OpenFreeMap (vektör "positron" stili).
 * Sokak stili iki temada da `--harita-*` token'larıyla yeniden boyanır (restyleBasemap): kara, su, yeşil
 * alan, yapı, yol sınıfları, sınır ve yazılar ayrışır ama hepsi bizim katmanlarımızdan soluk kalır.
 * CSS filtresiyle ters çevirme yok. Kendi katmanlarımız `op-` önekiyle tutulur ve zemin değişince
 * yeni stile taşınır; renkleri token'lardan okunur, tema ya da stil değişince yeniden boyanır.
 * Zemin yüklenemezse düz zemine geçilir; katmanlar yerel GeoJSON'dan çizildiği için çalışmaya devam eder.
 */
import type { FeatureCollection } from "geojson"
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
  type FilterSpecification,
  type LayerSpecification,
  type StyleSpecification,
} from "maplibre-gl"

import type { Bounds } from "@/lib/geo"
import { RISK } from "@/lib/labels"
import type { Tema } from "@/lib/tema"

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
const LEVEL_SHAPE = RISK.low.shape

const ESRI_ATTRIBUTION =
  'Uydu: <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a>, Maxar, Earthstar Geographics'
const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/positron"

const css = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#8e8c86"

/**
 * Sokak stilinin katmanlarını tema token'larıyla boyar (katman kimlikleri OpenFreeMap positron'dan).
 * Görsel sıra: yazı > ana yol > yol > yapı > su/yeşil > kara. Bilinmeyen katman olduğu gibi kalır.
 */
function basemapPaint(id: string, type: string): Record<string, unknown> | null {
  const has = (...parts: string[]) => parts.some((part) => id.includes(part))
  if (type === "background") return { "background-color": css("--harita-kara") }
  if (type === "fill") {
    if (has("water")) return { "fill-color": css("--harita-su") }
    if (has("park", "wood", "grass")) return { "fill-color": css("--harita-yesil") }
    if (has("residential")) return { "fill-color": css("--harita-yerlesim") }
    if (has("building"))
      return { "fill-color": css("--harita-yapi"), "fill-outline-color": css("--harita-yapi-kenar") }
    if (has("ice", "glacier", "pier", "aeroway")) return { "fill-color": css("--harita-kara") }
    return null
  }
  if (type === "line") {
    if (has("waterway")) return { "line-color": css("--harita-su") }
    if (has("boundary")) return { "line-color": css("--harita-sinir") }
    if (has("railway")) return { "line-color": has("dashline") ? css("--harita-kara") : css("--harita-demiryolu") }
    if (has("motorway")) return { "line-color": css(has("casing") ? "--harita-otoyol-kilif" : "--harita-otoyol") }
    if (has("major")) {
      if (has("casing")) return { "line-color": css("--harita-yol-ana-kilif") }
      return { "line-color": css(has("subtle") ? "--harita-yol" : "--harita-yol-ana") }
    }
    if (has("minor", "path", "pier", "taxiway", "runway"))
      return { "line-color": css(has("casing") ? "--harita-yol-kilif" : "--harita-yol") }
    return null
  }
  if (type === "symbol") {
    const halo = { "text-halo-color": css("--harita-yazi-hale"), "text-halo-width": 1.4 }
    if (has("water")) return { "text-color": css("--harita-su-yazi"), ...halo }
    if (has("highway", "road", "transportation")) return { "text-color": css("--harita-yazi-yol"), ...halo }
    // Büyük yerleşim adları (şehir, il) Üs ve Bölge adlarıyla yarışmasın.
    if (has("city", "state", "country")) return { "text-color": css("--harita-yazi"), "text-opacity": 0.7, ...halo }
    return { "text-color": css("--harita-yazi"), ...halo }
  }
  return null
}

function restyleBasemap(style: StyleSpecification): StyleSpecification {
  return {
    ...style,
    layers: style.layers.map((layer) => {
      if (layer.id.startsWith(PREFIX) || layer.type === "raster") return layer
      // Yol kalkanları (beyaz simgeler) ve tek yön okları bilgi taşımadan göz çeker.
      if (layer.id.includes("shield") || layer.id.includes("oneway"))
        return { ...layer, layout: { ...layer.layout, visibility: "none" } } as LayerSpecification
      const paint = basemapPaint(layer.id, layer.type)
      return paint ? ({ ...layer, paint: { ...layer.paint, ...paint } } as LayerSpecification) : layer
    }),
  }
}

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
      { id: "zemin-arka", type: "background", paint: { "background-color": css("--harita-duz-zemin") } },
      { id: "zemin", type: "raster", source: "zemin" },
    ],
  }
}

function plainStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [{ id: "zemin-arka", type: "background", paint: { "background-color": css("--harita-duz-zemin") } }],
  }
}

const ICON_PREFIX = "iz-seviye-"
const ICON_PX = 13

/**
 * Seviye baklavası (dolgu seviyeyle artar; `.seviye-simge` ile aynı merdiven): tema token'larından
 * tuvalde çizilir, tema değişince yeniden üretilir.
 */
function levelIcon(level: string): ImageData {
  const ratio = 2
  const size = (ICON_PX + 6) * ratio
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = size
  const ctx = canvas.getContext("2d")!
  const c = size / 2
  const r = (ICON_PX / 2) * ratio
  const diamond = (radius: number) => {
    ctx.beginPath()
    ctx.moveTo(c, c - radius)
    ctx.lineTo(c + radius, c)
    ctx.lineTo(c, c + radius)
    ctx.lineTo(c - radius, c)
    ctx.closePath()
  }
  const color = css(
    { critical: "--seviye-kritik-canli", high: "--seviye-yuksek-canli", medium: "--seviye-orta-canli", low: "--seviye-dusuk-canli" }[
      level
    ] ?? "--seviye-yok",
  )
  // Zeminden ayrışsın diye zemin renginde kılıf.
  diamond(r + 2 * ratio)
  ctx.fillStyle = css("--harita-kilif")
  ctx.fill()
  diamond(r)
  ctx.lineWidth = 1.5 * ratio
  ctx.strokeStyle = color
  if (level === "yok") ctx.setLineDash([2 * ratio, 1.5 * ratio])
  if (level === "high" || level === "critical") {
    ctx.fillStyle = color
    ctx.fill()
  } else if (level === "medium") {
    ctx.save()
    ctx.clip()
    ctx.fillStyle = color
    ctx.fillRect(0, c, size, size)
    ctx.restore()
  }
  ctx.stroke()
  if (level === "critical") {
    diamond(r + 3.5 * ratio)
    ctx.lineWidth = 1.25 * ratio
    ctx.stroke()
  }
  return ctx.getImageData(0, 0, size, size)
}

/** Rota rengi = araç sınıfı (seviye değil); sınıfı bilinmeyen (kaçırılmış) temas nötr. */
const vehicleColor = (property = "vehicle"): unknown => [
  "match",
  ["get", property],
  "car",
  css("--sinif-car"),
  "van",
  css("--sinif-van"),
  "truck",
  css("--sinif-truck"),
  "bus",
  css("--sinif-bus"),
  css("--sinif-diger"),
]

/**
 * Katman kimliği → MapLibre katmanları. Renkler tasarım token'larından okunur.
 * Her katmanın ayrı bir görsel rolü var:
 *   bölge alanı  nötr, kesikli sınır, çok düşük dolgu (yaklaşık; kesin sınır değil)
 *   ayak izi     seçim mavisi, düz ve kalın çerçeve (seçili görüntü)
 *   Üs halkaları ince, soluk düz çizgi (ölçek bilgisi)
 *   rotalar      sınıf renginde, kılıflı; seçili rota kalın, diğerleri seçim varken soluk
 * Çizgilerin altında zeminin tersi bir kılıf var: hem uydu görüntüsünde hem sokak haritasında seçilsinler.
 */
function overlayLayers(layer: AreaLayer): LayerSpecification[] {
  const source = PREFIX + layer
  const casing = (width: unknown, opacity: unknown = 0.7): LayerSpecification => ({
    id: `${source}-kilif`,
    type: "line",
    source,
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": css("--harita-kilif"), "line-opacity": opacity, "line-width": width } as never,
  })
  switch (layer) {
    // Pasta dilimleri: komşular sırayla çok hafif farklı dolgu; seçili karenin Bölge'si biraz daha koyu
    // dolgu ve kalın kesikli sınırla. Mavi değil: mavi yalnızca seçili görüntünün ayak izi.
    case "bolge-alanlari":
      return [
        {
          id: `${source}-dolgu`,
          type: "fill",
          source,
          paint: {
            "fill-color": css("--bolge-dolgu"),
            "fill-opacity": ["case", ["get", "selected"], 0.13, ["==", ["get", "parity"], 1], 0.06, 0.025],
          },
        },
        // İnce kılıf: kesikli sınır uydu görüntüsünde de seçilsin (seçili dilimde daha belirgin).
        casing(["case", ["get", "selected"], 4, 2.5], ["case", ["get", "selected"], 0.7, 0.35]),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          layout: { "line-join": "round" },
          paint: {
            "line-color": css("--bolge-cizgi"),
            "line-opacity": 0.55,
            "line-width": 1.1,
            "line-dasharray": [4, 3],
          },
        },
        {
          id: `${source}-secili`,
          type: "line",
          source,
          filter: ["==", ["get", "selected"], true],
          layout: { "line-join": "round" },
          paint: {
            "line-color": css("--bolge-secili"),
            "line-opacity": 0.9,
            "line-width": 2,
            "line-dasharray": [3, 2],
          },
        },
      ]
    case "ayak-izi":
      return [
        {
          id: `${source}-dolgu`,
          type: "fill",
          source,
          paint: { "fill-color": css("--secim"), "fill-opacity": 0.1 },
        },
        casing(6, 0.9),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          layout: { "line-join": "miter" },
          paint: { "line-color": css("--secim"), "line-width": 2.5 },
        },
      ]
    case "rotalar":
      return [
        casing(["case", ["get", "selected"], 8, 5], ["case", ["get", "dimmed"], 0.35, 0.85]),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": vehicleColor(),
            "line-width": ["case", ["get", "selected"], 4.5, 2.5],
            "line-opacity": ["case", ["get", "dimmed"], 0.3, 0.95],
          } as never,
        },
      ]
    // İz analizi: çizgi rengi sınıf; hazır hâlinde ince ve yarı saydam (yüzlerce çizgi haritayı
    // doldurmasın), oynatmada kuyruk daha belirgin; vurgulanan track kalın ve opak, diğerleri soluk.
    // Çizginin ucunda seviye baklavası (dolgu merdiveni); ayrı nokta yok, sınıf çizginin renginde.
    case "izler": {
      const line = ["!=", ["get", "kind"], "bas"] as FilterSpecification
      const width: unknown = [
        "case",
        ["get", "highlighted"],
        3.5,
        ["==", ["get", "kind"], "kuyruk"],
        2.5,
        1.25,
      ]
      const opacity: unknown = [
        "case",
        ["get", "highlighted"],
        1,
        ["get", "dimmed"],
        0.12,
        ["==", ["get", "kind"], "kuyruk"],
        0.8,
        0.4,
      ]
      return [
        {
          id: `${source}-kilif`,
          type: "line",
          source,
          filter: line,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": css("--harita-kilif"),
            "line-width": ["+", width, 2],
            "line-opacity": ["*", opacity, 0.6],
          },
        } as LayerSpecification,
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          filter: line,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": vehicleColor("tone"), "line-width": width, "line-opacity": opacity },
        } as LayerSpecification,
        {
          id: `${source}-seviye`,
          type: "symbol",
          source,
          filter: ["==", ["get", "kind"], "bas"],
          // Çizginin ucunda (aracın o anki konumunda) seviye baklavası; vurgulanan daha büyük.
          layout: {
            "icon-image": ["concat", ICON_PREFIX, ["get", "level"]],
            "icon-size": ["case", ["get", "highlighted"], 1.35, 1],
            "icon-allow-overlap": true,
            "icon-ignore-placement": true,
          },
          paint: { "icon-opacity": ["case", ["get", "dimmed"], 0.35, 1] },
        } as LayerSpecification,
      ]
    }
    case "us-halkalari":
      return [
        casing(3.5, 0.6),
        {
          id: `${source}-cizgi`,
          type: "line",
          source,
          paint: { "line-color": css("--metin-ikincil"), "line-opacity": 0.75, "line-width": 1.25 },
        },
      ]
  }
}

function markerElement(group: MarkerGroup, marker: MapMarker, onClick?: () => void): HTMLElement {
  const el = document.createElement(onClick ? "button" : "div")
  el.className = [
    `harita-isaret`,
    `harita-isaret--${group}`,
    ...(marker.variant ?? []).map((v) => `harita-isaret--${v}`),
    ...(marker.tone ? [`harita-isaret--sinif-${marker.tone}`] : []),
  ].join(" ")
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
  // Baştaki seviye baklavası metin değil, seviye simgesi olarak çizilir (dolgu seviyeyle artar).
  if (marker.label.startsWith(`${LEVEL_SHAPE} `)) {
    const level = document.createElement("span")
    level.className = "seviye-simge"
    level.setAttribute("aria-hidden", "true")
    level.textContent = LEVEL_SHAPE
    label.append(level, marker.label.slice(LEVEL_SHAPE.length + 1))
  } else {
    label.textContent = marker.label
  }
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
  // İlk zemin sayfadan gelir (setBasemap); o gelene kadar düz zemin, gereksiz karo indirilmesin.
  let basemap: Basemap | null = null
  let theme: Tema = "koyu"
  const markers = new Map<MarkerGroup, Marker[]>()
  const areas = new Map<AreaLayer, FeatureCollection>()

  const map = new MapLibreMap({
    container,
    style: plainStyle(),
    center: [32.853, 39.922],
    zoom: 12,
    attributionControl: { compact: false },
    dragRotate: false,
    pitchWithRotate: false,
  })
  map.touchZoomRotate.disableRotation()

  // Son sığdırma isteği: panel boyutu değişince (ilk yerleşim, çekmece açılıp kapanınca) yeniden
  // sığdırılır; kullanıcı haritayı kendisi kaydırdı ya da yakınlaştırdıysa onun görünümü korunur.
  let lastFit: { bounds: Bounds; padding: number; insetRight: number } | null = null
  /** Sağdaki kartın payı, kutuya en az haritanın yarısı kalacak kadar. */
  const paddingFor = (padding: number, insetRight: number) => {
    const room = map.getContainer().clientWidth
    const right = Math.max(padding, Math.min(insetRight, room / 2 - padding))
    return { top: padding, bottom: padding, left: padding, right }
  }
  map.on("movestart", (event) => {
    if ((event as { originalEvent?: Event }).originalEvent) lastFit = null
  })
  map.on("resize", () => {
    if (lastFit)
      map.fitBounds(lastFit.bounds, { padding: paddingFor(lastFit.padding, lastFit.insetRight), duration: 0 })
  })
  map.addControl(new NavigationControl({ showCompass: false }), "top-left")
  map.addControl(new ScaleControl({ unit: "metric" }), "bottom-right")

  /** Zemin kaynaklarından gelen hata (bizim `op-` kaynaklarımız değil) → düz zemin. */
  map.on("error", (event) => {
    const sourceId = (event as { sourceId?: string }).sourceId
    if (basemap === null || basemap === "duz" || (sourceId && sourceId.startsWith(PREFIX))) return
    basemap = "duz"
    applyStyle(plainStyle())
    events.onBasemapError()
  })

  function applyStyle(style: StyleSpecification | string) {
    map.setStyle(style, {
      transformStyle: (previous, incoming) => {
        const next = restyleBasemap(incoming)
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

  /** Kendi katmanlarımızın renklerini güncel token'lardan yeniden okur (tema ya da stil değişti). */
  function repaint() {
    for (const layer of AREA_LAYERS) {
      for (const spec of overlayLayers(layer)) {
        if (!map.getLayer(spec.id) || !("paint" in spec) || !spec.paint) continue
        for (const [prop, value] of Object.entries(spec.paint))
          map.setPaintProperty(spec.id, prop as Parameters<typeof map.setPaintProperty>[1], value)
      }
    }
    if (map.getLayer("zemin-arka")) map.setPaintProperty("zemin-arka", "background-color", css("--harita-duz-zemin"))
    for (const level of ["critical", "high", "medium", "low", "yok"]) {
      const id = ICON_PREFIX + level
      if (map.hasImage(id)) map.removeImage(id)
      map.addImage(id, levelIcon(level), { pixelRatio: 2 })
    }
  }

  // İz analizi: üzerine gelince ipucu (kimlik, sınıf, seviye, kayıt aralığı), tıklayınca vurgula.
  const IZ_ETKILESIM = [`${PREFIX}izler-cizgi`, `${PREFIX}izler-seviye`]
  const tip = new Popup({ closeButton: false, closeOnClick: false, className: "harita-ipucu", offset: 10 })
  map.on("mousemove", (event) => {
    const layers = IZ_ETKILESIM.filter((id) => map.getLayer(id))
    const hit = layers.length ? map.queryRenderedFeatures(event.point, { layers })[0] : undefined
    map.getCanvas().style.cursor = hit ? "pointer" : ""
    if (hit) tip.setLngLat(event.lngLat).setText(String(hit.properties.description ?? "")).addTo(map)
    else tip.remove()
  })
  // Fare haritadan çıkınca ipucu asılı kalmasın.
  map.on("mouseout", () => {
    map.getCanvas().style.cursor = ""
    tip.remove()
  })

  // DOM işaretlerinin tıklaması haritaya yayılmaz; buraya gelen tıklama ya bir ize ya boşluğa.
  map.on("click", (event) => {
    const layers = IZ_ETKILESIM.filter((id) => map.getLayer(id))
    const hit = layers.length ? map.queryRenderedFeatures(event.point, { layers })[0] : undefined
    if (hit) events.onAreaClick?.("izler", String(hit.properties.id))
    else events.onMapClick?.()
  })
  /** Alan katmanını sabit sırayla ekler: listede kendinden sonra gelen ilk katmanın altına. */
  function addArea(layer: AreaLayer, data: FeatureCollection) {
    map.addSource(PREFIX + layer, { type: "geojson", data })
    const after = AREA_LAYERS.slice(AREA_LAYERS.indexOf(layer) + 1)
      .flatMap((l) => overlayLayers(l).map((s) => s.id))
      .find((layerId) => map.getLayer(layerId))
    for (const spec of overlayLayers(layer)) map.addLayer(spec, after)
  }

  // Stil önceki stil yüklenmeden değişirse MapLibre onu sıfırdan kurar ve transformStyle'a önceki
  // stili vermez; o arada eklenen katmanlarımız düşer. Her stil yüklenişinde eksik olanlar yeniden eklenir.
  map.on("style.load", () => {
    for (const layer of AREA_LAYERS) {
      const data = areas.get(layer)
      if (data && !map.getSource(PREFIX + layer)) addArea(layer, data)
    }
    repaint()
  })

  const styleFor = (b: Basemap) => (b === "uydu" ? rasterStyle() : b === "sokak" ? OPENFREEMAP_STYLE : plainStyle())

  function withStyle(fn: () => void) {
    if (map.isStyleLoaded()) fn()
    else map.once("idle", fn)
  }

  return {
    setBasemap(next) {
      if (next === basemap) return
      basemap = next
      applyStyle(styleFor(next))
    },

    setTheme(next) {
      if (next === theme) return
      theme = next
      // Sokak zemini tema token'larıyla yeniden boyanır (stil yeniden yüklenir, katmanlarımız taşınır);
      // diğer zeminlerde yalnızca katmanlar boyanır.
      if (basemap === "sokak") applyStyle(styleFor("sokak"))
      else withStyle(repaint)
    },

    setArea(layer, data: FeatureCollection) {
      areas.set(layer, data)
      // Kaynak varsa hemen yaz: `setData` sonrası `isStyleLoaded()` kaynak işlenene kadar false döner;
      // o anda ertelemek, sonraki anlık bir yazmanın üstüne eski verinin binmesine yol açar.
      const existing = map.getSource(PREFIX + layer) as GeoJSONSource | undefined
      if (existing) {
        existing.setData(data)
        return
      }
      // İlk ekleme stil hazır olunca; o ana kadar gelen en son veriyle.
      withStyle(() => {
        const latest = areas.get(layer) ?? data
        const source = map.getSource(PREFIX + layer) as GeoJSONSource | undefined
        if (source) source.setData(latest)
        else addArea(layer, latest)
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

    fitBounds(bounds: Bounds, paddingPx, insetRight = 0) {
      lastFit = { bounds, padding: paddingPx, insetRight }
      map.fitBounds(bounds, { padding: paddingFor(paddingPx, insetRight), duration: 0 })
    },

    destroy() {
      map.remove()
    },
  }
}
