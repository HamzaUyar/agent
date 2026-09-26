"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useOperasyon, type RiskTab } from "@/store/operasyon"

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
  const { left, right, riskTab, setRiskTab } = useOperasyon()

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
          {left.panel === "goruntu" && <p className="text-metin-soluk">Kare seçilmedi.</p>}
          {left.panel === "sohbet" && (
            <p className="text-metin-soluk">
              Sohbet, tamamlanmış bir değerlendirmeden sonra açılır.
            </p>
          )}
        </Cekmece>

        <main className="flex min-w-0 flex-1 p-[var(--harita-paneli-bosluk)]">
          <section
            aria-label="Harita paneli"
            className="relative flex-1 overflow-hidden rounded-lg border border-[var(--harita-paneli-cerceve)] bg-[var(--harita-paneli-zemin)]"
          />
        </main>

        <Cekmece side="right" title="Risk & Temaslar" panelKey={right.panel} state={right.state}>
          <Tabs value={riskTab} onValueChange={(v) => setRiskTab(v as RiskTab)}>
            <TabsList>
              <TabsTrigger value="temaslar">Temaslar</TabsTrigger>
              <TabsTrigger value="brief">Brief</TabsTrigger>
            </TabsList>
            <TabsContent value="temaslar" className="text-metin-soluk">
              Henüz değerlendirme yok. Bir kare seçip risk analizini başlatın.
            </TabsContent>
            <TabsContent value="brief" className="text-metin-soluk">
              Brief, değerlendirme tamamlanınca burada görünür.
            </TabsContent>
          </Tabs>
        </Cekmece>
        <SekmeRafi side="right" />
      </div>

      <section
        aria-label="Zaman akışı"
        className="h-[var(--zaman-akisi-yukseklik)] border-t border-cizgi bg-[var(--zaman-akisi-zemin)]"
      />
    </div>
  )
}
