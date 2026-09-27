"use client"

import { Loader2, RotateCcw } from "lucide-react"
import Image from "next/image"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { orchestratorCalls } from "@/lib/orkestrator"
import { useOperasyon } from "@/store/operasyon"

import { SeviyeRozeti } from "./seviye-rozeti"
import { TemaDugmesi } from "./tema-dugmesi"

/** Üst durum çubuğu: logo, seçili kare · Bölge · çekim anı, canlı adımlar, seviye ve önerilen eylem, kaynak rozetleri. */
export function UstCubuk() {
  const images = useOperasyon((s) => s.images)
  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const evaluation = useOperasyon((s) => s.evaluation)
  const startEvaluation = useOperasyon((s) => s.startEvaluation)

  const summary =
    images.status === "ready" ? images.data.find((i) => i.image_id === selectedImageId) : undefined
  const brief = evaluation?.status === "done" ? evaluation.brief : null
  const calls = orchestratorCalls(evaluation?.steps ?? [])
  const lastCall = calls.at(-1)

  return (
    <header className="flex h-[var(--ust-cubuk-yukseklik)] items-center gap-4 border-b border-cizgi bg-[var(--ust-cubuk-zemin)] px-4 text-sm">
      {/* Logo temaya göre: açıkta lacivert, koyuda lacivert kısımları açık renkli sürüm. */}
      <span className="flex shrink-0 items-center">
        <Image src="/logo/bora-acik.png" alt="BORA" width={147} height={32} priority className="h-8 w-auto dark:hidden" />
        <Image src="/logo/bora-koyu.png" alt="BORA" width={147} height={32} priority className="hidden h-8 w-auto dark:block" />
      </span>
      <span aria-hidden className="h-5 w-px bg-cizgi" />

      {!selectedImageId ? (
        <p className="text-metin-soluk">Zaman akışından bir kare seçin</p>
      ) : (
        <p className="font-mono text-metin-ikincil" aria-label="Seçili kare">
          <span className="font-bold text-metin">{selectedImageId}</span>
          {summary && ` · ${summary.zone} · ${summary.capture_time}`}
        </p>
      )}

      {brief && (
        <div className="flex items-center gap-2" aria-label="Görüntü risk seviyesi">
          <SeviyeRozeti level={brief.risk_level} className="text-sm" />
          <span className="text-metin-ikincil">→ {brief.recommended_action}</span>
        </div>
      )}

      <div className="ml-auto flex items-center gap-2">
        {/* Canlı adımlar tek bir anlamlı durum mesajıyla duyurulur. */}
        <p role="status" aria-atomic="true" className="flex items-center gap-2 text-xs text-metin-ikincil">
          {evaluation?.status === "streaming" && (
            <>
              <Loader2 aria-hidden className="size-3.5 animate-spin" />
              {lastCall
                ? `Adım ${calls.length} · ${lastCall.kind === "agent" ? "agent " : ""}${lastCall.name}: ${lastCall.result}`
                : "Orkestratör başladı"}
            </>
          )}
          {evaluation?.status === "done" &&
            `${calls.length} çağrı tamamlandı · ${calls.filter((c) => c.kind === "agent").length} agent`}
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
        <TemaDugmesi />
      </div>
    </header>
  )
}
