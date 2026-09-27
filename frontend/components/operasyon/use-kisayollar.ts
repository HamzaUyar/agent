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

/** Ok tuşlarını kendisi kullanan öğeler (sekmeler, seçim kutuları); orada ←/→ kare değiştirmez. */
function usesArrows(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    target.closest('[role="tablist"], select, [role="slider"], input[type="range"], [role="combobox"]') !== null
  )
}

/** Açık seçim listesi (Radix Select) bütün tuşları kendisi kullanır: harfle arama, oklar, Esc. */
function inListbox(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && target.closest('[role="listbox"]') !== null
}

/**
 * Kısayollar: R Risk & Araçlar · B Brief · G Görüntü · I İz analizi · Esc kapat · ←/→ önceki/sonraki kare.
 * Aynı kısayol açık çekmeceyi kapatır. Yazı alanındayken yalnızca Esc çalışır.
 */
export function useKisayollar() {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || inListbox(event.target)) return
      const s = useOperasyon.getState()

      if (event.key === "Escape") {
        // Önce İz analizindeki vurgu kalkar, sonra çekmeceler kapanır.
        if (s.izHighlight) {
          s.setIzHighlight(null)
          event.preventDefault()
          return
        }
        const side = s.lastSide ?? (s.right.panel ? "right" : s.left.panel ? "left" : null)
        if (side) {
          s.close(side)
          event.preventDefault()
        }
        return
      }
      if (isTyping(event.target)) return

      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        if (usesArrows(event.target)) return
        s.stepImage(event.key === "ArrowRight" ? 1 : -1)
        event.preventDefault()
        return
      }

      switch (event.key.toLocaleLowerCase("tr-TR")) {
        // Açık çekmecede aynı kısayol kapatır; öbür sekmedeyse o sekmeye geçer.
        case "r":
          if (s.right.panel && s.riskTab === "temaslar") s.close("right")
          else s.openRight("temaslar")
          break
        case "b":
          if (s.right.panel && s.riskTab === "brief") s.close("right")
          else s.openRight("brief")
          break
        case "i":
        case "ı":
          s.toggleIz()
          break
        case "g":
          if (s.left.panel === "goruntu") s.close("left")
          else s.openLeft("goruntu")
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
