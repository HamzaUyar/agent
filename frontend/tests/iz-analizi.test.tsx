import { act, fireEvent, screen, waitFor, within } from "@testing-library/react"
import type { Feature } from "geojson"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { TrackOverview } from "@/lib/api/types"
import { dakika } from "@/lib/iz"
import { useOperasyon } from "@/store/operasyon"

import { http, HttpResponse } from "msw"

import { API, fixtures } from "./msw/handlers"
import { server } from "./msw/server"
import { renderEkran } from "./render"
import type { FakeMap } from "./sahte-harita"

const tracks = fixtures.tracks as TrackOverview[]
const count = (level: TrackOverview["level"]) => tracks.filter((t) => t.level === level).length
const features = (map: FakeMap) => map.areas.get("izler")?.features ?? []
const ids = (list: Feature[], kind: string) =>
  list.filter((f) => f.properties!.kind === kind).map((f) => f.properties!.id as string)

async function opened() {
  // Gerçek başlangıç: İz analizi açık.
  const view = renderEkran({ izOpen: true })
  const card = await screen.findByRole("region", { name: "İz analizi" })
  await within(card).findByRole("group", { name: "Risk seviyesi süzgeci" })
  return { ...view, card }
}

afterEach(() => vi.useRealTimers())

describe("İz analizi: açma ve süzgeç", () => {
  it("uygulama açılışında İz analizi açık gelir: bütün track'ler tam yollarıyla, hareketsiz", async () => {
    expect(useOperasyon.getInitialState().izOpen).toBe(true)
    const { card, map } = await opened()

    expect(screen.getByRole("button", { name: "İz analizi" })).toHaveAttribute("aria-pressed", "true")
    expect(within(card).getByText("Tüm gün")).toBeInTheDocument()
    expect(card).toHaveTextContent(`${tracks.length} / ${tracks.length} track`)
    await waitFor(() => expect(ids(features(map), "yol")).toHaveLength(tracks.length))
    expect(ids(features(map), "bas")).toEqual([])
  })

  it("seviyeler çoklu seçilir: Hepsi'yi kaldırıp Kritik + Orta seçince yalnızca onların track'leri", async () => {
    const { card, user, map } = await opened()
    const filter = within(card).getByRole("group", { name: "Risk seviyesi süzgeci" })

    await user.click(within(filter).getByRole("button", { name: "Hepsi" }))
    expect(card).toHaveTextContent(`0 / ${tracks.length} track`)
    await user.click(within(filter).getByRole("button", { name: "Kritik" }))
    await user.click(within(filter).getByRole("button", { name: "Orta" }))

    const expected = tracks.filter((t) => t.level === "critical" || t.level === "medium").map((t) => t.track_id)
    expect(card).toHaveTextContent(`${expected.length} / ${tracks.length} track`)
    expect(within(filter).getByRole("button", { name: "Hepsi" })).toHaveAttribute("aria-pressed", "false")
    await waitFor(() => expect(ids(features(map), "yol").sort()).toEqual(expected.sort()))

    await user.click(within(filter).getByRole("button", { name: "Hepsi" }))
    await waitFor(() => expect(ids(features(map), "yol")).toHaveLength(tracks.length))
  })

  it("süzgeç anahtarlarında adet yazmaz; değerlendirilmemiş track'ler 'Değerlendirilmedi' anahtarında", async () => {
    const { card } = await opened()
    const filter = within(card).getByRole("group", { name: "Risk seviyesi süzgeci" })
    expect(within(filter).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Hepsi",
      "Kritik",
      "Yüksek",
      "Orta",
      "Düşük",
      "Değerlendirilmedi",
    ])
    expect(count(null)).toBeGreaterThan(0)
  })

  it("değerlendirilmemiş track yoksa 'Değerlendirilmedi' anahtarı gösterilmez", async () => {
    server.use(
      http.get(`${API}/tracks`, () =>
        HttpResponse.json(tracks.map((t) => ({ ...t, level: t.level ?? "low" }))),
      ),
    )
    const { card } = await opened()
    const filter = within(card).getByRole("group", { name: "Risk seviyesi süzgeci" })
    expect(within(filter).queryByRole("button", { name: "Değerlendirilmedi" })).not.toBeInTheDocument()
    expect(within(filter).getByRole("button", { name: "Hepsi" })).toHaveAttribute("aria-pressed", "true")
  })

  it("kapatınca iz katmanı boşalır", async () => {
    const { card, user, map } = await opened()
    await waitFor(() => expect(features(map).length).toBeGreaterThan(0))

    await user.click(within(card).getByRole("button", { name: "İz analizini kapat" }))

    expect(screen.queryByRole("region", { name: "İz analizi" })).not.toBeInTheDocument()
    expect(features(map)).toEqual([])
  })
})

