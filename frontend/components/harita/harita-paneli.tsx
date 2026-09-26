"use client"

import type { FeatureCollection } from "geojson"
import { useMemo } from "react"

import { Button } from "@/components/ui/button"
import { buildFootprint, buildScene } from "@/lib/harita/sahne"
import { buildContactLayers } from "@/lib/harita/temaslar"
import type { Basemap } from "@/lib/harita/types"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

import { Harita } from "./harita"
import { Lejant } from "./lejant"

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

  const scene = useMemo(() => (zones.status === "ready" ? buildScene(zones.data) : null), [zones])
  const footprint = useMemo(
    () => (imageDetail.status === "ready" ? buildFootprint(imageDetail.data) : null),
    [imageDetail],
  )
  const brief = useOperasyon((s) => (s.evaluation?.status === "done" ? s.evaluation.brief : null))
  const contactLayers = useMemo(() => (brief ? buildContactLayers(brief) : null), [brief])

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
      className="relative flex-1 overflow-hidden rounded-lg border border-[var(--harita-paneli-cerceve)] bg-[var(--harita-paneli-zemin)]"
    >
      <Harita
        basemap={basemap}
        areas={areas}
        markers={markers}
        // Kare seçiliyken ayak izine yaklaşır; ayrıntısı yüklenirken görünüm yerinde kalır.
        fitTo={selectedImageId ? (footprint?.bounds ?? null) : (scene?.bounds ?? null)}
        onBasemapError={basemapError}
      />

      <div className="absolute top-3 right-3 z-10 flex flex-col items-end gap-2">
        <div role="group" aria-label="Harita zemini" className="flex rounded-md border border-cizgi bg-yuzey/90 p-0.5">
          {BASEMAPS.map((b) => (
            <button
              key={b.id}
              type="button"
              aria-pressed={basemap === b.id}
              onClick={() => setBasemap(b.id)}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-bold",
                basemap === b.id ? "bg-secim-zemin text-metin" : "text-metin-ikincil hover:text-metin",
              )}
            >
              {b.label}
            </button>
          ))}
        </div>
        {basemapFailed && (
          <p role="status" className="max-w-56 rounded-md border border-cizgi bg-yuzey/90 px-2 py-1 text-xs text-metin-ikincil">
            Harita zemini yüklenemedi; düz zemin gösteriliyor. Katmanlar çalışmaya devam ediyor.
          </p>
        )}
      </div>

      {zones.status === "ready" && <Lejant withContacts={brief !== null} />}

      {zones.status === "error" && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div role="alert" className="max-w-sm rounded-lg border border-cizgi bg-yuzey p-4 text-center">
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
