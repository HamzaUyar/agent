"use client"

import { Loader2, RotateCcw } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useOperasyon } from "@/store/operasyon"

import { SeviyeRozeti } from "./seviye-rozeti"

/** Üst durum çubuğu: Üs, seçili kare · Bölge · çekim anı, canlı adımlar, seviye ve önerilen eylem, kaynak rozetleri. */
export function UstCubuk() {
  const zones = useOperasyon((s) => s.zones)
  const images = useOperasyon((s) => s.images)
  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const evaluation = useOperasyon((s) => s.evaluation)
  const startEvaluation = useOperasyon((s) => s.startEvaluation)

  const summary =
    images.status === "ready" ? images.data.find((i) => i.image_id === selectedImageId) : undefined
  const brief = evaluation?.status === "done" ? evaluation.brief : null
  const lastStep = evaluation?.steps.at(-1)

  return (
    <header className="flex h-[var(--ust-cubuk-yukseklik)] items-center gap-4 border-b border-cizgi bg-[var(--ust-cubuk-zemin)] px-4 text-sm">
      <span className="text-xs font-bold tracking-wider text-metin uppercase">
        {zones.status === "ready" ? zones.data.base.name : "Üs"}
      </span>

      {!selectedImageId ? (
        <p className="text-metin-soluk">Zaman akışından bir kare seçin</p>
      ) : (
        <p className="font-mono text-metin-ikincil" aria-label="Seçili kare">
          {selectedImageId}
          {summary && ` · ${summary.zone} · ${summary.capture_time}`}
        </p>
      )}

      {brief && (
        <div className="flex items-center gap-2" aria-label="Görüntü risk seviyesi">
          <SeviyeRozeti level={brief.risk_level} className="text-sm" />
          <span className="text-metin">→ {brief.recommended_action}</span>
        </div>
      )}

      <div className="ml-auto flex items-center gap-2">
        {/* Canlı adımlar tek bir anlamlı durum mesajıyla duyurulur. */}
        <p role="status" aria-atomic="true" className="flex items-center gap-2 text-xs text-metin-ikincil">
          {evaluation?.status === "streaming" && (
            <>
              <Loader2 aria-hidden className="size-3.5 animate-spin" />
              {lastStep ? `Adım ${lastStep.step_no} · ${lastStep.name}: ${lastStep.summary}` : "Değerlendirme başladı"}
            </>
          )}
          {evaluation?.status === "done" && `${evaluation.steps.length} adım tamamlandı`}
        </p>
        {evaluation?.status === "streaming" && evaluation.slow && (
          <span className="text-xs text-metin-soluk">Model yanıtı bekleniyor (en fazla 45 sn)</span>
        )}
        {brief && (
          <>
            {brief.is_fallback ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant="outline" className="border-otomatik-ozet text-otomatik-ozet" tabIndex={0}>
                    otomatik özet
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>{brief.fallback_reason ?? "LLM yanıt vermedi; kurallarla yazıldı"}</TooltipContent>
              </Tooltip>
            ) : (
              brief.model && (
                <Badge variant="outline" className="font-mono">
                  LLM: {brief.model}
                </Badge>
              )
            )}
            {evaluation?.cached && (
              <>
                <Badge variant="outline" className="border-veri-bayat text-veri-bayat">
                  önbellek
                </Badge>
                <Button size="xs" variant="outline" onClick={() => void startEvaluation(true)}>
                  <RotateCcw />
                  Yeniden değerlendir
                </Button>
              </>
            )}
          </>
        )}
      </div>
    </header>
  )
}
