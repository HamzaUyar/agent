/** Sayılar Türkçe biçimde: 1,6 km · 850 m · 6,2 m/s. */

const LOCALE = "tr-TR"

const oneDecimal = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 })
const integer = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 })
const percent = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 0 })

/** 10 m'nin altı bir ondalıklı metre, 1 km'nin altı metre, üstü bir ondalıklı kilometre. */
export function formatDistance(meters: number): string {
  if (meters < 10) return `${oneDecimal.format(meters)} m`
  if (meters < 1000) return `${integer.format(meters)} m`
  return `${oneDecimal.format(meters / 1000)} km`
}

export const formatSpeed = (mps: number) => `${oneDecimal.format(mps)} m/s`

export const formatConfidence = (value: number) => percent.format(value)

export const formatDegrees = (deg: number) => `${integer.format(deg)}°`

export const formatNumber = (value: number) => oneDecimal.format(value)
