"""Basit, hard-coded, açıklanabilir risk skoru: yalnızca 3 sinyal.

Üretim pipeline'ından (app/pipelines/risk.py, EvaluationService) bağımsız bir keşif
scripti. Tanımlar ve puanlar aşağıda, tek yerde:

- ADIM: ardışık iki track noktası arası mesafe.
- DURAGAN ADIM: adım < DURAGAN_ADIM_M.
- DURAKLAMA: art arda en az DURAKLAMA_MIN_ADIM durağan adım. Süre = durağan adım
  sayısı x TRACK_STEP_MINUTES. Konum ve üsse mesafe = duraklamadaki noktaların ortalaması.
- GERİ DÖNÜŞ: konum GERI_DONUS_CELL_*_DEG boyutunda hücrelere bölünür. Araç bir
  hücreden çıkıp en az GERI_DONUS_MIN_GAP_DK dakika sonra aynı hücreye tekrar
  giriyorsa bu bir geri dönüştür.

Skor üç sinyalin puanının toplamı, SKOR_TAVAN'da sınırlanır; seviye SEVIYE_ESIK'e göre.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import time
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.data_package import TRACK_STEP_MINUTES, format_hhmm, read_package, to_minutes
from app.pipelines.geo import distance_m
from app.schemas.domain import GeoPoint

OUTPUT_PATH = Path("outputs/simple_risk.csv")

# --- Sabitler (hepsi burada, tek yerde) --------------------------------------

DURAGAN_ADIM_M = 25.0
DURAKLAMA_MIN_ADIM = 2

GERI_DONUS_CELL_LAT_DEG = 0.00135  # ~150 m
GERI_DONUS_CELL_LON_DEG = 0.00176  # ~150 m (bu enlemde)
GERI_DONUS_MIN_GAP_DK = 15

US_YAKINI_PARK_M1, US_YAKINI_PARK_DK1, US_YAKINI_PARK_PUAN1 = 1000, 30, 40
US_YAKINI_PARK_M2, US_YAKINI_PARK_DK2, US_YAKINI_PARK_PUAN2 = 2000, 30, 20

ARAC_TIPI_PUAN = {"truck": 30, "van": 25, "bus": 10, "car": 5, "unknown": 10}

SKOR_TAVAN = 100
SEVIYE_ESIK: list[tuple[int, str]] = [(75, "KRITIK"), (50, "YUKSEK"), (25, "ORTA"), (0, "DUSUK")]


def _seviye(skor: int) -> str:
    for esik, ad in SEVIYE_ESIK:
        if skor >= esik:
            return ad
    return "DUSUK"


def _dolasma_puan(sayi: int) -> int:
    if sayi <= 0:
        return 0
    if sayi == 1:
        return 15
    if sayi == 2:
        return 25
    return 35


@lru_cache
def _base() -> GeoPoint:
    return read_package(get_settings().resolved_data_dir).base.location


# --- DURAKLAMA ----------------------------------------------------------------

Nokta = tuple[time, GeoPoint]


@dataclass(frozen=True)
class Duraklama:
    start: time
    end: time
    dakika: int
    mesafe_m: float


def _duraklamalar(points: list[Nokta], base: GeoPoint) -> list[Duraklama]:
    """Art arda en az DURAKLAMA_MIN_ADIM durağan adımdan oluşan duraklamaları döndürür."""
    times = [t for t, _ in points]
    locs = [p for _, p in points]
    adimlar_m = [distance_m(a, b) for a, b in zip(locs, locs[1:], strict=False)]
    duragan = [d < DURAGAN_ADIM_M for d in adimlar_m]

    duraklamalar: list[Duraklama] = []
    i, n = 0, len(duragan)
    while i < n:
        if not duragan[i]:
            i += 1
            continue
        j = i
        while j < n and duragan[j]:
            j += 1
        run = j - i  # i..j arası durağan adım sayısı
        if run >= DURAKLAMA_MIN_ADIM:
            secili = locs[i : j + 1]
            mesafe_m = sum(distance_m(p, base) for p in secili) / len(secili)
            duraklamalar.append(
                Duraklama(times[i], times[j], run * TRACK_STEP_MINUTES, mesafe_m)
            )
        i = j
    return duraklamalar


def _park_puan(duraklamalar: list[Duraklama]) -> tuple[int, str]:
    tier1 = [
        d for d in duraklamalar if d.mesafe_m < US_YAKINI_PARK_M1 and d.dakika >= US_YAKINI_PARK_DK1
    ]
    tier2 = [
        d
        for d in duraklamalar
        if US_YAKINI_PARK_M1 <= d.mesafe_m < US_YAKINI_PARK_M2 and d.dakika >= US_YAKINI_PARK_DK2
    ]
    if tier1:
        en_uzun = max(tier1, key=lambda d: d.dakika)
        return US_YAKINI_PARK_PUAN1, _park_gerekce(en_uzun, US_YAKINI_PARK_PUAN1)
    if tier2:
        en_uzun = max(tier2, key=lambda d: d.dakika)
        return US_YAKINI_PARK_PUAN2, _park_gerekce(en_uzun, US_YAKINI_PARK_PUAN2)
    return 0, "tetiklenmedi"


def _park_gerekce(d: Duraklama, puan: int) -> str:
    km = d.mesafe_m / 1000
    return (
        f"Üsse {km:.1f} km mesafede {d.dakika} dk bekledi "
        f"({format_hhmm(d.start)}-{format_hhmm(d.end)}) -> +{puan}"
    )


# --- GERİ DÖNÜŞ -----------------------------------------------------------------


def _geri_donus_sayisi(points: list[Nokta]) -> int:
    """Bir hücreden çıkıp en az GERI_DONUS_MIN_GAP_DK dakika sonra aynı hücreye dönüşleri sayar."""
    cells = [
        (int(p.lat / GERI_DONUS_CELL_LAT_DEG), int(p.lon / GERI_DONUS_CELL_LON_DEG))
        for _, p in points
    ]
    last_seen: dict[tuple[int, int], time] = {}
    current: tuple[int, int] | None = None
    count = 0
    for (t, _), cell in zip(points, cells, strict=True):
        if cell != current:
            prev = last_seen.get(cell)
            if prev is not None and to_minutes(t) - to_minutes(prev) >= GERI_DONUS_MIN_GAP_DK:
                count += 1
            current = cell
        last_seen[cell] = t
    return count


# --- ARAÇ TİPİ ------------------------------------------------------------------


def _tip_puan(tip: str) -> tuple[int, str]:
    puan = ARAC_TIPI_PUAN.get(tip, ARAC_TIPI_PUAN["unknown"])
    ad = "bilinmiyor" if tip not in ARAC_TIPI_PUAN else tip
    return puan, f"Araç tipi {ad} -> +{puan}"


# --- Puanlama --------------------------------------------------------------------


def score_track(track_df: pd.DataFrame, vehicle_class: str) -> dict[str, object]:
    """Bir track için 3 sinyalin puanı, gerekçesi, toplam skor ve seviye."""
    df = track_df.sort_values("time").reset_index(drop=True)
    track_id = df["track_id"].iloc[0]
    points: list[Nokta] = [(row.time, GeoPoint(row.lat, row.lon)) for row in df.itertuples()]

    duraklamalar = _duraklamalar(points, _base())
    park_puan, park_gerekce = _park_puan(duraklamalar)

    donus_sayisi = _geri_donus_sayisi(points)
    donus_puan = _dolasma_puan(donus_sayisi)
    donus_gerekce = (
        f"Son 2 saatte aynı bölgeye {donus_sayisi} kez geri döndü -> +{donus_puan}"
        if donus_sayisi > 0
        else "tetiklenmedi"
    )

    tip_puan, tip_gerekce = _tip_puan(vehicle_class)

    skor = min(park_puan + donus_puan + tip_puan, SKOR_TAVAN)
    return {
        "track_id": track_id,
        "arac_tipi": vehicle_class,
        "skor": skor,
        "seviye": _seviye(skor),
        "park_puan": park_puan,
        "park_gerekce": park_gerekce,
        "donus_sayisi": donus_sayisi,
        "donus_puan": donus_puan,
        "donus_gerekce": donus_gerekce,
        "tip_puan": tip_puan,
        "tip_gerekce": tip_gerekce,
    }


def score_all(tracks_df: pd.DataFrame, class_map: dict[str, str]) -> pd.DataFrame:
    """Her track için `score_track` çağırır; sonuç bir satır/track DataFrame'idir."""
    rows = [
        score_track(group, class_map.get(str(track_id), "unknown"))
        for track_id, group in tracks_df.groupby("track_id", sort=False)
    ]
    return pd.DataFrame(rows)


