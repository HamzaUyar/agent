"use client"

import { ArrowUpRight, Check, Pause, Play, RotateCcw, Route, X } from "lucide-react"
import { useMemo, useRef, type KeyboardEvent } from "react"

import { SeviyeRozeti, SeviyeSimgesi } from "@/components/operasyon/seviye-rozeti"
import { Button } from "@/components/ui/button"
import { RISK, vehicleClass } from "@/lib/labels"
import {
  DAKIKA_PER_SANIYE,
  gorunenler,
  IZ_HIZLARI,
  IZ_SEVIYELERI,
  saat,
  sayilar,
  yogunluk,
  type IzSeviyesi,
} from "@/lib/iz"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

import { useIzTracks } from "./iz-katmani"

const SEVIYE_ADI = (l: IzSeviyesi) => (l === "yok" ? "Değerlendirilmedi" : RISK[l].label)
const DENSITY_BINS = 48

/**
 * İz analizi kartı: haritanın sağ üstünde, haritayı daraltmayan küçük opak kart. Bilgi sırası
 * operatörün sorularına göre: hangi riskler (süzgeç) → kaç track (sayı) → saat kaç (büyük saat) →
 * nerede (zaman çizgisi) → oynuyor mu (oynatma satırı) → hangi track (vurgu).
 */
export function IzAnaliziKarti() {
  const izOpen = useOperasyon((s) => s.izOpen)
  const tracks = useOperasyon((s) => s.tracks)
  if (!izOpen) return null
  return (
    <section
      aria-label="İz analizi"
      className="absolute top-2 right-2 z-20 flex max-h-[min(60%,34rem)] w-80 max-w-[45%] min-w-72 flex-col overflow-hidden rounded-lg border border-cizgi bg-yuzey text-xs text-metin-ikincil shadow-golge-yuksek"
    >
      <Baslik />
      <div className="flex min-h-0 flex-col gap-3 overflow-y-auto p-3">
        {tracks.status === "loading" && <p className="text-metin-soluk">Track&apos;ler yükleniyor…</p>}
        {tracks.status === "error" && (
          <div role="alert" className="flex flex-wrap items-center gap-2">
            Track&apos;ler alınamadı. <span className="text-metin-soluk">{tracks.message}</span>
            <Button size="xs" variant="outline" onClick={() => void useOperasyon.getState().loadTracks()}>
              Tekrar dene
            </Button>
          </div>
        )}
        {tracks.status === "ready" && <Icerik />}
      </div>
    </section>
  )
}

function Baslik() {
  const toggleIz = useOperasyon((s) => s.toggleIz)
  return (
    <header className="flex items-center gap-2 border-b border-cizgi px-3 py-2">
      <Route aria-hidden strokeWidth={1.75} className="size-4 text-metin" />
      <h2 className="flex-1 text-sm font-bold text-metin">İz analizi</h2>
      <Button variant="ghost" size="icon-xs" aria-label="İz analizini kapat" title="Kapat" onClick={() => toggleIz(false)}>
        <X />
      </Button>
    </header>
  )
}

function Icerik() {
  const { all, filtered, range } = useIzTracks()
  const status = useOperasyon((s) => s.izStatus)
  const time = useOperasyon((s) => s.izTime)
  const counts = useMemo(() => sayilar(all), [all])
  const visible = time === null || status === "hazir" ? null : gorunenler(filtered, time).length

  return (
    <>
      <Suzgec counts={counts} />
      <p aria-live="polite" className="flex flex-wrap items-baseline gap-x-1.5 text-metin-ikincil">
        <span>
          <span className="font-mono text-base font-bold text-metin">{filtered.length}</span> / {all.length} track
        </span>
        {visible !== null && (
          <span>
            · şu an <span className="font-mono font-bold text-metin">{visible}</span> araç
          </span>
        )}
      </p>
      {range && <Zaman start={range.start} end={range.end} />}
      <Vurgu />
      <p className="border-t border-cizgi pt-2 text-[11px] leading-4 text-metin-soluk">
        Seviye ve sınıf: track&apos;in bittiği görüntünün son değerlendirmesi. Konum 5 dk&apos;lık kayıtlar
        arasında doğrusal ara değerdir; kaydı olmayan zamanda araç gösterilmez.
      </p>
    </>
  )
}