describe("İz analizi: zaman", () => {
  const A = tracks[0]
  const at = (m: number) => {
    const slider = screen.getByRole("slider", { name: "Simülasyon zamanı" })
    fireEvent.change(slider, { target: { value: String(m) } })
  }

  it("bir zamana atlayınca yalnızca kaydı o anı kapsayan track'ler görünür: başlangıçtan önce ve bitişten sonra yok", async () => {
    const { card, map } = await opened()
    const start = dakika(A.start)
    const end = dakika(A.end)

    act(() => at(start - 30))
    expect(ids(features(map), "bas")).not.toContain(A.track_id)
    act(() => at(start))
    expect(ids(features(map), "bas")).toContain(A.track_id)
    act(() => at(end))
    expect(ids(features(map), "bas")).toContain(A.track_id)
    act(() => at(end + 1))
    expect(ids(features(map), "bas")).not.toContain(A.track_id)
    act(() => at(end + 30))
    expect(ids(features(map), "bas")).not.toContain(A.track_id)

    // Görünen sayı o anda kaydı olan track sayısıdır; saat gösterilir.
    const active = tracks.filter((t) => dakika(t.start) <= end + 30 && dakika(t.end) >= end + 30).length
    expect(card).toHaveTextContent(`şu an ${active} araç`)
    expect(ids(features(map), "bas")).toHaveLength(active)
    expect(ids(features(map), "yol")).toEqual([])
  })

  it("Oynat zamanı ilerletir, Duraklat durdurur ve kaldığı yerden devam eder; Sıfırla hazır hâline döner", async () => {
    const { card, map } = await opened()
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance"] })

    fireEvent.click(within(card).getByRole("button", { name: "Oynat" }))
    const start = Math.min(...tracks.map((t) => dakika(t.start)))
    expect(useOperasyon.getState().izTime).toBe(start)
    // 1× = saniyede 5 dakika: 2 saniyede 10 dakika.
    act(() => vi.advanceTimersByTime(2000))
    expect(useOperasyon.getState().izTime).toBeGreaterThanOrEqual(start + 9)
    expect(ids(features(map), "bas").length).toBeGreaterThan(0)

    fireEvent.click(within(card).getByRole("button", { name: "Duraklat" }))
    const paused = useOperasyon.getState().izTime!
    act(() => vi.advanceTimersByTime(2000))
    expect(useOperasyon.getState().izTime).toBe(paused)
    expect(card).toHaveTextContent("duraklatıldı")

    // Hız 4×: aynı sürede dört kat.
    fireEvent.click(within(card).getByRole("button", { name: "4×" }))
    fireEvent.click(within(card).getByRole("button", { name: "Oynat" }))
    act(() => vi.advanceTimersByTime(1000))
    expect(useOperasyon.getState().izTime).toBeGreaterThanOrEqual(paused + 19)

    fireEvent.click(within(card).getByRole("button", { name: "Sıfırla: bütün yollar, hareketsiz" }))
    expect(within(card).getByText("Tüm gün")).toBeInTheDocument()
    expect(ids(features(map), "yol")).toHaveLength(tracks.length)
  })
})

describe("İz analizi ve seçili kare", () => {
  it("kare seçilince izler soluklaşır, seçili karenin araçları ve rotaları tam renkli kalır; kare bırakılınca izler geri gelir", async () => {
    const { map, user } = await opened()
    await waitFor(() => expect(features(map).length).toBeGreaterThan(0))
    expect(features(map).every((f) => !f.properties!.dimmed)).toBe(true)

    await user.click(screen.getByRole("button", { name: /^img_000860/ }))
    await user.click(screen.getByRole("button", { name: "Risk analizini başlat" }))
    await screen.findByLabelText("Görüntü risk seviyesi")

    expect(features(map).every((f) => f.properties!.dimmed)).toBe(true)
    expect(map.areas.get("rotalar")!.features.every((f) => !f.properties!.dimmed)).toBe(true)

    act(() => useOperasyon.getState().close("left"))
    expect(features(map).every((f) => !f.properties!.dimmed)).toBe(true)
  })
})

describe("İz analizi: oynatma yarışları", () => {
  it("Duraklat ve Sıfırla art arda gelince bekleyen animasyon karesi hazır hâlinin üstüne yazmaz", async () => {
    const { card, map } = await opened()
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance"] })
    fireEvent.click(within(card).getByRole("button", { name: "Oynat" }))
    act(() => vi.advanceTimersByTime(500))

    // Efektler çalışmadan (aynı görevde) önce duraklat, sonra sıfırla; ardından bir kare geçsin.
    act(() => {
      useOperasyon.getState().pause()
      useOperasyon.getState().resetIz()
      vi.advanceTimersByTime(16)
    })
    act(() => vi.advanceTimersByTime(100))

    expect(ids(features(map), "bas")).toEqual([])
    expect(ids(features(map), "yol")).toHaveLength(tracks.length)
  })
})

