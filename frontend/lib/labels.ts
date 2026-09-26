/**
 * Arayüz metinleri; terimler kökteki CONTEXT.md ile aynı.
 * Seviye hiçbir yerde yalnızca renkle verilmez: her seviyenin şekli ve kelimesi var.
 */
import type {
  Certainty,
  ContactKind,
  Effect,
  RiskLevel,
  Trend,
  Verdict,
} from "@/lib/api/types"

export const RISK_LEVELS: readonly RiskLevel[] = ["low", "medium", "high", "critical"]

export const RISK: Record<RiskLevel, { label: string; shape: string; order: number }> = {
  low: { label: "Düşük", shape: "●", order: 0 },
  medium: { label: "Orta", shape: "■", order: 1 },
  high: { label: "Yüksek", shape: "▲", order: 2 },
  critical: { label: "Kritik", shape: "◆", order: 3 },
}

export const CONTACT_KIND: Record<ContactKind, string> = {
  matched: "Eşleşmiş temas",
  unregistered: "Kayıt dışı temas",
  missed: "Kaçırılmış temas",
}

/** Tespit sınıfı; backend'in `car/van/truck/bus` değerleri. */
export const VEHICLE_CLASS: Record<string, string> = {
  car: "otomobil",
  van: "minibüs",
  truck: "kamyon",
  bus: "otobüs",
}

export const vehicleClass = (label: string | null | undefined) =>
  label ? (VEHICLE_CLASS[label] ?? label) : "tip bilinmiyor"

export const CERTAINTY: Record<Certainty, string> = {
  certain: "kesin",
  likely: "olası",
  weak: "zayıf",
  unverified: "doğrulanamadı",
}

export const TREND: Record<Trend, string> = {
  approaching: "yaklaşıyor",
  receding: "uzaklaşıyor",
  stationary: "duruyor",
  passing: "geçiyor",
  unknown: "bilinmiyor",
}

export const VERDICT: Record<Verdict, string> = {
  consistent: "tutarlı",
  contradicts: "çelişkili",
  unverifiable: "doğrulanamaz",
  irrelevant: "ilgisiz",
}

export const EFFECT: Record<Effect, { label: string; symbol: string }> = {
  raises: { label: "yükseltir", symbol: "↑" },
  lowers: { label: "düşürür", symbol: "↓" },
  none: { label: "yok", symbol: "–" },
}

/** Rapor kaynağı; backend'in `official / third_party` değerleri. */
export const REPORT_SOURCE: Record<string, string> = {
  official: "resmi",
  third_party: "üçüncü taraf",
}

export const reportSource = (source: string) => REPORT_SOURCE[source] ?? source

/** Görsel doğrulamanın yük durumu. */
export const CARGO: Record<string, string> = { loaded: "yüklü", empty: "boş" }
