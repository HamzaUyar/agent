import { describe, expect, it } from "vitest"

import type { StepEvent } from "@/lib/api/types"

import { orchestratorCalls } from "./orkestrator"

const step = (step_no: number, name: string, summary: string, data: Record<string, unknown> = {}): StepEvent => ({
  step_no,
  name,
  summary,
  data,
})

const finding = (over: Record<string, unknown>) => ({
  claim_id: 1,
  report_time: "14:00",
  source: "official",
  text: "",
  claim_type: "vehicle",
  track_id: null,
  verdict: "unverifiable",
  certainty: "unverified",
  effect: "none",
  reasoning: "",
  rule_verdict: "unverifiable",
  detail_verdict: "unverifiable",
  needs_review: false,
  dangerous_reassurance: false,
  ...over,
})

describe("orchestratorCalls", () => {
  it("rapor agent'ı her iddiayı alt çağrı olarak gösterir: kural ikinci görüşü, tehlikeli güvence, gözcü notu", () => {
    const [call] = orchestratorCalls([
      step(1, "raporlar", "2 iddia", {
        findings: [
          finding({
            claim_id: 262,
            track_id: "T0122",
            verdict: "contradicts",
            detail_verdict: "contradicts",
            rule_verdict: "contradicts",
            dangerous_reassurance: true,
            reasoning: "tespit modeli görmedi; görsel incelemede kamyon (eminlik düşük, karara girmedi)",
          }),
          finding({ claim_id: 7, source: "third_party", needs_review: true, rule_verdict: "contradicts" }),
        ],
        visual_checks: [],
      }),
    ])
    expect(call).toMatchObject({ kind: "agent", args: "2 iddia", by: "LLM + kural ikinci görüşü" })
    expect(call.children[0]).toEqual({
      text: "#262 resmi · T0122 → çelişkili",
      warn: true,
      tags: ["tehlikeli güvence", "kural onayladı", "gözcü: görsel bakış"],
    })
    expect(call.children[1]).toMatchObject({
      text: "#7 üçüncü taraf → doğrulanamaz",
      warn: true,
      tags: ["kural ayrıştı: çelişkili → operatör"],
    })
  })

  it("karar agent'ı modeli ve yalnızca ayar önerilen temasları, motorun kararıyla gösterir", () => {
    const [call] = orchestratorCalls(
      [
        step(1, "karar", "glm/glm-5.3-flash: 1 ayar kabul, 1 red", {
          model: "glm/glm-5.3-flash",
          contacts: [
            { track_id: "T0122", final_level: "critical", adjustment_reason: null, adjustment_rejected: null },
            { track_id: "T0032", final_level: "medium", adjustment_reason: "duraklama", adjustment_rejected: null },
            { track_id: "T0092", final_level: "high", adjustment_reason: "yaklaşma", adjustment_rejected: "seviyede sayılı" },
          ],
        }),
      ],
      [12_300],
    )
    expect(call).toMatchObject({ by: "glm/glm-5.3-flash", result: "1 ayar kabul, 1 red", durationMs: 12_300 })
    expect(call.children).toEqual([
      { text: "T0032 → orta · duraklama", warn: false, tags: ["motor onayladı"] },
      { text: "T0092 → yüksek · yaklaşma", warn: true, tags: ["motor reddetti: seviyede sayılı"] },
    ])
  })
})