describe("İz analizi: oynatmada riskli iz uyarısı", () => {
  it("oynarken o an kritik ya da yüksek seviyeli iz varsa haritanın sol üstünde yanıp sönen uyarı; durunca kalkar", async () => {
    const { card } = await opened()
    const high = tracks.find((t) => t.level === "high")!
    const critical = tracks.find((t) => t.level === "critical")!
    const quiet = Math.min(...tracks.map((t) => dakika(t.start)))
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance"] })

    // Kritik izin kaydı sürerken oynat.
    act(() => useOperasyon.getState().setIzTime(dakika(critical.end) - 1))
    fireEvent.click(within(card).getByRole("button", { name: "Oynat" }))
    act(() => vi.advanceTimersByTime(100))
    const alert = screen.getByRole("status", { name: "Riskli iz uyarısı" })
    expect(alert).toHaveTextContent("Kritik riskli iz")
    expect(dakika(high.start)).toBeGreaterThan(0)

    fireEvent.click(within(card).getByRole("button", { name: "Duraklat" }))
    expect(screen.queryByRole("status", { name: "Riskli iz uyarısı" })).not.toBeInTheDocument()

    // Kaydı olan hiçbir kritik/yüksek iz yoksa uyarı yok.
    const calm = tracks.filter((t) => t.level === "critical" || t.level === "high")
    const noneActive = (m: number) => calm.every((t) => dakika(t.start) > m || dakika(t.end) < m)
    if (noneActive(quiet)) {
      act(() => useOperasyon.getState().setIzTime(quiet))
      fireEvent.click(within(card).getByRole("button", { name: "Oynat" }))
      act(() => vi.advanceTimersByTime(16))
      expect(screen.queryByRole("status", { name: "Riskli iz uyarısı" })).not.toBeInTheDocument()
    }
  })
})

describe("İz analizi: vurgu", () => {
  it("haritada bir track'e tıklamak onu vurgular, diğerleri soluklaşır; kart bittiği görüntüyü önerir; Esc kaldırır", async () => {
    const { card, map, user } = await opened()
    const target = tracks.find((t) => t.image_id === "img_000860")!

    act(() => map.events!.onAreaClick?.("izler", target.track_id))

    const panel = within(card).getByRole("region", { name: "Vurgulanan track" })
    expect(panel).toHaveTextContent(target.track_id)
    expect(within(panel).getByRole("button", { name: "Görüntüye git: img_000860" })).toBeInTheDocument()
    const highlighted = features(map).find((f) => f.properties!.id === target.track_id)!
    expect(highlighted.properties!.highlighted).toBe(true)
    expect(features(map).find((f) => f.properties!.id !== target.track_id)!.properties!.dimmed).toBe(true)

    await user.keyboard("{Escape}")
    expect(within(card).queryByRole("region", { name: "Vurgulanan track" })).not.toBeInTheDocument()
  })

  it("Görüntüye git zaten değerlendirilmiş seçili karede aracı hemen seçer", async () => {
    const { card, user } = await opened()
    await user.click(screen.getByRole("button", { name: /^img_000860/ }))
    await user.click(screen.getByRole("button", { name: "Risk analizini başlat" }))
    await screen.findByLabelText("Görüntü risk seviyesi")
    act(() => useOperasyon.getState().selectContact(null))

    act(() => useOperasyon.getState().setIzHighlight("T0122"))
    await user.click(within(card).getByRole("button", { name: "Görüntüye git: img_000860" }))

    expect(useOperasyon.getState().selectedContactKey).toBe("T0122")
    expect(useOperasyon.getState().pendingContactKey).toBeNull()
  })

  it("haritada boş bir yere tıklamak vurguyu kaldırır", async () => {
    const { card, map } = await opened()
    act(() => map.events!.onAreaClick?.("izler", tracks[0].track_id))
    expect(within(card).getByRole("region", { name: "Vurgulanan track" })).toBeInTheDocument()

    act(() => map.events!.onMapClick?.())

    expect(within(card).queryByRole("region", { name: "Vurgulanan track" })).not.toBeInTheDocument()
  })

  it("Görüntüye git kareyi seçip Görüntü çekmecesini açar ama analizi başlatmaz; analiz bitince track'in aracı seçili gelir", async () => {
    const posts = vi.fn()
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST") posts(request.url)
    })
    const { card, user } = await opened()
    act(() => useOperasyon.getState().setIzHighlight("T0122"))

    await user.click(within(card).getByRole("button", { name: "Görüntüye git: img_000860" }))

    expect(useOperasyon.getState().selectedImageId).toBe("img_000860")
    const drawer = screen.getByRole("region", { name: "Görüntü" })
    expect(await within(drawer).findByRole("button", { name: "Risk analizini başlat" })).toBeEnabled()
    expect(posts).not.toHaveBeenCalled()
    expect(useOperasyon.getState().evaluation).toBeNull()
    // Vurgu kalkar: harita seçili kareye geçer.
    expect(within(card).queryByRole("region", { name: "Vurgulanan track" })).not.toBeInTheDocument()

    await user.click(within(drawer).getByRole("button", { name: "Risk analizini başlat" }))
    await screen.findByLabelText("Görüntü risk seviyesi")
    expect(posts).toHaveBeenCalledTimes(1)
    expect(useOperasyon.getState().selectedContactKey).toBe("T0122")
    server.events.removeAllListeners()
  })
})

