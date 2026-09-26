/**
 * Temas yardımcıları: seçim anahtarı, sıralama, görünen ad ve görüntü üzerindeki konum.
 */
import type { Brief, ContactFinding, ImageDetail } from "@/lib/api/types"
import { haversineM, toLngLat } from "@/lib/geo"
import { CONTACT_KIND, RISK, vehicleClass } from "@/lib/labels"

/**
 * Tek seçim deposundaki Temas anahtarı: track'i olan Temas'ta `track_id`, kayıt dışı Temas'ta
 * Brief'teki sırası. Yalnızca o değerlendirme boyunca geçerlidir.
 */
export function contactKey(contact: ContactFinding, index: number): string {
  return contact.track_id ?? `kayit-disi-${index}`
}

export type KeyedContact = { key: string; index: number; contact: ContactFinding }

export function keyedContacts(brief: Brief): KeyedContact[] {
  return brief.contacts.map((contact, index) => ({ key: contactKey(contact, index), index, contact }))
}

/** Seviyeye göre (yüksekten düşüğe), eşitse Üs'e yakın olan önce. */
export function bySeverity(a: KeyedContact, b: KeyedContact): number {
  return (
    RISK[b.contact.final_level].order - RISK[a.contact.final_level].order ||
    a.contact.distance_to_base_m - b.contact.distance_to_base_m
  )
}

/** Kısa ad: "T0122" ya da "kayıt dışı otomobil". */
export function contactName(contact: ContactFinding): string {
  if (contact.track_id) return contact.track_id
  return `kayıt dışı ${vehicleClass(contact.effective_label ?? contact.label)}`
}

export function contactTitle(contact: ContactFinding): string {
  return `${contactName(contact)} · ${CONTACT_KIND[contact.kind].toLocaleLowerCase("tr-TR")}`
}

/**
 * Coğrafi konumu görüntü pikseline çevirir (backend'in doğrusal oranının tersi; kare kuzeye hizalı).
 * Kaçırılmış temasın kutusu yok; görüntüde konum işaretiyle gösterilir.
 */
export function toPixel(image: ImageDetail, lat: number, lon: number): { x: number; y: number } {
  const c = image.corner_coordinates
  const [tlLat, tlLon] = c.top_left
  const [, trLon] = c.top_right
  const [blLat] = c.bottom_left
  return {
    x: ((lon - tlLon) / (trLon - tlLon)) * image.width_px,
    y: ((tlLat - lat) / (tlLat - blLat)) * image.height_px,
  }
}

export type DistancePoint = { time: string | null; meters: number }

/**
 * Üs'e mesafenin çekim anına kadarki seyri: rota noktalarından istemcide (haversine) hesaplanır.
 * Görüntüleme içindir; seviye ve eğilim backend'den gelir.
 */
export function distanceSeries(
  route: { lat: number; lon: number; time?: string | null }[],
  base: { lat: number; lon: number },
  captureTime: string,
): DistancePoint[] {
  const b = toLngLat(base)
  return route
    .filter((p) => !p.time || p.time <= captureTime)
    .map((p) => ({ time: p.time ?? null, meters: haversineM(toLngLat(p), b) }))
}
