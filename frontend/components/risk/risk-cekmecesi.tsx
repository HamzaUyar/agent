"use client"

import { CircleAlert, Loader2 } from "lucide-react"
import { useEffect, useRef } from "react"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Brief } from "@/lib/api/types"
import { keyedContacts } from "@/lib/temas"
import { useOperasyon, type Evaluation, type RiskTab } from "@/store/operasyon"

import { BriefPaneli } from "./brief-paneli"
import { TemasKarti } from "./temas-karti"
import { TemasListesi } from "./temas-listesi"

/** Sağ çekmece: Araçlar (değerlendirme adımları, araç listesi, seçili araç) ve Brief sekmeleri. */
export function RiskCekmecesi() {
  const riskTab = useOperasyon((s) => s.riskTab)
  const setRiskTab = useOperasyon((s) => s.setRiskTab)
  const evaluation = useOperasyon((s) => s.evaluation)

  return (
    <Tabs value={riskTab} onValueChange={(v) => setRiskTab(v as RiskTab)}>
      <TabsList className="w-full">
        <TabsTrigger value="temaslar">Araçlar</TabsTrigger>
        <TabsTrigger value="brief">Brief</TabsTrigger>
      </TabsList>
      <TabsContent value="temaslar" className="flex flex-col gap-3">
        {evaluation ? <DegerlendirmeDurumu evaluation={evaluation} /> : <BosDurum />}
      </TabsContent>
      <TabsContent value="brief">
        {evaluation?.brief ? (
          <BriefPaneli brief={evaluation.brief} />
        ) : (
          <p className="text-metin-soluk">Brief, değerlendirme tamamlanınca burada görünür.</p>
        )}
      </TabsContent>
    </Tabs>
  )
}

function BosDurum() {
  return (
    <p className="rounded-md border border-dashed border-cizgi-guclu p-3 text-center text-metin-soluk">
      Henüz değerlendirme yok. Bir kare seçip risk analizini başlatın.
    </p>
  )
}

function DegerlendirmeDurumu({ evaluation }: { evaluation: Evaluation }) {
  const startEvaluation = useOperasyon((s) => s.startEvaluation)
  const brief = evaluation.brief

  const steps = (
    <ol className="flex flex-col gap-1.5">
      {evaluation.steps.map((step) => (
        <li key={step.step_no} className="grid grid-cols-[1.5rem_1fr] gap-x-2 text-xs">
          <span className="font-mono text-metin-soluk">{step.step_no}</span>
          <span>
            <span className="font-mono font-bold">{step.name}</span>
            <span className="block text-metin-ikincil">{step.summary}</span>
          </span>
        </li>
      ))}
      {evaluation.status === "streaming" && (
        <li className="flex items-center gap-2 text-xs text-metin-soluk">
          <Loader2 aria-hidden className="size-3.5 animate-spin" />
          {evaluation.slow ? "Model yanıtı bekleniyor (en fazla 45 sn)" : "Sonraki adım bekleniyor…"}
        </li>
      )}
    </ol>
  )

  return (
    <>
      {brief && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-cizgi bg-kart p-2">
          <SeviyeRozeti level={brief.risk_level} className="text-sm" />
          <span className="text-metin">→ {brief.recommended_action}</span>
        </div>
      )}
      {evaluation.status === "error" && (
        <div role="alert" className="rounded-md border border-cizgi bg-kart p-3 shadow-golge">
          <p className="flex items-center gap-1.5 font-bold">
            <CircleAlert aria-hidden className="size-4 shrink-0 text-hata" />
            {evaluation.error ?? "Değerlendirme başarısız."}
          </p>
          <Button className="mt-2" size="sm" variant="outline" onClick={() => void startEvaluation(true)}>
            Tekrar dene
          </Button>
        </div>
      )}
      {brief && <SeciliTemas brief={brief} />}
      {brief && <TemasListesi brief={brief} />}
      {brief ? (
        // Brief geldikten sonra adımlar katlanır; gerekçe için açılabilir.
        <details aria-label="Değerlendirme adımları" className="rounded-md border border-cizgi bg-kart px-2 py-1.5">
          <summary className="text-xs font-bold tracking-wider text-metin-soluk uppercase select-none">
            Değerlendirme adımları ({evaluation.steps.length})
          </summary>
          <div className="mt-2">{steps}</div>
        </details>
      ) : (
        <section aria-label="Değerlendirme adımları">
          <h3 className="mb-1 text-xs font-bold tracking-wider text-metin-soluk uppercase">
            Değerlendirme adımları
          </h3>
          {steps}
        </section>
      )}
    </>
  )
}

/** Seçili Temas'ın detay kartı; seçilince görünür alana kaydırılır. */
function SeciliTemas({ brief }: { brief: Brief }) {
  const key = useOperasyon((s) => s.selectedContactKey)
  const ref = useRef<HTMLDivElement>(null)
  const selected = keyedContacts(brief).find((k) => k.key === key)

  useEffect(() => {
    if (key) ref.current?.scrollIntoView?.({ block: "nearest" })
  }, [key])

  if (!selected) return null
  return (
    <div ref={ref}>
      <TemasKarti brief={brief} contact={selected.contact} />
    </div>
  )
}
