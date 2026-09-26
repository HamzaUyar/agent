"use client"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import type { Brief, ContactKind } from "@/lib/api/types"
import { formatDistance } from "@/lib/format"
import { CERTAINTY, CONTACT_KIND, vehicleClass } from "@/lib/labels"
import { bySeverity, keyedContacts, type KeyedContact } from "@/lib/temas"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

const KIND_STYLE: Record<ContactKind, string> = {
  matched: "border-metin-ikincil bg-metin-ikincil/15",
  unregistered: "border-metin-ikincil",
  missed: "border-dashed border-metin-ikincil",
}

export function TurRozeti({ kind }: { kind: ContactKind }) {
  return (
    <span className={cn("rounded border px-1 py-px text-[11px] whitespace-nowrap text-metin-ikincil", KIND_STYLE[kind])}>
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
        <details className="group rounded-md border border-cizgi">
          <summary className="cursor-pointer px-2 py-1.5 text-xs text-metin-ikincil select-none">
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

function TemasSatiri({ item: { key, contact } }: { item: KeyedContact }) {
  const selected = useOperasyon((s) => s.selectedContactKey === key)
  const selectContact = useOperasyon((s) => s.selectContact)
  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => selectContact(selected ? null : key)}
        className={cn(
          "grid w-full grid-cols-[1fr_auto] items-center gap-x-2 gap-y-1 rounded-md border px-2 py-1.5 text-left text-xs",
          selected ? "border-secim bg-secim-zemin" : "border-cizgi bg-kart hover:border-metin-soluk",
        )}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="font-mono font-bold">{contact.track_id ?? "track yok"}</span>
          <span className="truncate">{vehicleClass(contact.effective_label ?? contact.label)}</span>
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
