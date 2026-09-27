"""Kurallar: kanıt dosyası üzerinde deterministik kontroller (LLM yok).

Rapor doğrulamada LLM kararının ikinci görüşüdür; ikisi çelişki konusunda ayrışırsa rapor
operatör incelemesine düşer. Kapsadığı yalan türleri: "olağan" ve
"transit" hareket iddiaları, bölge düzeyindeki "ağır araç yok / trafik normal" iddiaları,
noktada hiç araç olmaması ve sayı şişirme.
"""

from typing import Any

from app.reports_v2.verdict import Check, CheckStatus, Harm, ReportVerdict, VerdictLabel
from app.schemas.claims import ReportClaim

HEAVY = {"truck", "bus"}
LIGHT = {"car", "van"}


def _type_status(claimed: str | None, label: str | None) -> CheckStatus:
    if claimed in (None, "unknown"):
        return "not_claimed"
    if label is None or label == "tespit edilemedi":
        return "unverified"
    ok = {
        "truck": {"truck"},
        "bus": {"bus"},
        "heavy": HEAVY,
        "car": {"car"},
        "van": {"van"},
        "light": LIGHT,
    }[claimed]
    return "match" if label in ok else "mismatch"


def _behavior_status(
    behavior: str | None, mv: dict[str, Any] | None, time_ref: str | None
) -> tuple[CheckStatus, str]:
    if behavior in (None, "unknown"):
        return "not_claimed", ""
    if not mv or mv.get("bilinmiyor"):
        return "unverified", "hareket kaydı yok"
    trend = mv["trend_son_30dk"]
    still = mv["ayni_yerde_dk"]
    desc = f"çekim anında {trend}, üsse {mv['usse_mesafe_m']} m, {still} dk aynı yerde"
    if behavior == "stationary":
        need = 60 if time_ref and "saat" in time_ref else 30 if time_ref else 10
        if trend == "duruyor" or still >= 10:
            since_start = still >= 0 and mv["kayit_baslangici"] and still + 5 >= 120
            return ("match" if still >= need or since_start else "mismatch"), desc
        return "mismatch", desc
    if behavior == "approaching":
        return ("match" if trend == "yaklaşıyor" else "mismatch"), desc
    if behavior == "receding":
        return ("match" if trend == "uzaklaşıyor" else "mismatch"), desc
    if behavior in ("transit", "normal_traffic"):
        return ("mismatch" if trend == "yaklaşıyor" else "match"), desc
    if behavior == "moving":
        return ("mismatch" if trend == "duruyor" else "match"), desc
    return "not_claimed", ""


LOWERING_BEHAVIORS = {"normal_traffic", "receding", "transit"}


