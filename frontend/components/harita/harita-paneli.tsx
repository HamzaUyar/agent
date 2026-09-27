"use client"

import type { FeatureCollection } from "geojson"
import { useMemo, useState } from "react"

import { CircleAlert, TriangleAlert } from "lucide-react"

import { Button } from "@/components/ui/button"
import { toLngLat } from "@/lib/geo"
import { buildFootprint, buildScene } from "@/lib/harita/sahne"
import { buildContactLayers, contactBounds } from "@/lib/harita/temaslar"
import type { AreaLayer, Basemap, MapAdapter, MarkerGroup } from "@/lib/harita/types"
import { izSinirlari } from "@/lib/iz"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

import { Harita } from "./harita"
import { IzAnaliziKarti } from "./iz-analizi-karti"
import { IzKatmani, useIzTracks } from "./iz-katmani"
import { Lejant } from "./lejant"
import { RiskliIzUyarisi } from "./riskli-iz-uyarisi"

const BASEMAPS: { id: Exclude<Basemap, "duz">; label: string }[] = [
  { id: "uydu", label: "Uydu" },
  { id: "sokak", label: "Sokak" },
]

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] }

/** Çerçeveli harita paneli: zemin seçimi, lejant ve sahne katmanları (Üs, halkalar, Bölge'ler). */
export function HaritaPaneli() {
  const zones = useOperasyon((s) => s.zones)
  const loadZones = useOperasyon((s) => s.loadZones)
  const basemap = useOperasyon((s) => s.basemap)
  const basemapFailed = useOperasyon((s) => s.basemapFailed)
  const setBasemap = useOperasyon((s) => s.setBasemap)
  const basemapError = useOperasyon((s) => s.basemapError)

  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const imageDetail = useOperasyon((s) => s.imageDetail)

  const theme = useOperasyon((s) => s.theme)
  const selectedZone = imageDetail.status === "ready" ? imageDetail.data.zone : null
  // Seçili karenin köşeleri Bölge dilimlerinin içinde kalmalı (uzak kareler dilimin dışına taşmasın).
  const cover = useMemo(
    () => (imageDetail.status === "ready" ? Object.values(imageDetail.data.corner_coordinates).map(toLngLat) : []),
    [imageDetail],
  )
  const scene = useMemo(
    () => (zones.status === "ready" ? buildScene(zones.data, selectedZone, cover) : null),
    [zones, selectedZone, cover],
  )
  const footprint = useMemo(
    () => (imageDetail.status === "ready" ? buildFootprint(imageDetail.data) : null),
    [imageDetail],
  )
  const brief = useOperasyon((s) => (s.evaluation?.status === "done" ? s.evaluation.brief : null))
  const selectedContactKey = useOperasyon((s) => s.selectedContactKey)
  const selectContact = useOperasyon((s) => s.selectContact)
  const izOpen = useOperasyon((s) => s.izOpen)
  const { all: izTracks } = useIzTracks()
  // Panel açılınca harita günün bütün track'lerine sığar (süzgeç değişince yeniden sığmaz).
  const izBounds = useMemo(() => (izOpen ? izSinirlari(izTracks) : null), [izOpen, izTracks])
  const [adapter, setAdapter] = useState<MapAdapter | null>(null)
  // Seçili kare ön planda: rotaları ve araçları tam renkli, İz analizinin izleri soluk (IzKatmani).
  const contactLayers = useMemo(
    () => (brief ? buildContactLayers(brief, selectedContactKey) : null),
    [brief, selectedContactKey],
  )
  const selectedBounds = useMemo(
    () => (brief && selectedContactKey ? contactBounds(brief, selectedContactKey) : null),
    [brief, selectedContactKey],
  )
  // Seçili araca tekrar tıklamak seçimi kaldırır.
  const onMarkerClick = (group: MarkerGroup, id: string) => {
    if (group === "temaslar") selectContact(useOperasyon.getState().selectedContactKey === id ? null : id)
  }
  const onAreaClick = (layer: AreaLayer, id: string | null) => {
    if (layer !== "izler" || id === null) return
    const { izHighlight, setIzHighlight } = useOperasyon.getState()
    setIzHighlight(izHighlight === id ? null : id)
  }

  // Her katman her zaman verilir: değerlendirme temizlenince eski Temas'lar da silinsin.
  const areas = useMemo(
    () => ({
      ...scene?.areas,
      "ayak-izi": footprint?.area ?? EMPTY,
      rotalar: contactLayers?.routes ?? EMPTY,
    }),
    [scene, footprint, contactLayers],
  )
  const markers = useMemo(
    () => ({
      ...scene?.markers,
      temaslar: contactLayers?.contacts ?? [],
      duraklamalar: contactLayers?.stops ?? [],
      "rota-saatleri": contactLayers?.routeTimes ?? [],
    }),
    [scene, contactLayers],
  )

  return (
    <section
      aria-label="Harita paneli"
      className={cn(
        "relative flex-1 overflow-hidden rounded-lg border border-[var(--harita-paneli-cerceve)] bg-[var(--harita-paneli-zemin)]",
      )}
    >
      <Harita
        basemap={basemap}
        theme={theme}
        areas={areas}
        markers={markers}
        // Seçili veri önce: seçili araç varsa rotasına, seçili kare varsa kareye; yoksa İz analizi
        // açıksa bütün track'lere, değilse bütün sahneye.
        fitTo={
          selectedBounds ??
          (selectedImageId ? (footprint?.bounds ?? null) : (izBounds ?? scene?.bounds ?? null))
        }
        // İz analizi kartı sağ üstte haritanın üstünde (w-80 + kenar payı).
        fitInsetRight={izOpen ? 336 : 0}
        onBasemapError={basemapError}
        onMarkerClick={onMarkerClick}
        onAreaClick={onAreaClick}
        onMapClick={() => useOperasyon.getState().clearMapSelection()}
        onReady={setAdapter}
      />
      <IzKatmani adapter={adapter} />
      <IzAnaliziKarti />
      <RiskliIzUyarisi />

      {/* Zemin anahtarı sol üstte, yakınlaştırma düğmelerinin yanında; sağ üst İz analizi kartının. */}
      <div className="absolute top-2.5 left-12 z-10 flex flex-col items-start gap-2">
        <div
          role="group"
          aria-label="Harita zemini"
          className="flex gap-0.5 rounded-md border border-cizgi bg-yuzey p-0.5 shadow-golge"
        >
          {BASEMAPS.map((b) => (
            <button
              key={b.id}
              type="button"
              aria-pressed={basemap === b.id}
              onClick={() => setBasemap(b.id)}
              className={cn(
                "rounded px-3 py-1 text-xs font-bold transition-colors focus-visible:outline-offset-0",
                basemap === b.id
                  ? "bg-birincil text-birincil-uzeri"
                  : "text-metin-ikincil hover:bg-kart-hover hover:text-metin",
              )}
            >
              {b.label}
            </button>
          ))}
        </div>
        {basemapFailed && (
          <p
            role="status"
            className="flex max-w-60 gap-1.5 rounded-md border border-cizgi bg-yuzey px-2 py-1.5 text-xs text-metin-ikincil shadow-golge"
          >
            <TriangleAlert aria-hidden className="mt-px size-3.5 shrink-0 text-metin" />
            Harita zemini yüklenemedi; düz zemin gösteriliyor. Katmanlar çalışmaya devam ediyor.
          </p>
        )}
      </div>

      {zones.status === "ready" && <Lejant />}

      {zones.status === "error" && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div role="alert" className="max-w-sm rounded-lg border border-cizgi bg-yuzey p-4 text-center shadow-golge-yuksek">
            <CircleAlert aria-hidden className="mx-auto mb-1 size-5 text-hata" />
            <p className="font-bold">Üs ve bölge bilgisi alınamadı.</p>
            <p className="mt-1 text-xs text-metin-soluk">{zones.message}</p>
            <Button className="mt-3" size="sm" onClick={() => void loadZones()}>
              Tekrar dene
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}
