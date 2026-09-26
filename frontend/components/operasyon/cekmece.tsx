"use client"

import { Maximize2, Minimize2, X } from "lucide-react"
import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useOperasyon, type DrawerState, type Side } from "@/store/operasyon"

const WIDTH: Record<DrawerState, string> = {
  closed: "0px",
  peek: "var(--cekmece-goz-atma)",
  half: "var(--cekmece-yarim)",
  full: "var(--cekmece-tam)",
}

/** Sürükleme bırakılınca en yakın hâle oturur; göz atmanın yarısından darsa kapanır. */
function snap(widthPx: number): DrawerState {
  const vw = window.innerWidth
  const stops: [DrawerState, number][] = [
    ["closed", 0],
    ["peek", 56],
    ["half", vw * 0.3],
    ["full", vw * 0.55],
  ]
  return stops.reduce((best, stop) =>
    Math.abs(stop[1] - widthPx) < Math.abs(best[1] - widthPx) ? stop : best,
  )[0]
}

type CekmeceProps = {
  side: Side
  title: string
  /** Açık panelin kimliği; değişince odak başlığa taşınır. */
  panelKey: string | null
  state: DrawerState
  /** Göz atma hâlindeki dar şeridin içeriği (özet sayılar). */
  peek?: ReactNode
  children: ReactNode
}

/**
 * Kenar çekmecesi. Modal değil: sayfa düzeninin parçasıdır, harita paneli onun kadar daralır
 * ve etkileşimli kalır. Sekmeye tıklayarak, tutamaçtan sürükleyerek ya da kısayolla açılır.
 */
export function Cekmece({ side, title, panelKey, state, peek, children }: CekmeceProps) {
  const setDrawerState = useOperasyon((s) => s.setDrawerState)
  const close = useOperasyon((s) => s.close)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  const [dragWidth, setDragWidth] = useState<number | null>(null)
  const open = state !== "closed" && panelKey !== null

  // Açılınca odak çekmeceye taşınır, kapanınca açan öğeye döner.
  useEffect(() => {
    if (!open) return
    returnFocus.current = document.activeElement as HTMLElement | null
    if (state !== "peek") headingRef.current?.focus()
    return () => {
      const target = returnFocus.current
      if (target?.isConnected) target.focus()
    }
    // Yalnızca panel açıldığında ya da değiştiğinde.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, panelKey])

  function onHandleDown(event: PointerEvent<HTMLDivElement>) {
    const panel = event.currentTarget.parentElement
    if (!panel) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const rect = panel.getBoundingClientRect()
    const edge = side === "right" ? rect.right : rect.left
    const widthAt = (x: number) => Math.max(0, side === "right" ? edge - x : x - edge)
    const handle = event.currentTarget

    function onMove(e: globalThis.PointerEvent) {
      setDragWidth(widthAt(e.clientX))
    }
    function onUp(e: globalThis.PointerEvent) {
      handle.removeEventListener("pointermove", onMove)
      handle.removeEventListener("pointerup", onUp)
      setDragWidth(null)
      const next = snap(widthAt(e.clientX))
      if (next === "closed") close(side)
      else setDrawerState(side, next)
    }
    handle.addEventListener("pointermove", onMove)
    handle.addEventListener("pointerup", onUp)
  }

  const width = dragWidth !== null ? `${dragWidth}px` : open ? WIDTH[state] : "0px"
  const expanded = state === "full"

  return (
    <section
      aria-label={title}
      hidden={!open}
      data-state={open ? state : "closed"}
      className={cn(
        "relative flex min-h-0 shrink-0 flex-col bg-[var(--cekmece-zemin)] transition-[width] duration-200 ease-out",
        side === "right" ? "border-l" : "border-r",
        "border-[var(--cekmece-cerceve)]",
      )}
      style={{ width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={`${title} genişliği`}
        onPointerDown={onHandleDown}
        className={cn(
          "absolute top-0 z-10 flex h-full w-3 cursor-col-resize touch-none items-center justify-center",
          side === "right" ? "-left-1.5" : "-right-1.5",
        )}
      >
        <span className="h-10 w-1 rounded-full bg-cizgi" />
      </div>

      {state === "peek" ? (
        <button
          type="button"
          onClick={() => setDrawerState(side, "half")}
          className="flex h-full w-full items-center justify-center text-xs text-metin-ikincil [writing-mode:vertical-rl]"
          aria-label={`${title} çekmecesini aç`}
        >
          {peek ?? title}
        </button>
      ) : (
        <>
          <header className="flex items-center gap-2 border-b border-cizgi px-3 py-2">
            <h2 ref={headingRef} tabIndex={-1} className="flex-1 text-sm font-bold outline-none">
              {title}
            </h2>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={expanded ? "Daralt" : "Genişlet"}
              onClick={() => setDrawerState(side, expanded ? "half" : "full")}
            >
              {expanded ? <Minimize2 /> : <Maximize2 />}
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label="Kapat (Esc)" onClick={() => close(side)}>
              <X />
            </Button>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">{children}</div>
        </>
      )}
    </section>
  )
}
