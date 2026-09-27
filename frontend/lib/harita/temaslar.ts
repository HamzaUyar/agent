/**
 * Brief'ten harita katmanları: Temas'lar (çekim anındaki konum), track'i olan Temas'ların rotası,
 * rota saatleri, duraklamaları ve son yönü. Çekim anından sonraki hiçbir şey çizilmez (ADR-0001).
 * Renk = araç sınıfı (nokta ve rota); seviye etiketteki baklava ve şeritte; takip durumu noktanın çizgisinde.
 */
import type { FeatureCollection } from "geojson"

import type { Brief, ContactFinding, RoutePoint } from "@/lib/api/types"
import { formatDegrees, formatDistance } from "@/lib/format"
import { boundsOf, circleRing, toLngLat, type Bounds } from "@/lib/geo"
import { certaintyLabel, CONTACT_KIND, RISK, TREND, vehicleClass, vehicleTone } from "@/lib/labels"
import { bySeverity, contactName, keyedContacts } from "@/lib/temas"

import type { MapMarker } from "./types"

/** Rota saati etiketleri her 30 dakikada bir (6 nokta × 5 dk) ve son noktada. */
const TIME_LABEL_EVERY = 6

/** Çekim anından sonraki rota noktaları çizilmez; saati olmayan (eski önbellek) noktalar kalır. */
function untilCapture(route: RoutePoint[], captureTime: string): RoutePoint[] {
  return route.filter((p) => !p.time || p.time <= captureTime)
}

function describe(contact: ContactFinding): string {
  const parts = [
    `${contactName(contact)} · ${CONTACT_KIND[contact.kind]}`,
    `sınıf ${vehicleClass(contact.effective_label ?? contact.label)}`,
    `seviye ${RISK[contact.final_level].label}`,
    certaintyLabel(contact.certainty).toLocaleLowerCase("tr-TR"),
    `üsse ${formatDistance(contact.distance_to_base_m)}`,
  ]
  const m = contact.motion
  if (m) {
    parts.push(TREND[m.trend])
    parts.push(m.heading_deg != null ? `yön ${formatDegrees(m.heading_deg)}` : "yön belirsiz")
  }
  return parts.join(" · ")
}

export type ContactLayers = {
  routes: FeatureCollection
  contacts: MapMarker[]
  stops: MapMarker[]
  routeTimes: MapMarker[]
}

export function buildContactLayers(brief: Brief, selectedKey: string | null = null): ContactLayers {
  const keyed = keyedContacts(brief)
  const routes: FeatureCollection = { type: "FeatureCollection", features: [] }
  const stops: MapMarker[] = []
  const routeTimes: MapMarker[] = []

  for (const { key, contact } of keyed) {
    const m = contact.motion
    if (!m) continue
    const route = untilCapture(m.route ?? [], brief.capture_time)
    if (route.length >= 2) {
      routes.features.push({
        type: "Feature",
        properties: {
          key,
          level: contact.final_level,
          vehicle: vehicleTone(contact.effective_label ?? contact.label),
          selected: key === selectedKey,
          dimmed: selectedKey !== null && key !== selectedKey,
        },
        geometry: { type: "LineString", coordinates: route.map(toLngLat) },
      })
    }
    // Metaveri (saat, duraklama) seçim varken yalnızca seçili Temas için: harita sade kalsın.
    if (selectedKey !== null && key !== selectedKey) continue
    route.forEach((p, i) => {
      if (!p.time || (i % TIME_LABEL_EVERY !== 0 && i !== route.length - 1)) return
      routeTimes.push({ id: `${key}-${i}`, lngLat: toLngLat(p), label: p.time, description: `${key} · ${p.time}` })
    })
    for (const stop of (m.stops ?? []).filter((s) => s.start <= brief.capture_time)) {
      stops.push({
        id: `${key}-${stop.start}`,
        lngLat: toLngLat(stop.location),
        label: `${stop.start} · ${stop.minutes} dk`,
        description: `${key} duraklama: ${stop.start}–${stop.end}, ${stop.minutes} dk, ${stop.zone}`,
      })
    }
  }

  // En önemli Temas önce: çakışan etiketlerde yerinde kalan o olur.
  const contacts: MapMarker[] = [...keyed].sort(bySeverity).map(({ key, contact }) => {
    const m = contact.motion
    const heading = m && m.heading_deg != null && m.trend !== "stationary" ? m.heading_deg : undefined
    return {
      id: key,
      lngLat: toLngLat(contact.location),
      label: `${RISK[contact.final_level].shape} ${contactName(contact)}${m ? ` · ${TREND[m.trend]}` : ""}`,
      description: describe(contact),
      variant: [contact.kind, contact.final_level, ...(key === selectedKey ? ["secili"] : [])],
      tone: vehicleTone(contact.effective_label ?? contact.label),
      headingDeg: heading,
    }
  })

  return { routes, contacts, stops, routeTimes }
}

/** Seçili Temas'a yaklaşırken görünür olacak kutu: konumu ve (varsa) çekim anına kadarki rotası. */
export function contactBounds(brief: Brief, key: string): Bounds | null {
  const found = keyedContacts(brief).find((k) => k.key === key)
  if (!found) return null
  const { contact } = found
  const points = [
    toLngLat(contact.location),
    ...untilCapture(contact.motion?.route ?? [], brief.capture_time).map(toLngLat),
  ]
  // Duran bir Temas için tek nokta: çevresinde ~300 m bırak.
  return boundsOf([...points, ...circleRing(toLngLat(contact.location), 300, 8)])
}
