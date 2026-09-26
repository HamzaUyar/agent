/**
 * Açık / koyu tema. Tema `<html>` üzerindeki `dark` sınıfıdır; token'lar (app/globals.css) buna göre
 * değişir. Varsayılan koyu. Seçim tarayıcıda saklanır ve sayfa boyanmadan önce uygulanır (TEMA_BETIGI).
 */
export type Tema = "koyu" | "acik"

export const TEMA_ANAHTARI = "operasyon-tema"

/** `<head>` içinde, ilk boyamadan önce çalışır: kayıtlı açık temayı yanıp sönme olmadan uygular. */
export const TEMA_BETIGI = `try{if(localStorage.getItem("${TEMA_ANAHTARI}")==="acik")document.documentElement.classList.remove("dark")}catch(e){}`

export function okuTema(): Tema {
  return document.documentElement.classList.contains("dark") ? "koyu" : "acik"
}

export function uygulaTema(tema: Tema) {
  document.documentElement.classList.toggle("dark", tema === "koyu")
  try {
    localStorage.setItem(TEMA_ANAHTARI, tema)
  } catch {
    // Depolama kapalı (gizli pencere vb.): tema bu oturumda geçerli, kalıcı değil.
  }
}