describe("İz analizi: track seçimi Risk & Araçlar'a yansır", () => {
  it("değerlendirilmiş track'e tıklamak bittiği karenin kaydını oynatır; panel o aracın kartını gösterir", async () => {
    const posts = vi.fn()
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST") posts(request.url)
    })
    const { map } = await opened()

    act(() => map.events!.onAreaClick?.("izler", "T0122"))

    const drawer = screen.getByRole("region", { name: "Risk & Araçlar" })
    expect(useOperasyon.getState().selectedImageId).toBe("img_000860")
    expect(await within(drawer).findByRole("article", { name: /^Araç: T0122/ })).toBeInTheDocument()
    expect(useOperasyon.getState().selectedContactKey).toBe("T0122")
    expect(within(drawer).queryByRole("region", { name: "Seçili track" })).not.toBeInTheDocument()
    expect(posts).toHaveBeenCalledTimes(1)
    server.events.removeAllListeners()
  })

  it("değerlendirilmemiş track'e tıklamak paneli track kartıyla açar, analiz başlatmaz", async () => {
    const posts = vi.fn()
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST") posts(request.url)
    })
    const { map } = await opened()
    const target = tracks.find((t) => t.image_id && !t.kind && !t.unframed)!

    act(() => map.events!.onAreaClick?.("izler", target.track_id))

    const drawer = screen.getByRole("region", { name: "Risk & Araçlar" })
    const panel = within(drawer).getByRole("region", { name: "Seçili track" })
    expect(panel).toHaveTextContent(target.track_id)
    expect(panel).toHaveTextContent(`kayıt ${target.start}–${target.end}`)
    expect(within(panel).getByRole("button", { name: `Görüntüye git: ${target.image_id}` })).toBeInTheDocument()
    expect(posts).not.toHaveBeenCalled()
    expect(useOperasyon.getState().evaluation).toBeNull()
    server.events.removeAllListeners()
  })
})

describe("Harita: genel görünüm ve odağı kaldırma", () => {
  it("Genel görünüm seçimi bozmadan haritayı açılıştaki kutuya geri sığdırır", async () => {
    const { map, user } = await opened()
    await waitFor(() => expect(map.fits.length).toBeGreaterThan(0))
    const overview = map.fits.at(-1)!

    act(() => map.events!.onAreaClick?.("izler", "T0122"))
    await screen.findByRole("article", { name: /^Araç: T0122/ })
    expect(map.fits.at(-1)).not.toEqual(overview)

    await user.click(screen.getByRole("button", { name: "Genel görünüm" }))

    expect(map.fits.at(-1)).toEqual(overview)
    expect(useOperasyon.getState().selectedContactKey).toBe("T0122")
  })

  it("Odağı kaldır seçili aracı, vurguyu ve kareyi bırakır; harita genel görünüme döner", async () => {
    const { map, user } = await opened()
    await waitFor(() => expect(map.fits.length).toBeGreaterThan(0))
    const overview = map.fits.at(-1)!
    expect(screen.queryByRole("button", { name: "Odağı kaldır" })).not.toBeInTheDocument()

    act(() => map.events!.onAreaClick?.("izler", "T0122"))
    await screen.findByRole("article", { name: /^Araç: T0122/ })

    await user.click(screen.getByRole("button", { name: "Odağı kaldır" }))

    const s = useOperasyon.getState()
    expect([s.selectedContactKey, s.izHighlight, s.selectedImageId, s.evaluation]).toEqual([null, null, null, null])
    await waitFor(() => expect(map.fits.at(-1)).toEqual(overview))
    expect(screen.queryByRole("button", { name: "Odağı kaldır" })).not.toBeInTheDocument()
  })
})
