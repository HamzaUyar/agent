"use client"

import { Maximize2, Minimize2, X } from "lucide-react"
import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useOperasyon, type DrawerState, type Side } from "@/store/operasyon"

/** Çekmecenin en dar hâli; bundan darında içerik bozulur. */
export const DRAWER_MIN_PX = 280
/** Sürüklemeyle en fazla ekranın bu oranı. */
const DRAWER_MAX_RATIO = 0.5
/** Tam (geniş) görünüm. */
const DRAWER_FULL_RATIO = 0.55
/** Varsayılan genişlik (kullanıcı henüz ayarlamadıysa). */
const DRAWER_DEFAULT_RATIO = 0.3
/** Harita paneline her zaman kalan en az genişlik; iki ray ve boşluklar bunun dışında. */
const MAP_MIN_PX = 400
const CHROME_PX = 2 * 44 + 40
const KEY_STEP_PX = 16

const subscribe = (onChange: () => void) => {
  window.addEventListener("resize", onChange)
  return () => window.removeEventListener("resize", onChange)
}
const useViewportWidth = () =>
  useSyncExternalStore(
    subscribe,
    () => window.innerWidth,
    () => 1440,
  )

/** Ekran genişliğine göre sınırlar: harita en az MAP_MIN_PX kalır. */
export function drawerBounds(viewport: number) {
  const room = viewport - MAP_MIN_PX - CHROME_PX
  const max = Math.round(Math.max(DRAWER_MIN_PX, Math.min(viewport * DRAWER_MAX_RATIO, room)))
  return { min: DRAWER_MIN_PX, max, full: Math.max(DRAWER_MIN_PX, Math.min(viewport * DRAWER_FULL_RATIO, room)) }
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

type CekmeceProps = {
  side: Side
  title: string
  /** Açık panelin kimliği; değişince odak başlığa taşınır. */
  panelKey: string | null
  state: DrawerState
  children: ReactNode
}

/**
 * Kenar çekmecesi. Modal değil: sayfa düzeninin parçasıdır, harita paneli onun kadar daralır
 * ve etkileşimli kalır. Ray ikonundan ya da kısayolla açılır; genişliği tutamaçtan sürükleyerek
 * (ya da tutamaç odaktayken ok tuşlarıyla) ayarlanır, bırakıldığı yerde kalır ve saklanır.
 */
export function Cekmece({ side, title, panelKey, state, children }: CekmeceProps) {
  const setDrawerState = useOperasyon((s) => s.setDrawerState)
  const setDrawerWidth = useOperasyon((s) => s.setDrawerWidth)
  const storedWidth = useOperasyon((s) => s.drawerWidth[side])
  const close = useOperasyon((s) => s.close)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  const drag = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null)
  const [dragWidth, setDragWidth] = useState<number | null>(null)
  const viewport = useViewportWidth()
  const open = state !== "closed" && panelKey !== null

  // Açılınca odak çekmeceye taşınır, kapanınca açan öğeye döner.
  useEffect(() => {
    if (!open) return
    returnFocus.current = document.activeElement as HTMLElement | null
    headingRef.current?.focus()
    return () => {
      const target = returnFocus.current
      if (target?.isConnected) target.focus()
    }
    // Yalnızca panel açıldığında ya da değiştiğinde.
  }, [open, panelKey])

  const bounds = drawerBounds(viewport)
  const restingWidth = Math.round(
    state === "full" ? bounds.full : clamp(storedWidth ?? viewport * DRAWER_DEFAULT_RATIO, bounds.min, bounds.max),
  )
  const width = dragWidth ?? restingWidth
  // Sağ çekmece sola doğru, sol çekmece sağa doğru büyür.
  const direction = side === "right" ? -1 : 1

  function onHandleDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: width }
    setDragWidth(width)
    document.body.classList.add("cekmece-surukleniyor")
  }

  function onHandleMove(event: PointerEvent<HTMLDivElement>) {
    const d = drag.current
    if (!d || d.pointerId !== event.pointerId) return
    setDragWidth(clamp(d.startWidth + direction * (event.clientX - d.startX), bounds.min, bounds.max))
  }

  function onHandleUp(event: PointerEvent<HTMLDivElement>) {
    const d = drag.current
    if (!d || d.pointerId !== event.pointerId) return
    drag.current = null
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    document.body.classList.remove("cekmece-surukleniyor")
    // İptalde (pointercancel) koordinat güvenilmez: son izlenen genişlik geçerli.
    const final =
      event.type === "pointercancel"
        ? (dragWidth ?? d.startWidth)
        : clamp(d.startWidth + direction * (event.clientX - d.startX), bounds.min, bounds.max)
    setDragWidth(null)
    setDrawerWidth(side, final)
  }

  function onHandleKey(event: KeyboardEvent<HTMLDivElement>) {
    const grow = side === "right" ? "ArrowLeft" : "ArrowRight"
    const shrink = side === "right" ? "ArrowRight" : "ArrowLeft"
    let next: number | null = null
    if (event.key === grow) next = width + KEY_STEP_PX
    else if (event.key === shrink) next = width - KEY_STEP_PX
    else if (event.key === "Home") next = bounds.min
    else if (event.key === "End") next = bounds.max
    if (next === null) return
    event.preventDefault()
    event.stopPropagation()
    setDrawerWidth(side, clamp(next, bounds.min, bounds.max))
  }

  const expanded = state === "full"

  return (
    <section
      aria-label={title}
      hidden={!open}
      data-state={open ? state : "closed"}
      className={cn(
        "relative flex min-h-0 shrink-0 flex-col bg-[var(--cekmece-zemin)]",
        // Sürüklerken genişlik imleci gecikmeden izlesin: geçiş yalnızca sürükleme dışında.
        dragWidth === null && "transition-[width] duration-200 ease-out",
        side === "right" ? "border-l" : "border-r",
        "border-[var(--cekmece-cerceve)]",
      )}
      style={{ width: open ? `${width}px` : "0px" }}
    >
      {/* Tutamaç çekmecenin içinde durur (haritanın üstüne taşmaz); işaretçi ona yakalanır. */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={`${title} genişliği`}
        aria-valuemin={Math.round(bounds.min)}
        aria-valuemax={Math.round(bounds.max)}
        aria-valuenow={Math.round(width)}
        tabIndex={0}
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        onPointerCancel={onHandleUp}
        onKeyDown={onHandleKey}
        onDoubleClick={() => setDrawerState(side, expanded ? "half" : "full")}
        className={cn(
          "group absolute top-0 z-30 flex h-full w-2 cursor-col-resize touch-none items-center justify-center focus-visible:outline-offset-[-2px]",
          side === "right" ? "left-0" : "right-0",
        )}
      >
        <span
          className={cn(
            "h-10 w-1 rounded-full bg-cizgi-guclu/60 transition-colors group-hover:bg-cizgi-guclu",
            dragWidth !== null && "bg-secim group-hover:bg-secim",
          )}
        />
      </div>

      <header className="flex items-center gap-2 border-b border-cizgi bg-yuzey px-3 py-2">
        <h2 ref={headingRef} tabIndex={-1} className="flex-1 truncate text-sm font-bold text-metin outline-none">
          {title}
        </h2>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={expanded ? "Daralt" : "Genişlet"}
          title={expanded ? "Daralt" : "Genişlet"}
          onClick={() => setDrawerState(side, expanded ? "half" : "full")}
        >
          {expanded ? <Minimize2 /> : <Maximize2 />}
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Kapat (Esc)" title="Kapat (Esc)" onClick={() => close(side)}>
          <X />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">{children}</div>
    </section>
  )
}
