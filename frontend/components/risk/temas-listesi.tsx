"use client"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import type { Brief, Certainty, ContactKind } from "@/lib/api/types"
import { formatDistance } from "@/lib/format"
import { CERTAINTIES, CONTACT_KIND, certaintyLabel, vehicleClass, vehicleTone } from "@/lib/labels"
import { bySeverity, keyedContacts, secondaryDetections, type KeyedContact } from "@/lib/temas"
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
 * Sınıf karesi: dolgu = sınıf rengi, çerçeve çizgisi = takip durumu (düz / kesikli / noktalı).
 * Tipi bilinmeyen (kaçırılmış) araç nötr.
 */
function SinifKaresi({ kind, label }: { kind: ContactKind; label: string | null | undefined }) {
  const tone = kind === "missed" ? "diger" : vehicleTone(label)
  return (
    <span
      aria-hidden
      className={cn(
        "sinif-renk size-3! rounded-[3px] border-2 border-[color:var(--sinif)] bg-[color-mix(in_srgb,var(--sinif)_55%,transparent)]",
        `sinif--${tone}`,
        KIND_STYLE[kind],
      )}
    />
  )
}

/** "Kaç güvenilir sonuç var?": kesinlik dağılımı; her grup listeyi o gruba süzen bir anahtar. */
function KesinlikOzeti({ brief }: { brief: Brief }) {
  const filter = useOperasyon((s) => s.certaintyFilter)
  const setFilter = useOperasyon((s) => s.setCertaintyFilter)
  const counts = Object.fromEntries(CERTAINTIES.map((c) => [c, 0])) as Record<Certainty, number>
  for (const c of brief.contacts) counts[c.certainty]++
  const shown = CERTAINTIES.filter((c) => c !== "unverified" || counts.unverified > 0 || filter === c)

  return (
    <div role="group" aria-label="Tespit güvenilirliği" className="flex flex-col gap-1">
      <span className="text-[11px] font-bold tracking-wider text-metin-soluk uppercase">Tespit güvenilirliği</span>
      <div className="grid grid-cols-3 gap-1">
        {shown.map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={filter === c}
            // Etkin süzgeç, sonucu kalmasa da kapatılabilir olmalı.
            disabled={counts[c] === 0 && filter !== c}
            onClick={() => setFilter(filter === c ? null : c)}
            className={cn(
              "flex flex-col items-start rounded-md border px-2 py-1 text-left transition-colors disabled:opacity-45",
              filter === c
                ? "border-secim bg-secim-zemin ring-1 ring-secim"
                : "border-cizgi bg-kart hover:border-cizgi-guclu hover:bg-kart-hover",
            )}
          >
            <span className="font-mono text-base leading-5 font-bold text-metin">{counts[c]}</span>
            <span className="text-[11px] leading-4 text-metin-ikincil">{certaintyLabel(c)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/**
 * Araçlar listesi (alan dilinde Temas'lar): seviyeye göre sıralı; düşük seviyeliler katlanır bir
 * grupta. Üstte tespit güvenilirliği özeti ve süzgeci.
 */
export function TemasListesi({ brief }: { brief: Brief }) {
  const filter = useOperasyon((s) => s.certaintyFilter)
  const secondary = secondaryDetections(brief)
  const sorted = keyedContacts(brief)
    .filter((k) => filter === null || k.contact.certainty === filter)
    .sort(bySeverity)
  const main = sorted.filter((k) => k.contact.final_level !== "low")
  const low = sorted.filter((k) => k.contact.final_level === "low")
  const nearestLow = Math.min(...low.map((k) => k.contact.distance_to_base_m))
  const row = (k: KeyedContact) => (
    <TemasSatiri key={k.key} item={k} sameAs={secondary.has(k.key) ? secondary.get(k.key)! : null} />
  )

  return (
    <section aria-label="Araçlar" className="flex flex-col gap-2">
      {brief.contacts.length > 0 && <KesinlikOzeti brief={brief} />}
      <h3 className="text-xs font-bold tracking-wider text-metin-soluk uppercase">
        {filter ? `${sorted.length} / ${brief.contacts.length} araç` : `${brief.contacts.length} araç`}
      </h3>
      {brief.contacts.length === 0 && <p className="text-metin-soluk">Bu karede araç yok.</p>}
      <ul className="flex flex-col gap-1">{main.map(row)}</ul>
      {low.length > 0 && (
        <details className="group rounded-md border border-cizgi bg-kart">
          <summary className="px-2 py-1.5 text-xs text-metin-ikincil select-none hover:text-metin">
            {low.length} düşük seviyeli araç, en yakını {formatDistance(nearestLow)}
          </summary>
          <ul className="flex flex-col gap-1 p-1">{low.map(row)}</ul>
        </details>
      )}
    </section>
  )
}

/**
 * Araç satırı: nötr kart. Seviye soldaki ince şeritte ve rozette (kartı boyamaz); sınıf renk
 * karesinde, takip durumu karenin çizgisinde. Seçili satır mavi çerçeve + açık mavi zemin.
 * Aynı araca verilmiş ikinci (düşük güvenli) sınıf önerisi soluk ve açıklamalı.
 */
function TemasSatiri({ item: { key, contact }, sameAs }: { item: KeyedContact; sameAs: string | null }) {
  const selected = useOperasyon((s) => s.selectedContactKey === key)
  const selectContact = useOperasyon((s) => s.selectContact)
  const label = contact.effective_label ?? contact.label
  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        aria-label={`${contact.track_id ?? "track yok"} · ${vehicleClass(label)} · ${CONTACT_KIND[contact.kind]} · ${
          certaintyLabel(contact.certainty)
        }${sameAs ? " · aynı araç, düşük güvenli ikinci sınıf" : ""}`}
        onClick={() => selectContact(selected ? null : key)}
        className={cn(
          `seviye--${contact.final_level}`,
          "grid w-full grid-cols-[1fr_auto] items-center gap-x-2 gap-y-0.5 rounded-md border border-l-[3px] border-l-[color:var(--sv)] py-1.5 pr-2 pl-2 text-left text-xs transition-colors",
          selected
            ? "border-secim border-l-[color:var(--sv)] bg-secim-zemin ring-1 ring-secim"
            : "border-cizgi bg-kart hover:border-cizgi-guclu hover:border-l-[color:var(--sv)] hover:bg-kart-hover",
          sameAs && !selected && "opacity-60",
        )}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="font-mono text-[13px] font-bold text-metin">{contact.track_id ?? "track yok"}</span>
          <SinifKaresi kind={contact.kind} label={label} />
          <span className="truncate text-metin-ikincil">{vehicleClass(label)}</span>
        </span>
        <SeviyeRozeti level={contact.final_level} />
        <span className="col-span-2 text-metin-soluk">
          üsse {formatDistance(contact.distance_to_base_m)}
          {sameAs && " · aynı araç, düşük güvenli ikinci sınıf"}
        </span>
      </button>
    </li>
  )
}
