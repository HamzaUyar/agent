/**
 * Backend istemcisi. Bileşenler `fetch` bilmez; bütün çağrılar buradan geçer.
 * Tarayıcı `/api/*`'ye gider, Next.js bunu backend'e yönlendirir (next.config.ts).
 */
import { readSse } from "./sse"
import type {
  ChatEvent,
  EvaluationEvent,
  ImageDetail,
  ImageSummary,
  TrackOverview,
  ZonesResponse,
} from "./types"

export const API_BASE = "/api"

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message = `İstek başarısız (${response.status})`
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === "string") message = body.detail
  } catch {
    // Gövde JSON değil; durum koduyla yetin.
  }
  return new ApiError(response.status, message)
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) throw await errorFrom(response)
  return (await response.json()) as T
}

export const getZones = (signal?: AbortSignal) => getJson<ZonesResponse>("/zones", signal)

export const getImages = (signal?: AbortSignal) => getJson<ImageSummary[]>("/images", signal)

export const getImage = (imageId: string, signal?: AbortSignal) =>
  getJson<ImageDetail>(`/images/${encodeURIComponent(imageId)}`, signal)

/** Bütün track'ler, kayıtlarıyla; seviye bittiği görüntünün son değerlendirmesinden. */
export const getTracks = (signal?: AbortSignal) => getJson<TrackOverview[]>("/tracks", signal)

export const imageFileUrl = (imageId: string) =>
  `${API_BASE}/images/${encodeURIComponent(imageId)}/file`

async function* postStream<E extends { event: string; data: unknown }>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<E> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await errorFrom(response)
  if (!response.body) throw new ApiError(response.status, "Akış gövdesi boş")
  for await (const message of readSse(response.body)) {
    yield { event: message.event, data: JSON.parse(message.data) } as E
  }
}

/** Değerlendirme akışı: `run`, `step`…, son olay `brief` ya da `error`. */
export const streamEvaluation = (imageId: string, recompute: boolean, signal?: AbortSignal) =>
  postStream<EvaluationEvent>("/evaluations", { image_id: imageId, recompute }, signal)

/** Sohbet akışı: `tool`…, son olay `answer` ya da `error`. */
export const streamChat = (runId: string, message: string, signal?: AbortSignal) =>
  postStream<ChatEvent>(`/evaluations/${encodeURIComponent(runId)}/chat`, { message }, signal)
