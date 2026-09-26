"use client"

import { createContext, useContext, type ReactNode } from "react"

import type { MapAdapterFactory } from "./types"

/** Varsayılan: MapLibre, yalnızca tarayıcıda ve ilk kullanımda yüklenir. */
const mapLibreFactory: MapAdapterFactory = async (container, events) => {
  const { createMapLibreAdapter } = await import("./maplibre-adapter")
  return createMapLibreAdapter(container, events)
}

const MapAdapterContext = createContext<MapAdapterFactory>(mapLibreFactory)

/** Harita sağlayıcısını değiştirir (testlerde sahte uygulama, ileride başka bir sağlayıcı). */
export function MapAdapterProvider({
  factory,
  children,
}: {
  factory: MapAdapterFactory
  children: ReactNode
}) {
  return <MapAdapterContext.Provider value={factory}>{children}</MapAdapterContext.Provider>
}

export const useMapAdapterFactory = () => useContext(MapAdapterContext)
