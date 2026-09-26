"use client"

import { Moon, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useOperasyon } from "@/store/operasyon"

/** Açık / koyu tema anahtarı; üst çubuğun en sağında. Simge geçilecek temayı gösterir. */
export function TemaDugmesi() {
  const theme = useOperasyon((s) => s.theme)
  const setTheme = useOperasyon((s) => s.setTheme)
  const next = theme === "koyu" ? "acik" : "koyu"
  const label = next === "acik" ? "Açık temaya geç" : "Koyu temaya geç"

  return (
    <Button variant="outline" size="icon-sm" aria-label={label} title={label} onClick={() => setTheme(next)}>
      {next === "acik" ? <Sun /> : <Moon />}
    </Button>
  )
}
