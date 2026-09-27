/**
 * Backend sözleşmesinin tipleri.
 *
 * JSON uçlarının tipleri `openapi.json`'dan üretilir (`npm run api:types`); burada yalnızca
 * kısa adlar verilir. SSE olay yükleri OpenAPI'de tanımlı değil; backend'deki
 * `app/agent/runner.py` ve `app/agent/chat.py` ile birebir aynı tutulur.
 */
import type { components } from "./schema"

type Schemas = components["schemas"]

export type ZonesResponse = Schemas["ZonesResponse"]
export type ImageSummary = Schemas["ImageSummary"]
export type ImageDetail = Schemas["ImageDetail"]
export type Brief = Schemas["Brief"]
export type ContactFinding = Schemas["ContactFinding"]
export type MotionFinding = Schemas["MotionFinding"]
export type RoutePoint = Schemas["RoutePoint"]
export type StopFinding = Schemas["StopFinding"]
export type ReportFinding = Schemas["ReportFinding"]
export type StepEvent = Schemas["StepEvent"]
export type TrackOverview = Schemas["TrackOverview"]
export type AttentionFinding = Schemas["AttentionFinding"]
export type RiskLevel = NonNullable<ImageSummary["last_risk_level"]>
export type ContactKind = ContactFinding["kind"]
export type Certainty = ContactFinding["certainty"]
export type Trend = MotionFinding["trend"]
export type Verdict = ReportFinding["verdict"]
export type Effect = ReportFinding["effect"]
export type AttentionReason = AttentionFinding["reason"]

/** `POST /evaluations` akışının olayları (`runner.py`). */
export type EvaluationEvent =
  | { event: "run"; data: { run_id: string; image_id: string; cached: boolean } }
  | { event: "step"; data: StepEvent }
  | { event: "brief"; data: Brief }
  | { event: "error"; data: { run_id: string; message: string } }

/** `POST /evaluations/{run_id}/chat` akışının olayları (`chat.py`). */
export type ChatEvent =
  | { event: "tool"; data: { name: string; arguments: Record<string, unknown>; result: unknown } }
  | { event: "answer"; data: { content: string; model: string | null } }
  | { event: "error"; data: { message: string } }
