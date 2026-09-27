"""Bağlam katmanı: tek bir araca bağlanamayan raporlar için gün düzeyinde sinyaller.

Konvoy planı, tatbikat, "dün gece" ihbarı ve telsiz kopukluğu doğrulanacak bir iddia
taşımaz ama anlam taşır. İlke asimetrik güvendir (ADR-0002): doğrulanamayan bilgi riski
artıran yönde dikkat çekebilir, riski düşüremez.

- Konvoy / tatbikat: raporun saatine yakın, birlikte hareket eden ağır araç grubu varsa
  "olası örtü hikâyesi" (grup dost olabilir, ama kimlik ve rota doğrulanamıyor).
- Dün gece ihbarı: o bölgede uzun süre bekleyip rapordan sonra kalkan araçlar.
- Telsiz kopukluğu: aynı bölgede, aynı saatte hareket eden ağır araç ya da yaklaşan araç.
"""

from typing import Any

from app.data_package import format_hhmm, from_minutes, to_minutes
from app.pipelines.geo import distance_m, nearest_zone
from app.reports_v2 import evidence as ev

GROUP_MIN = 3
GROUP_RADIUS_M = 1500.0
MOVE_STEP_M = 300.0
CONVOY_WINDOW_MIN = 30
SLEEP_MIN = 30


_GROUPS: dict[int, list[dict[str, Any]]] = {}


def heavy_groups(data: ev.Data) -> list[dict[str, Any]]:
    if id(data) not in _GROUPS:
        _GROUPS[id(data)] = _heavy_groups(data)
    return _GROUPS[id(data)]


def _heavy_groups(data: ev.Data) -> list[dict[str, Any]]:
    """Aynı 5 dakikada birbirine yakın (≤ 1,5 km) en az 3 ağır aracın birlikte ilerlediği anlar."""
    labels = ev.track_labels(data)
    heavy = [t for t, lab in labels.items() if lab in ev.HEAVY]
    by_time: dict[int, dict[str, Any]] = {}
    for tid in heavy:
        pts = data.tracks[tid]
        for a, b in zip(pts, pts[1:], strict=False):
            if distance_m(a.location, b.location) > MOVE_STEP_M:
                by_time.setdefault(to_minutes(b.time), {})[tid] = b.location
    groups: list[dict[str, Any]] = []
    for minute, moving in sorted(by_time.items()):
        for loc in moving.values():
            members = sorted(t for t, l2 in moving.items() if distance_m(loc, l2) <= GROUP_RADIUS_M)
            if len(members) >= GROUP_MIN:
                zone = nearest_zone(loc, data.package.zones).name
                app = [
                    t
                    for t in members
                    if ev.motion(data, t, minute).get("trend_son_30dk") == "yaklaşıyor"
                ]
                groups.append(
                    {
                        "saat": format_hhmm(from_minutes(minute)),
                        "dakika": minute,
                        "bolge": zone,
                        "araclar": members,
                        "usse_yaklasan": app,
                        "usse_en_yakin_m": min(
                            ev.motion(data, t, minute)["usse_mesafe_m"] for t in members
                        ),
                    }
                )
                break
    return groups


def sleepers(data: ev.Data, zone: str, after_minute: int) -> list[dict[str, Any]]:
    """Bölgede kaydın başından beri en az 30 dk bekleyip `after_minute`'tan sonra kalkan araçlar."""
    out = []
    for tid, pts in data.tracks.items():
        if nearest_zone(pts[0].location, data.package.zones).name != zone:
            continue
        for a, b in zip(pts, pts[1:], strict=False):
            if distance_m(a.location, b.location) > 100:
                waited = to_minutes(a.time) - to_minutes(pts[0].time)
                if waited >= SLEEP_MIN and to_minutes(b.time) > after_minute:
                    mv = ev.motion(data, tid, to_minutes(pts[-1].time))
                    out.append(
                        {
                            "iz": tid,
                            "tip": ev.track_labels(data).get(tid, "bilinmiyor"),
                            "kalkis": format_hhmm(b.time),
                            "bekleme_dk": waited,
                            "cekimde_trend": mv["trend_son_30dk"],
                            "cekimde_usse_m": mv["usse_mesafe_m"],
                        }
                    )
                break
    return out


def add_context(data: ev.Data, d: dict[str, Any]) -> dict[str, Any]:
    """Bağlam raporunun kanıt dosyasına gün düzeyindeki sinyalleri ekler."""
    text = d["metin"]
    hh, mm = d["rapor_saati"].split(":")
    minute = int(hh) * 60 + int(mm)
    out = dict(d)
    if "Lojistik konvoyu" in text or "tatbikat" in text:
        near = [g for g in heavy_groups(data) if abs(g["dakika"] - minute) <= CONVOY_WINDOW_MIN]
        out["baglam"] = {
            "tur": "konvoy/tatbikat duyurusu",
            "ayni_metin_gun_icinde": max(1, sum(r.text == text for r in data.package.reports)),
            "rapor_saatine_yakin_birlikte_hareket_eden_agir_arac_gruplari": [
                {k: v for k, v in g.items() if k != "dakika"} for g in near
            ],
            "not": "duyuruda konum, rota, araç sayısı ya da tip yok; hiçbir araca bağlanamaz",
        }
    elif "Dun gece" in text and d.get("bolge"):
        zones_with = {
            z.name
            for r in data.package.reports
            if "Dun gece" in r.text
            for z in data.package.zones
            if z.name in r.text
        }
        out["baglam"] = {
            "tur": "gece hareketliliği ihbarı",
            "ayni_ihbar_olan_bolge_sayisi": f"{len(zones_with)}/{len(data.package.zones)}",
            "bolgede_bekleyip_rapordan_sonra_kalkan_araclar": sleepers(data, d["bolge"], minute),
        }
    elif "telsiz" in text and d.get("bolge"):
        out["baglam"] = {
            "tur": "telsiz kopukluğu",
            "not": "aynı saatte bölgedeki hareketlilik bolge_rapor_saatinde alanında",
        }
    return out
