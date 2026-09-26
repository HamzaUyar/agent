"use client"

import { useEffect } from "react"

import { useOperasyon } from "@/store/operasyon"

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.isContentEditable ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  )
}

/**
 * Çekmece kısayolları: R Risk & Temaslar · B Brief · G Görüntü · S Sohbet · Esc kapat.
 * Aynı kısayol açık çekmeceyi kapatır. Yazı alanındayken yalnızca Esc çalışır.
 */
export function useKisayollar() {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
      const s = useOperasyon.getState()

      if (event.key === "Escape") {
        const side = s.lastSide ?? (s.right.panel ? "right" : s.left.panel ? "left" : null)
        if (side) {
          s.close(side)
          event.preventDefault()
        }
        return
      }
      if (isTyping(event.target)) return

      switch (event.key.toLocaleLowerCase("tr-TR")) {
        case "r":
          if (s.right.panel && s.riskTab === "temaslar") s.close("right")
          else s.openRight("temaslar")
          break
        case "b":
          if (s.right.panel && s.riskTab === "brief") s.close("right")
          else s.openRight("brief")
          break
        case "g":
          if (s.left.panel === "goruntu") s.close("left")
          else s.openLeft("goruntu")
          break
        case "s":
          if (s.left.panel === "sohbet") s.close("left")
          else s.openLeft("sohbet")
          break
        default:
          return
      }
      event.preventDefault()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])
}
