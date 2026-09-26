"use client"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import type { Brief, ContactKind } from "@/lib/api/types"
import { formatDistance } from "@/lib/format"
import { CERTAINTY, CONTACT_KIND, vehicleClass, vehicleTone } from "@/lib/labels"
import { bySeverity, keyedContacts, type KeyedContact } from "@/lib/temas"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

/** Takip durumu çizgiyle (harita noktası ve görüntü kutusuyla aynı): düz · kesikli · noktalı. */
const KIND_STYLE: Record<ContactKind, string> = {
  matched: "border-solid",
  unregistered: "border-dashed",
  missed: "border-dotted",
}

export function TurRozeti({ kind }: { kind: ContactKind }) {
  return (
    <span
      className={cn(
        "rounded border-[1.5px] border-cizgi-guclu px-1 py-px text-[11px] leading-4 whitespace-nowrap text-metin-ikincil",
        KIND_STYLE[kind],
      )}
    >
      {CONTACT_KIND[kind]}
    </span>
  )
}

/**
 * Temas listesi: seviyeye göre sıralı; düşük seviyeliler katlanır bir grupta
 * ("3 düşük seviyeli temas, en yakını 0,8 km").
 */
export function TemasListesi({ brief }: { brief: Brief }) {
  const sorted = keyedContacts(brief).sort(bySeverity)
  const main = sorted.filter((k) => k.contact.final_level !== "low")
  const low = sorted.filter((k) => k.contact.final_level === "low")
  const nearestLow = Math.min(...low.map((k) => k.contact.distance_to_base_m))

  return (
    <section aria-label="Temaslar" className="flex flex-col gap-1">
      <h3 className="text-xs font-bold tracking-wider text-metin-soluk uppercase">
        {brief.contacts.length} temas
      </h3>
      {brief.contacts.length === 0 && <p className="text-metin-soluk">Bu karede temas yok.</p>}
      <ul className="flex flex-col gap-1">
        {main.map((k) => (
          <TemasSatiri key={k.key} item={k} />
        ))}
      </ul>
      {low.length > 0 && (
        <details className="group rounded-md border border-cizgi bg-kart">
          <summary className="px-2 py-1.5 text-xs text-metin-ikincil select-none hover:text-metin">
            {low.length} düşük seviyeli temas, en yakını {formatDistance(nearestLow)}
          </summary>
          <ul className="flex flex-col gap-1 p-1">
            {low.map((k) => (
              <TemasSatiri key={k.key} item={k} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

/**
 * Temas satırı: nötr kart. Seviye soldaki ince şeritte ve rozette (kartı boyamaz); sınıf renk
 * karesinde; takip durumu tür rozetinin çizgisinde. Seçili satır mavi çerçeve + açık mavi zemin.
 */
function TemasSatiri({ item: { key, contact } }: { item: KeyedContact }) {
  const selected = useOperasyon((s) => s.selectedContactKey === key)
  const selectContact = useOperasyon((s) => s.selectContact)
  const label = contact.effective_label ?? contact.label
  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => selectContact(selected ? null : key)}
        className={cn(
          `seviye--${contact.final_level}`,
          "grid w-full grid-cols-[1fr_auto] items-center gap-x-2 gap-y-1 rounded-md border border-l-[3px] border-l-[color:var(--sv)] py-1.5 pr-2 pl-2 text-left text-xs transition-colors",
          selected
            ? "border-secim border-l-[color:var(--sv)] bg-secim-zemin ring-1 ring-secim"
            : "border-cizgi bg-kart hover:border-cizgi-guclu hover:border-l-[color:var(--sv)] hover:bg-kart-hover",
        )}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="font-mono text-[13px] font-bold text-metin">{contact.track_id ?? "track yok"}</span>
          <span aria-hidden className={cn("sinif-renk", `sinif--${vehicleTone(label)}`)} />
          <span className="truncate text-metin-ikincil">{vehicleClass(label)}</span>
        </span>
        <SeviyeRozeti level={contact.final_level} />
        <span className="flex items-center gap-1.5 text-metin-ikincil">
          <TurRozeti kind={contact.kind} />
          üsse {formatDistance(contact.distance_to_base_m)}
        </span>
        <span className="text-right text-metin-soluk">kesinlik: {CERTAINTY[contact.certainty]}</span>
      </button>
    </li>
  )
}
