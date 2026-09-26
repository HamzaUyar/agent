"use client"

import { useEffect } from "react"

import { GoruntuCekmecesi } from "@/components/goruntu/goruntu-cekmecesi"
import { HaritaPaneli } from "@/components/harita/harita-paneli"
import { RiskCekmecesi, RiskOzeti } from "@/components/risk/risk-cekmecesi"
import { ZamanAkisi } from "@/components/zaman-akisi/zaman-akisi"
import { useOperasyon } from "@/store/operasyon"

import { Cekmece } from "./cekmece"
import { SekmeRafi } from "./sekme-rafi"
import { UstCubuk } from "./ust-cubuk"
import { useKisayollar } from "./use-kisayollar"

const LEFT_TITLES = { goruntu: "Görüntü", sohbet: "Sohbet" } as const

/**
 * Tek operasyon ekranı (Konsept A): üst durum çubuğu, çerçeveli harita paneli, alt zaman akışı
 * ve kenar çekmeceleri. Çekmeceler açılınca harita paneli daralır ama kaybolmaz.
 */
export function OperasyonEkrani() {
  useKisayollar()
  const left = useOperasyon((s) => s.left)
  const right = useOperasyon((s) => s.right)

  useEffect(() => {
    const s = useOperasyon.getState()
    if (s.zones.status === "idle") void s.loadZones()
    if (s.images.status === "idle") void s.loadImages()
  }, [])

  return (
    <div className="grid h-dvh grid-rows-[auto_minmax(0,1fr)_auto]">
      <UstCubuk />

      <div className="flex min-h-0">
        <SekmeRafi side="left" />
        <Cekmece
          side="left"
          title={left.panel ? LEFT_TITLES[left.panel] : "Sol çekmece"}
          panelKey={left.panel}
          state={left.state}
        >
          {left.panel === "goruntu" && <GoruntuCekmecesi />}
          {left.panel === "sohbet" && (
            <p className="text-metin-soluk">Sohbet, tamamlanmış bir değerlendirmeden sonra açılır.</p>
          )}
        </Cekmece>

        <main className="flex min-w-0 flex-1 p-[var(--harita-paneli-bosluk)]">
          <HaritaPaneli />
        </main>

        <Cekmece
          side="right"
          title="Risk & Temaslar"
          panelKey={right.panel}
          state={right.state}
          peek={<RiskOzeti />}
        >
          <RiskCekmecesi />
        </Cekmece>
        <SekmeRafi side="right" />
      </div>

      <ZamanAkisi />
    </div>
  )
}