def judge(d: dict[str, Any], claim: ReportClaim) -> ReportVerdict:
    text = d["metin"]
    ctype = claim.claim_type
    checks: list[Check] = []

    def out(v: VerdictLabel, harm: Harm, why: str, danger: bool = False) -> ReportVerdict:
        return ReportVerdict(
            verdict=v, harm=harm, dangerous_reassurance=danger, checks=checks, reasoning=why
        )

    if ctype == "irrelevant":
        return out("irrelevant", "none", "tespitle ilişkisi olmayan bilgi")
    ctx = d.get("baglam") or {}
    if ctx.get("tur") == "konvoy/tatbikat duyurusu":
        v = out(
            "unverifiable",
            "lowers_risk",
            "kimlik ve rota vermeyen dost duyurusu; hiçbir araca bağlanamaz",
        )
        groups = ctx["rapor_saatine_yakin_birlikte_hareket_eden_agir_arac_gruplari"]
        if any(g["usse_yaklasan"] for g in groups):
            g = next(g for g in groups if g["usse_yaklasan"])
            v.context_flags.append("olası örtü hikâyesi")
            v.reasoning += (
                f"; {g['saat']}'te {g['bolge']}'nda {len(g['araclar'])} ağır araç "
                "birlikte üsse yaklaşıyor"
            )
        return v
    if "telsiz" in text:
        v = out("unverifiable", "none", "iletişim durumu veriyle doğrulanamaz")
        z = d.get("bolge_rapor_saatinde") or {}
        if z.get("hareket_eden_agir_arac") or len(z.get("usse_yaklasan", [])) >= 3:
            v.context_flags.append("telsiz kopukluğu + ağır araç hareketi")
        return v
    if ctx.get("tur") == "gece hareketliliği ihbarı":
        v = out(
            "unverifiable",
            "none",
            f"dün geceye ait ihbar ({ctx['ayni_ihbar_olan_bolge_sayisi']} bölgede)",
        )
        if any(
            x["cekimde_trend"] == "yaklaşıyor"
            and (x.get("tip") in ("truck", "bus") or x["cekimde_usse_m"] < 3000)
            for x in ctx["bolgede_bekleyip_rapordan_sonra_kalkan_araclar"]
        ):
            v.context_flags.append("gece ihbarı bölgesinden kalkış")
        return v
    if ctype == "rumor":
        return out("unverifiable", "none", "doğrulanmamış ihbar")
    if d["konum_turu"] == "yok":
        harm: Harm = "lowers_risk" if ctype == "friendly_claim" else "none"
        return out("unverifiable", harm, "konum ve saat vermeyen genel bilgi")

    if d["konum_turu"] == "bölge":
        z = d["bolge_rapor_saatinde"]
        heavy = z["hareket_eden_agir_arac"]
        n_app = len(z["usse_yaklasan"])
        if claim.vehicle_type == "light":
            if heavy:
                ids = ", ".join(h["iz"] for h in heavy)
                checks.append(
                    Check(
                        attribute="bölge",
                        status="mismatch",
                        evidence=f"hareket eden ağır araç: {ids}",
                    )
                )
                return out(
                    "contradicts",
                    "lowers_risk",
                    f"'ağır araç yok' dendi ama bölgede ağır araç hareket ediyor ({ids})",
                    True,
                )
            checks.append(
                Check(attribute="bölge", status="match", evidence="hareket eden ağır araç yok")
            )
            return out("consistent", "none", "bölgede hareket eden ağır araç yok")
        if claim.behavior == "normal_traffic":
            ev = f"{n_app} araç üsse yaklaşıyor, {len(heavy)} ağır araç hareket ediyor"
            if n_app >= 5 or heavy:
                checks.append(Check(attribute="bölge", status="mismatch", evidence=ev))
                return out("contradicts", "lowers_risk", f"'olağan' dendi ama {ev}", True)
            if n_app >= 3:
                checks.append(Check(attribute="bölge", status="mismatch", evidence=ev))
                return out("partial", "lowers_risk", f"'olağan' tartışmalı: {ev}")
            checks.append(Check(attribute="bölge", status="match", evidence=ev))
            return out("consistent", "none", ev)
        return out("unverifiable", "none", "bölge düzeyinde, karşılaştırılacak özellik yok")

    # Koordinatlı rapor
    if not d.get("gorsel"):
        return out("unverifiable", "none", "koordinat hiçbir görüntünün içinde değil")
    near = d["noktadaki_temaslar_cekim_aninda"]
    bind = 15.0 if d["koordinat_ondalik"] >= 5 else 35.0
    linked = next((c for c in near if c["noktaya_uzaklik_m"] <= bind), None)
    quality = d["gorsel"]["kalite"]["not"]
    raises: Harm = "raises_risk"
    claim_harm: Harm = (
        "lowers_risk"
        if ctype == "friendly_claim" or claim.behavior in LOWERING_BEHAVIORS
        else raises
        if (
            claim.vehicle_type in ("truck", "heavy", "bus")
            or (claim.vehicle_count or 0) >= 2
            or ctype == "threat_warning"
        )
        else "none"
    )
    if linked is None:
        checks.append(
            Check(
                attribute="varlık",
                status="mismatch",
                evidence=f"en yakın araç {d['en_yakin_arac_m']} m",
            )
        )
        if quality == "net":
            return out(
                "contradicts", claim_harm, f"noktada araç yok (en yakın {d['en_yakin_arac_m']} m)"
            )
        return out("unverifiable", claim_harm, f"noktada araç görülmüyor ama görüntü {quality}")
    checks.append(
        Check(
            attribute="varlık",
            status="match",
            evidence=f"{linked['iz']} noktaya {linked['noktaya_uzaklik_m']} m",
        )
    )
    ts = _type_status(claim.vehicle_type, linked["tespit_tipi"])
    around = d["nokta_cevresi_75m"]
    count = claim.vehicle_count or 0
    if count >= 2:
        heavy_n = (
            around["agir_arac_sayisi"]
            if claim.vehicle_type in ("truck", "heavy", "bus")
            else around["arac_sayisi"]
        )
        cs = "match" if heavy_n >= count else ("mismatch" if heavy_n < count / 2 else "partial")
        checks.append(
            Check(
                attribute="sayı",
                status="match" if cs == "match" else "mismatch",
                evidence=(
                    f"{around.get('yaricap_m', 75)} m içinde {heavy_n} uygun araç, iddia {count}"
                ),
            )
        )
        if ts == "mismatch" and heavy_n > 0:
            ts = "not_claimed"  # tip sayım içinde değerlendirildi
    else:
        cs = "not_claimed"
    if ts != "not_claimed":
        checks.append(
            Check(attribute="tip", status=ts, evidence=f"noktadaki tespit: {linked['tespit_tipi']}")
        )
    mv = linked.get("hareket_cekim_aninda")
    bs, bdesc = _behavior_status(claim.behavior, mv, claim.time_reference)
    if bs != "not_claimed":
        checks.append(Check(attribute="hareket", status=bs, evidence=bdesc))
    if "yogun" in text:
        n = around["arac_sayisi"]
        checks.append(
            Check(
                attribute="sayı",
                status="match" if n >= 8 else "mismatch",
                evidence=f"75 m içinde {n} araç",
            )
        )
        return out(
            "consistent" if n >= 8 else "contradicts", "raises_risk", f"çevrede {n} araç, olağan 4"
        )

    mism = [c.attribute for c in checks if c.status == "mismatch"]
    danger = claim_harm == "lowers_risk" and "hareket" in mism
    if ctype == "friendly_claim":
        if mism:
            return out(
                "contradicts", "lowers_risk", f"dost iddiası: {', '.join(mism)} uyuşmuyor", danger
            )
        return out("unverifiable", "lowers_risk", "tip ve hareket tutuyor, kimlik doğrulanamaz")
    if cs == "partial" and not [m for m in mism if m != "sayı"]:
        return out("partial", claim_harm, "sayı kısmen tutuyor")
    if mism:
        return out("contradicts", claim_harm, f"{', '.join(mism)} uyuşmuyor", danger)
    if ts == "unverified":
        return out("partial", claim_harm, "araç var, tipi doğrulanamadı")
    return out("consistent", "none", "iddia tespit ve hareketle uyuşuyor")
