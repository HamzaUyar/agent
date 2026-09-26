import type { Metadata } from "next"
import { Atkinson_Hyperlegible, JetBrains_Mono } from "next/font/google"

import { TooltipProvider } from "@/components/ui/tooltip"

import "./globals.css"

const atkinson = Atkinson_Hyperlegible({
  variable: "--font-atkinson",
  weight: ["400", "700"],
  subsets: ["latin", "latin-ext"],
})

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin", "latin-ext"],
})

export const metadata: Metadata = {
  title: "Üs Koruma Karar Destek",
  description: "Merkez Üs operasyon ekranı: harita, görüntü değerlendirmesi ve temas incelemesi",
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" className={`${atkinson.variable} ${jetbrainsMono.variable} dark h-full antialiased`}>
      <body className="h-full overflow-hidden">
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  )
}
