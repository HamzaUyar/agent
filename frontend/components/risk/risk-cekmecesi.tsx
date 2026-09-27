"use client"

import { ArrowUpRight, CircleAlert, Loader2 } from "lucide-react"
import { useEffect, useRef } from "react"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Brief } from "@/lib/api/types"
import { vehicleClass, vehicleTone } from "@/lib/labels"
import { keyedContacts } from "@/lib/temas"
import { useOperasyon, type Evaluation, type RiskTab } from "@/store/operasyon"

import { BriefPaneli } from "./brief-paneli"
import { OrkestratorIzi, callCounts } from "./orkestrator-izi"
import { TemasKarti } from "./temas-karti"
import { TemasListesi } from "./temas-listesi"

/** Sağ çekmece: Araçlar (orkestratör izi, araç listesi, seçili araç) ve Brief sekmeleri. */
export function RiskCekmecesi() {
  const riskTab = useOperasyon((s) => s.riskTab)
  const setRiskTab = useOperasyon((s) => s.setRiskTab)
  const evaluation = useOperasyon((s) => s.evaluation)
  const trackCard = useOperasyon((s) => s.izHighlight !== null && s.izHighlight !== s.selectedContactKey)

  return (
    <Tabs value={riskTab} onValueChange={(v) => setRiskTab(v as RiskTab)}>
      <TabsList className="w-full">
        <TabsTrigger value="temaslar">Araçlar</TabsTrigger>
        <TabsTrigger value="brief">Brief</TabsTrigger>
      </TabsList>
      <TabsContent value="temaslar" className="flex flex-col gap-3">
        {trackCard && <SeciliTrack />}
        {evaluation ? <DegerlendirmeDurumu evaluation={evaluation} /> : !trackCard && <BosDurum />}
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

  const trace = <OrkestratorIzi evaluation={evaluation} />
  const { total, agents } = callCounts(evaluation)

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
        // Brief geldikten sonra iz katlanır; gerekçe için açılabilir.
        <details aria-label="Orkestratör izi" className="rounded-md border border-cizgi bg-kart px-2 py-1.5">
          <summary className="text-xs font-bold tracking-wider text-metin-soluk uppercase select-none">
            Orkestratör izi · {total} çağrı, {agents} agent
          </summary>
          <div className="mt-2">{trace}</div>
        </details>
      ) : (
        <section aria-label="Orkestratör izi">
          <h3 className="mb-1 text-xs font-bold tracking-wider text-metin-soluk uppercase">Orkestratör izi</h3>
          {trace}
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

/**
 * Haritada seçilen track (araç kartı henüz yoksa): kimlik, sınıf, seviye, kayıt aralığı ve durum.
 * Bittiği görüntünün kayıtlı değerlendirmesi yüklenirken bekleme, hiç yoksa görüntüye geçiş;
 * görüntüsüz track'te kısa değerlendirme.
 */
function SeciliTrack() {
  const trackId = useOperasyon((s) => s.izHighlight)
  const tracks = useOperasyon((s) => s.tracks)
  const loading = useOperasyon(
    (s) => s.evaluation?.status === "streaming" && s.pendingContactKey !== null && s.pendingContactKey === s.izHighlight,
  )
  const busy = useOperasyon((s) => s.evaluation?.status === "streaming")
  const track = tracks.status === "ready" ? tracks.data.find((t) => t.track_id === trackId) : undefined
  if (!track) return null

  const gotoImage = () => track.image_id && useOperasyon.getState().gotoTrackImage(track.image_id, track.track_id)
  const tone = track.kind === "missed" ? "diger" : vehicleTone(track.label)

  return (
    <section aria-label="Seçili track" className="flex flex-col gap-1.5 rounded-md border border-secim bg-secim-zemin p-2 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-bold text-metin">{track.track_id}</span>
        <span className={`sinif-renk sinif--${tone}`} aria-hidden />
        <span>{vehicleClass(track.label)}</span>
        {track.level ? (
          <SeviyeRozeti level={track.level} className="ml-auto" />
        ) : (
          <span className="ml-auto text-metin-soluk">değerlendirilmedi</span>
        )}
      </div>
      <span className="font-mono text-metin-soluk">
        kayıt {track.start}–{track.end}
        {track.unframed && " · görüntüsüz (kadraj dışında)"}
        {track.image_id && ` · bittiği görüntü ${track.image_id}`}
      </span>
      {track.unframed && track.assessment && <p className="text-metin">{track.assessment}</p>}
      {loading && (
        <span className="flex items-center gap-2 text-metin-soluk">
          <Loader2 aria-hidden className="size-3.5 animate-spin" />
          Kayıtlı değerlendirme yükleniyor…
        </span>
      )}
      {!loading && track.image_id && !track.kind && (
        <>
          <p className="text-metin-ikincil">Bittiği görüntü henüz değerlendirilmedi.</p>
          <Button variant="outline" size="xs" className="self-start" onClick={gotoImage}>
            <ArrowUpRight />
            Görüntüye git: {track.image_id}
          </Button>
        </>
      )}
      {!loading && busy && track.kind && (
        <p className="text-metin-ikincil">Başka bir analiz sürüyor; bitince track&apos;e tekrar tıklayın.</p>
      )}
    </section>
  )
}
