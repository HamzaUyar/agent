"use client"

import { Loader2 } from "lucide-react"

import { SeviyeRozeti, levelText } from "@/components/operasyon/seviye-rozeti"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Brief } from "@/lib/api/types"
import { useOperasyon, type Evaluation, type RiskTab } from "@/store/operasyon"

/** Göz atma hâlindeki dar şeridin özeti: "▲ Yüksek · 5 temas". */
export function RiskOzeti() {
  const evaluation = useOperasyon((s) => s.evaluation)
  const brief = evaluation?.brief
  if (!brief) return <>Risk &amp; Temaslar</>
  return (
    <>
      {levelText(brief.risk_level)} · {brief.contacts.length} temas
    </>
  )
}

/** Sağ çekmece: Temaslar (değerlendirme adımları; sonraki biletlerde temas listesi) ve Brief sekmeleri. */
export function RiskCekmecesi() {
  const riskTab = useOperasyon((s) => s.riskTab)
  const setRiskTab = useOperasyon((s) => s.setRiskTab)
  const evaluation = useOperasyon((s) => s.evaluation)

  return (
    <Tabs value={riskTab} onValueChange={(v) => setRiskTab(v as RiskTab)}>
      <TabsList>
        <TabsTrigger value="temaslar">Temaslar</TabsTrigger>
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
  return <p className="text-metin-soluk">Henüz değerlendirme yok. Bir kare seçip risk analizini başlatın.</p>
}

function DegerlendirmeDurumu({ evaluation }: { evaluation: Evaluation }) {
  const startEvaluation = useOperasyon((s) => s.startEvaluation)
  const brief = evaluation.brief

  return (
    <>
      {brief && (
        <div className="flex flex-wrap items-center gap-2">
          <SeviyeRozeti level={brief.risk_level} />
          <span>→ {brief.recommended_action}</span>
        </div>
      )}
      {evaluation.status === "error" && (
        <div role="alert" className="rounded-md border border-risk-kritik/50 p-3">
          <p className="font-bold">{evaluation.error ?? "Değerlendirme başarısız."}</p>
          <Button className="mt-2" size="sm" onClick={() => void startEvaluation(false)}>
            Tekrar dene
          </Button>
        </div>
      )}
      <section aria-label="Değerlendirme adımları">
        <h3 className="mb-1 text-xs font-bold tracking-wider text-metin-soluk uppercase">
          Değerlendirme adımları
        </h3>
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
      </section>
    </>
  )
}

function BriefPaneli({ brief }: { brief: Brief }) {
  return (
    <article aria-label="Brief" className="flex flex-col gap-3">
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono">
          {brief.image_id} · {brief.zone} · {brief.capture_time}
        </span>
        <SeviyeRozeti level={brief.risk_level} />
        {brief.is_fallback ? (
          <Badge variant="outline" className="border-otomatik-ozet text-otomatik-ozet">
            otomatik özet{brief.fallback_reason ? `: ${brief.fallback_reason}` : ""}
          </Badge>
        ) : (
          brief.model && <Badge variant="outline" className="font-mono">LLM: {brief.model}</Badge>
        )}
      </header>
      <p className="whitespace-pre-wrap leading-relaxed">{brief.text}</p>
      <p>
        <span className="font-bold">Önerilen eylem: </span>
        {brief.recommended_action}
      </p>
      <section aria-label="Kaynaklar">
        <h3 className="mb-1 text-xs font-bold tracking-wider text-metin-soluk uppercase">Kaynaklar</h3>
        <ul className="list-disc pl-5 text-xs text-metin-ikincil">
          {brief.sources.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </section>
    </article>
  )
}
