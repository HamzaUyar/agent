/**
 * İz analizi: günün bütün Track'lerinin seviyeye göre süzülmesi ve zaman içinde oynatılması.
 * Saf hesaplar; harita katmanını (GeoJSON) ve sayıları üretir, hiçbir şey çizmez.
 *
 * - Hazır hâli (zaman yok): süzgece uyan her track'in tam yolu, hareketsiz.
 * - t anı: yalnızca kaydı t'yi kapsayan (başlangıç ≤ t ≤ bitiş) track'ler; baş noktası t'deki konum,
 *   arkasında son `KUYRUK_DK` dakikalık kuyruk. Kaydın dışında (öncesi/sonrası) track yoktur;
 *   son konum ekranda kalmaz.
 * - İki kayıt arasındaki konum, iki gerçek kaydın arasında doğrusal ara değerdir (kayıtlar 5 dk arayla);
 *   tam kayıt saatinde kaydın kendisi. Duraklama veride zaten vardır (ardışık kayıtlar aynı yerde).
 */
import type { Feature, FeatureCollection } from "geojson"

import type { RiskLevel, TrackOverview } from "@/lib/api/types"
import { boundsOf, toLngLat, type Bounds, type LngLat } from "@/lib/geo"
import { RISK, vehicleClass, vehicleTone } from "@/lib/labels"

/** Süzgeç seviyesi: risk seviyesi ya da "yok" (bittiği görüntü değerlendirilmemiş). */
export type IzSeviyesi = RiskLevel | "yok"
export const IZ_SEVIYELERI: readonly IzSeviyesi[] = ["critical", "high", "medium", "low", "yok"]

export type IzHizi = 0.5 | 1 | 2 | 4
export const IZ_HIZLARI: readonly IzHizi[] = [0.5, 1, 2, 4]
/** 1× hızda gerçek zamanın bir saniyesi simülasyonda kaç dakika. */
export const DAKIKA_PER_SANIYE = 5
/** Oynatmada baş noktasının arkasındaki kuyruk. */
export const KUYRUK_DK = 15

export const dakika = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}
export const saat = (minutes: number) => {
  const m = Math.floor(minutes)
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
}

/** Hesaba hazır track: kayıt saatleri dakika, konumlar [lon, lat]. */
export type IzTrack = {
  id: string
  level: IzSeviyesi
  tone: string
  imageId: string | null
  start: number
  end: number
  times: number[]
  coords: LngLat[]
  source: TrackOverview
}

export function hazirla(tracks: TrackOverview[]): IzTrack[] {
  return tracks
    .map((t): IzTrack => {
      const points = t.points.filter((p) => p.time)
      return {
        id: t.track_id,
        level: (t.level ?? "yok") as IzSeviyesi,
        tone: t.kind === "missed" ? "diger" : vehicleTone(t.label),
        imageId: t.image_id ?? null,
        start: dakika(t.start),
        end: dakika(t.end),
        times: points.map((p) => dakika(p.time!)),
        coords: points.map((p) => toLngLat(p)),
        source: t,
      }
    })
    .filter((t) => t.times.length > 0)
}

export const suz = (tracks: IzTrack[], levels: readonly IzSeviyesi[]) =>
  tracks.filter((t) => levels.includes(t.level))

export function sayilar(tracks: IzTrack[]): Record<IzSeviyesi, number> {
  const counts = Object.fromEntries(IZ_SEVIYELERI.map((l) => [l, 0])) as Record<IzSeviyesi, number>
  for (const t of tracks) counts[t.level]++
  return counts
}

/** Kayıtların kapsadığı gün aralığı (dakika). */
export function aralik(tracks: IzTrack[]): { start: number; end: number } | null {
  if (tracks.length === 0) return null
  return {
    start: Math.min(...tracks.map((t) => t.start)),
    end: Math.max(...tracks.map((t) => t.end)),
  }
}

const aktif = (t: IzTrack, time: number) => time >= t.start && time <= t.end

/** t'deki konum; kaydın dışında `null`. */
export function konum(track: IzTrack, time: number): LngLat | null {
  if (!aktif(track, time)) return null
  const { times, coords } = track
  let i = 0
  while (i < times.length - 1 && times[i + 1] <= time) i++
  if (times[i] === time || i === times.length - 1) return coords[i]
  const f = (time - times[i]) / (times[i + 1] - times[i])
  const [a, b] = [coords[i], coords[i + 1]]
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]
}

/** `from`–`to` arasındaki yol: araya düşen kayıtlar ve iki uçta ara konum. */
export function yol(track: IzTrack, from: number, to: number): LngLat[] {
  const a = konum(track, Math.max(from, track.start))
  const b = konum(track, to)
  if (!a || !b) return []
  const inner = track.coords.filter((_, i) => track.times[i] > Math.max(from, track.start) && track.times[i] < to)
  return [a, ...inner, b]
}

export const gorunenler = (tracks: IzTrack[], time: number) => tracks.filter((t) => aktif(t, time))

/** Zaman çizgisindeki yoğunluk: `bins` dilimin her birinde kaydı olan track sayısı. */
export function yogunluk(tracks: IzTrack[], start: number, end: number, bins: number): number[] {
  const width = (end - start) / bins
  return Array.from({ length: bins }, (_, i) => {
    const mid = start + width * (i + 0.5)
    return tracks.filter((t) => aktif(t, mid)).length
  })
}

export type IzOzellik = {
  id: string
  /** yol: hazır hâlindeki tam yol · kuyruk: oynatmadaki son dakikalar · bas: t'deki konum. */
  kind: "yol" | "kuyruk" | "bas"
  tone: string
  level: IzSeviyesi
  highlighted: boolean
  dimmed: boolean
  description: string
}

const tanim = (t: IzTrack) =>
  `${t.id} · ${vehicleClass(t.source.label)} · ${t.level === "yok" ? "değerlendirilmedi" : RISK[t.level].label} · kayıt ${t.source.start}–${t.source.end}`

/**
 * Harita katmanı. `time` yoksa hazır hâli (tam yollar); varsa o anın baş noktaları ve kuyrukları.
 * Vurgulanan track'in yolu t'ye kadar tam çizilir, diğerleri soluklaşır.
 */
export function izKatmani(
  tracks: IzTrack[],
  time: number | null,
  highlight: string | null = null,
  kuyrukDk = KUYRUK_DK,
): FeatureCollection {
  const features: Feature[] = []
  const props = (t: IzTrack, kind: IzOzellik["kind"]): IzOzellik => ({
    id: t.id,
    kind,
    tone: t.tone,
    level: t.level,
    highlighted: t.id === highlight,
    dimmed: highlight !== null && t.id !== highlight,
    description: tanim(t),
  })
  for (const t of tracks) {
    if (time === null) {
      if (t.coords.length >= 2)
        features.push({ type: "Feature", properties: props(t, "yol"), geometry: { type: "LineString", coordinates: t.coords } })
      continue
    }
    const head = konum(t, time)
    if (!head) continue
    const tail = yol(t, t.id === highlight ? t.start : time - kuyrukDk, time)
    if (tail.length >= 2)
      features.push({ type: "Feature", properties: props(t, "kuyruk"), geometry: { type: "LineString", coordinates: tail } })
    features.push({ type: "Feature", properties: props(t, "bas"), geometry: { type: "Point", coordinates: head } })
  }
  return { type: "FeatureCollection", features }
}

/** Süzgece uyan bütün track'lerin kapsadığı kutu. */
export const izSinirlari = (tracks: IzTrack[]): Bounds | null =>
  tracks.length ? boundsOf(tracks.flatMap((t) => t.coords)) : null
