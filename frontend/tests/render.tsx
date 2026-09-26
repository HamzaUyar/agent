import { render } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { OperasyonEkrani } from "@/components/operasyon/operasyon-ekrani"
import { TooltipProvider } from "@/components/ui/tooltip"
import { MapAdapterProvider } from "@/lib/harita/context"

import { FakeMap } from "./sahte-harita"

/** Operasyon sayfasını sahte haritayla render eder; API MSW ile taklit edilir (tests/setup.ts). */
export function renderEkran() {
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
