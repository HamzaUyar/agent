"use client"

import { ImageOff } from "lucide-react"
import { useState } from "react"

import { imageFileUrl } from "@/lib/api/client"
import { cn } from "@/lib/utils"

/** Görüntü dosyası; yüklenemezse (ör. backend'de dosya yok) kırık simge yerine açıklama. */
export function Onizleme({
  imageId,
  alt,
  className,
  lazy = false,
}: {
  imageId: string
  alt: string
  className?: string
  lazy?: boolean
}) {
  const [failed, setFailed] = useState<string | null>(null)

  if (failed === imageId) {
    return (
      <span
        role={alt ? "img" : undefined}
        aria-label={alt ? `${alt} (önizleme yok)` : undefined}
        className={cn("flex flex-col items-center justify-center gap-1 text-xs text-metin-soluk", className)}
      >
        <ImageOff aria-hidden className="size-4" />
        önizleme yok
      </span>
    )
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- backend'den gelen dosya, tarayıcı önbelleğinde
    <img
      src={imageFileUrl(imageId)}
      alt={alt}
      loading={lazy ? "lazy" : undefined}
      onError={() => setFailed(imageId)}
      className={className}
    />
  )
}