# --- main ------------------------------------------------------------------------


def _load_tracks_df() -> pd.DataFrame:
    package = read_package(get_settings().resolved_data_dir)
    return pd.DataFrame(
        {"track_id": p.track_id, "time": p.time, "lat": p.location.lat, "lon": p.location.lon}
        for p in package.track_points
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--classes",
        type=Path,
        help="track_id -> araç tipi eşleyen JSON dosyası (yoksa hepsi 'unknown')",
    )
    args = parser.parse_args()

    class_map: dict[str, str] = (
        json.loads(args.classes.read_text(encoding="utf-8")) if args.classes else {}
    )

    tracks_df = _load_tracks_df()
    result = score_all(tracks_df, class_map)
    result = result.sort_values("skor", ascending=False).reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)
    print(f"{len(result)} track skorlandı -> {OUTPUT_PATH}")

    print("\nSeviye dağılımı:")
    print(
        result["seviye"]
        .value_counts()
        .reindex(["KRITIK", "YUKSEK", "ORTA", "DUSUK"], fill_value=0)
        .to_string()
    )

    print("\nSkora göre ilk 10 track:")
    for _, r in result.head(10).iterrows():
        print(
            f"{r['track_id']:<7} skor {r['skor']:>3}  {r['seviye']:<6}  "
            f"{r['park_gerekce']} | {r['donus_gerekce']} | {r['tip_gerekce']}"
        )

    print("\nÖrnek track'ler:")
    for track_id in ("T0122", "T0206"):
        eslesen = result[result["track_id"] == track_id]
        if eslesen.empty:
            print(f"{track_id}: bulunamadı")
            continue
        r = eslesen.iloc[0]
        print(f"{track_id}  skor {r['skor']}  {r['seviye']}")
        print(f"  {r['park_gerekce']}")
        print(f"  {r['donus_gerekce']}")
        print(f"  {r['tip_gerekce']}")


if __name__ == "__main__":
    main()
