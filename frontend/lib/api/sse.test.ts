import { describe, expect, it } from "vitest"

import { readSse } from "./sse"

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

async function collect(chunks: string[]) {
  const out = []
  for await (const message of readSse(streamOf(chunks))) out.push(message)
  return out
}

describe("readSse", () => {
  it("parçalara bölünmüş olayları birleştirir", async () => {
    const messages = await collect([
      "event: st",
      'ep\ndata: {"step_no":',
      '1}\n\nevent: brief\ndata: {"a":1}\n',
      "\n",
    ])

    expect(messages).toEqual([
      { event: "step", data: '{"step_no":1}' },
      { event: "brief", data: '{"a":1}' },
    ])
  })

  it("çok satırlı data'yı satır sonuyla birleştirir, yorumları ve CRLF'yi tanır", async () => {
    const messages = await collect([": ping\r\n\r\nevent: answer\r\ndata: bir\r\ndata: iki\r\n\r\n"])

    expect(messages).toEqual([{ event: "answer", data: "bir\niki" }])
  })

  it("parçalar arasında bölünen CRLF tek satır sonu sayılır", async () => {
    const messages = await collect(["event: step\r", "\ndata: 1\r", "\n\r", "\n"])

    expect(messages).toEqual([{ event: "step", data: "1" }])
  })

  it("olay adı yoksa 'message' sayar; sondaki boş satırsız olayı da verir", async () => {
    expect(await collect(["data: x"])).toEqual([{ event: "message", data: "x" }])
  })
})
