import { render } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { OperasyonEkrani } from "@/components/operasyon/operasyon-ekrani"
import { TooltipProvider } from "@/components/ui/tooltip"
import { MapAdapterProvider } from "@/lib/harita/context"
import { useOperasyon } from "@/store/operasyon"

import { FakeMap } from "./sahte-harita"

/**
 * Operasyon sayfasını sahte haritayla render eder; API MSW ile taklit edilir (tests/setup.ts).
 * "Günün görüntüleri" gerçekte kapalı başlar; şeridi kullanan testler için varsayılan olarak açık
 * render edilir (`timelineOpen: false` ile gerçek başlangıç). İz analizi de gerçekte açık başlar;
 * testlerde varsayılan kapalı (`izOpen: true` ile gerçek başlangıç).
 */
export function renderEkran({
  timelineOpen = true,
  izOpen = false,
}: { timelineOpen?: boolean; izOpen?: boolean } = {}) {
  // İz analizi gerçekte açık başlar; ondan bağımsız davranışların testleri için varsayılan kapalı.
  useOperasyon.setState({ timelineOpen, izOpen })
  const user = userEvent.setup()
  const map = new FakeMap()
  const view = render(
    <TooltipProvider>
      <MapAdapterProvider factory={map.factory}>
        <OperasyonEkrani />
      </MapAdapterProvider>
    </TooltipProvider>,
  )
  return { user, map, ...view }
}