/** Çoklu seçim seviye süzgeci + "Hepsi"; seçili anahtar rozet dilinde, işaretli. */
function Suzgec({ counts }: { counts: Record<IzSeviyesi, number> }) {
  const levels = useOperasyon((s) => s.izLevels)
  const setLevels = useOperasyon((s) => s.setIzLevels)
  const shown = IZ_SEVIYELERI.filter((l) => l !== "yok" || counts.yok > 0)
  const all = shown.every((l) => levels.includes(l))
  const toggle = (l: IzSeviyesi) =>
    setLevels(levels.includes(l) ? levels.filter((x) => x !== l) : [...levels, l])

  return (
    <div role="group" aria-label="Risk seviyesi süzgeci" className="flex flex-wrap gap-1">
      <button
        type="button"
        aria-pressed={all}
        onClick={() => setLevels(all ? [] : [...IZ_SEVIYELERI])}
        className={cn(
          "inline-flex items-center gap-1 rounded border px-2 py-1 font-bold transition-colors",
          all
            ? "border-birincil bg-birincil text-birincil-uzeri"
            : "border-dashed border-cizgi-guclu text-metin-ikincil hover:bg-kart-hover hover:text-metin",
        )}
      >
        {all && <Check aria-hidden className="size-3" />}
        Hepsi
      </button>
      {shown.map((l) => {
        const on = levels.includes(l)
        const empty = counts[l] === 0
        return (
          <button
            key={l}
            type="button"
            aria-pressed={on}
            disabled={empty}
            onClick={() => toggle(l)}
            className={cn(
              `seviye--${l === "yok" ? "none" : l}`,
              "inline-flex items-center gap-1 rounded border px-1.5 py-1 font-bold transition-colors disabled:opacity-40 [--sv-bosluk:var(--sv-zemin)]",
              on
                ? "border-[color:var(--sv)] bg-[var(--sv-zemin)] text-[color:var(--sv)]"
                : "border-dashed border-cizgi-guclu bg-transparent text-metin-soluk [--sv-bosluk:var(--yuzey)] hover:bg-kart-hover",
            )}
          >
            {on ? <Check aria-hidden className="size-3" /> : <SeviyeSimgesi level={l === "yok" ? null : l} />}
            {SEVIYE_ADI(l)}
          </button>
        )
      })}
    </div>
  )
}

