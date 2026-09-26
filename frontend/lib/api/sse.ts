/**
 * `text/event-stream` gövdesini olaylara ayırır.
 *
 * `EventSource` POST desteklemediği için akış `fetch` + `ReadableStream` ile okunur.
 * Parçalar satır ortasında bölünebilir; çok satırlı `data` birleştirilir.
 */
export type SseMessage = { event: string; data: string }

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  // Parçanın sonundaki \r, sonraki parçanın \n'iyle birlikte tek satır sonu olabilir.
  let pendingCr = ""
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      let text = pendingCr + decoder.decode(value, { stream: true })
      pendingCr = text.endsWith("\r") ? "\r" : ""
      if (pendingCr) text = text.slice(0, -1)
      buffer += text.replace(/\r\n?/g, "\n")
      let boundary: number
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const message = parseBlock(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (message) yield message
      }
    }
    const last = parseBlock(buffer + (pendingCr ? "\n" : ""))
    if (last) yield last
  } finally {
    reader.releaseLock()
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = "message"
  const data: string[] = []
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? "" : line.slice(colon + 1)
    if (value.startsWith(" ")) value = value.slice(1)
    if (field === "event") event = value
    else if (field === "data") data.push(value)
  }
  return data.length ? { event, data: data.join("\n") } : null
}
