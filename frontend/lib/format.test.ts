import { describe, expect, it } from "vitest"

import { formatConfidence, formatDistance, formatSpeed } from "./format"
import { RISK, vehicleClass } from "./labels"

describe("Türkçe biçim", () => {
  it("mesafe 1 km'nin altında metre, üstünde bir ondalıklı kilometre", () => {
    expect(formatDistance(0.44)).toBe("0,4 m")
    expect(formatDistance(850.4)).toBe("850 m")
    expect(formatDistance(1646.8)).toBe("1,6 km")
    expect(formatDistance(5511.2)).toBe("5,5 km")
    expect(formatDistance(12000)).toBe("12 km")
  })

  it("hız ve güven", () => {
    expect(formatSpeed(6.43)).toBe("6,4 m/s")
    expect(formatConfidence(0.91)).toBe("%91")
  })

  it("seviye şekil ve kelimeyle, sınıf Türkçe", () => {
    expect(RISK.critical).toMatchObject({ label: "Kritik", shape: "◆" })
    expect(vehicleClass("truck")).toBe("kamyon")
    expect(vehicleClass(null)).toBe("tip bilinmiyor")
  })
})