/** Büyük saat, yoğunluk göstergeli zaman çizgisi ve oynatma satırı. */
function Zaman({ start, end }: { start: number; end: number }) {
  const { filtered } = useIzTracks()
  const status = useOperasyon((s) => s.izStatus)
  const time = useOperasyon((s) => s.izTime)
  const speed = useOperasyon((s) => s.izSpeed)
  const { setIzTime, play, pause, resetIz, setIzSpeed } = useOperasyon.getState()
  const resumeAfterDrag = useRef(false)
  const density = useMemo(() => yogunluk(filtered, start, end, DENSITY_BINS), [filtered, start, end])
  const peak = Math.max(1, ...density)
  const value = time ?? start
  const playing = status === "oynuyor"
  const hours = Array.from({ length: Math.floor(end / 60) - Math.ceil(start / 60) + 1 }, (_, i) => (Math.ceil(start / 60) + i) * 60)
  const pct = (m: number) => `${((m - start) / (end - start)) * 100}%`
  const visibleAt = (m: number) => gorunenler(filtered, m).length

  const jump = (m: number) => setIzTime(Math.min(end, Math.max(start, m)))
  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    const steps: Record<string, number> = { ArrowRight: 5, ArrowUp: 5, ArrowLeft: -5, ArrowDown: -5, PageUp: 30, PageDown: -30 }
    if (event.key in steps) jump(value + steps[event.key])
    else if (event.key === "Home") jump(start)
    else if (event.key === "End") jump(end)
    else return
    event.preventDefault()
    event.stopPropagation()
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between">
        <span aria-hidden className="font-mono text-2xl leading-none font-bold text-metin">
          {status === "hazir" ? "Tüm gün" : saat(value)}
        </span>
        {/* Duyuru yalnızca durunca ya da atlayınca; oynarken her dakika duyurulmaz. */}
        <span role="status" aria-atomic="true" className="sr-only">
          {playing ? "" : status === "hazir" ? "Tüm gün, bütün yollar" : `${saat(value)} · ${visibleAt(value)} araç görünüyor`}
        </span>
        <span className="text-metin-soluk">
          {status === "hazir" ? "bütün yollar, hareketsiz" : playing ? "oynatılıyor" : "duraklatıldı"}
        </span>
      </div>

      <div className="relative h-9">
        {/* Yoğunluk: o dilimde kaydı olan track sayısı (silik). */}
        <div aria-hidden className="absolute inset-x-0 top-0 flex h-5 items-end gap-px">
          {density.map((d, i) => (
            <span key={i} className="flex-1 rounded-t-[1px] bg-cizgi-guclu/45" style={{ height: `${(d / peak) * 100}%` }} />
          ))}
        </div>
        <input
          type="range"
          aria-label="Simülasyon zamanı"
          aria-valuetext={status === "hazir" ? "Tüm gün" : saat(value)}
          min={start}
          max={end}
          step="any"
          value={value}
          onKeyDown={onKey}
          onPointerDown={(e) => {
            resumeAfterDrag.current = playing
            if (playing) pause()
            // Bırakma kaydırıcının dışında olsa da pointerup buraya gelsin.
            e.currentTarget.setPointerCapture?.(e.pointerId)
          }}
          onPointerUp={() => {
            if (resumeAfterDrag.current) play()
            resumeAfterDrag.current = false
          }}
          onPointerCancel={() => {
            if (resumeAfterDrag.current) play()
            resumeAfterDrag.current = false
          }}
          onChange={(e) => jump(Number(e.target.value))}
          className="iz-zaman absolute inset-x-0 top-3 w-full"
        />
        {/* Dar kartta etiketler binmesin: iki saatte bir. */}
        {hours.filter((h) => h % 120 === 0).map((h) => (
          <span
            key={h}
            aria-hidden
            className="absolute bottom-0 -translate-x-1/2 font-mono text-[10px] text-metin-soluk"
            style={{ left: pct(h) }}
          >
            {saat(h)}
          </span>
        ))}
      </div>

      <div className="flex items-center gap-1.5">
        <Button
          size="sm"
          aria-label={playing ? "Duraklat" : "Oynat"}
          onClick={() => (playing ? pause() : play())}
          className="min-w-24"
        >
          {playing ? <Pause /> : <Play />}
          {playing ? "Duraklat" : "Oynat"}
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Sıfırla: bütün yollar, hareketsiz"
          title="Sıfırla"
          disabled={status === "hazir"}
          onClick={resetIz}
        >
          <RotateCcw />
        </Button>
        <div
          role="group"
          aria-label="Oynatma hızı"
          title={`1× = gerçek zamanda saniyede ${DAKIKA_PER_SANIYE} dakika`}
          className="ml-auto flex rounded-md border border-cizgi bg-kart-vurgu p-0.5"
        >
          {IZ_HIZLARI.map((h) => (
            <button
              key={h}
              type="button"
              aria-pressed={speed === h}
              onClick={() => setIzSpeed(h)}
              className={cn(
                "rounded px-1.5 py-0.5 font-mono text-[11px] font-bold transition-colors",
                speed === h ? "bg-birincil text-birincil-uzeri" : "text-metin-ikincil hover:text-metin",
              )}
            >
              {String(h).replace(".", ",")}×
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/** Vurgulanan track: kimlik, sınıf, seviye, kayıt aralığı ve bittiği görüntüye geçiş. */
function Vurgu() {
  const highlight = useOperasyon((s) => s.izHighlight)
  const setHighlight = useOperasyon((s) => s.setIzHighlight)
  const { all } = useIzTracks()
  const track = all.find((t) => t.id === highlight)
  if (!track) return null
  const s = track.source

  const gotoImage = () => track.imageId && useOperasyon.getState().gotoTrackImage(track.imageId, track.id)

  return (
    <section aria-label="Vurgulanan track" className="flex flex-col gap-1.5 rounded-md border border-secim bg-secim-zemin p-2">
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-bold text-metin">{track.id}</span>
        <span className={`sinif-renk sinif--${track.tone}`} aria-hidden />
        <span>{vehicleClass(s.label)}</span>
        {s.level ? <SeviyeRozeti level={s.level} /> : <span className="text-metin-soluk">değerlendirilmedi</span>}
        <Button variant="ghost" size="icon-xs" className="ml-auto" aria-label="Vurguyu kaldır" onClick={() => setHighlight(null)}>
          <X />
        </Button>
      </div>
      <span className="font-mono text-metin-soluk">
        kayıt {s.start}–{s.end}
      </span>
      {track.imageId && (
        <Button variant="outline" size="xs" className="self-start" onClick={gotoImage}>
          <ArrowUpRight />
          Görüntüye git: {track.imageId}
        </Button>
      )}
    </section>
  )
}
