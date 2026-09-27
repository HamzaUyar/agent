"""Rapor doğrulama (app/reports_v2): politika, kurallar, bağlam ve değerlendirme akışı.

Ölçüm (eval/report_gold.json, 137 gerçek rapor): 35 yalanın 34'ü, 15 tehlikeli güvencenin
hepsi yakalanıyor. Bu testler davranışın kurallarını kilitler; LLM sahte sağlayıcıyla verilir.
"""

from datetime import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.llm.client import LLMRouter, load_model_config
from app.reports_v2 import rules
from app.reports_v2.stage import combine
from app.reports_v2.verdict import ReportVerdict
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import Detection, FieldReport, ImageMeta, ReportSource, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
T0122_AT_1410 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0122" and p.time == time(14, 10)
)


def claim(**overrides: Any) -> ReportClaim:
    base: dict[str, Any] = {
        "location_type": "coordinate",
        "lat": T0122_AT_1410.lat,
        "lon": T0122_AT_1410.lon,
        "zone": None,
        "vehicle_type": None,
        "vehicle_count": 1,
        "color": None,
        "behavior": None,
        "claim_type": "observation",
        "time_reference": None,
        "is_verifiable": True,
    }
    return ReportClaim.model_validate(base | overrides)


def verdict(v: str, harm: str = "none", **extra: Any) -> ReportVerdict:
    return ReportVerdict.model_validate(
        {
            "verdict": v,
            "harm": harm,
            "dangerous_reassurance": False,
            "checks": [],
            "reasoning": "gerekçe",
            **extra,
        }
    )


def moving(trend: str, *, to_base_m: int = 1800, still: int = 0) -> dict[str, Any]:
    return {
        "trend_son_30dk": trend,
        "usse_mesafe_m": to_base_m,
        "usse_mesafe_30dk_once_m": to_base_m + 3000,
        "usse_mesafe_60dk_once_m": to_base_m + 3000,
        "ayni_yerde_dk": still,
        "kayit_baslangici": "08:30",
        "kayitta_usse_en_yakin_m": to_base_m,
    }


def point_dossier(
    text: str, contacts: list[dict[str, Any]], *, quality: str = "net", around: int = 1
) -> dict[str, Any]:
    heavy = sum(c.get("tespit_tipi") in ("truck", "bus") for c in contacts)
    return {
        "rapor_id": 1,
        "rapor_saati": "13:00",
        "kaynak": "resmi",
        "metin": text,
        "konum_turu": "koordinat",
        "koordinat_ondalik": 5,
        "gorsel": {"id": "img_x", "cekim_saati": "14:10", "kalite": {"not": quality}},
        "noktadaki_temaslar_cekim_aninda": contacts,
        "nokta_cevresi_75m": {"yaricap_m": 30, "arac_sayisi": around, "agir_arac_sayisi": heavy},
        "en_yakin_arac_m": contacts[0]["noktaya_uzaklik_m"] if contacts else 90.0,
    }


def truck_at_point(trend: str = "yaklaşıyor", still: int = 0) -> dict[str, Any]:
    return {
        "iz": "T0122",
        "noktaya_uzaklik_m": 0.4,
        "tespit_tipi": "truck",
        "tespit_guveni": 0.9,
        "hareket_cekim_aninda": moving(trend, still=still),
    }


# --- politika (kod) ---------------------------------------------------------------------


def test_identity_claim_is_never_consistent() -> None:
    final, _ = combine(verdict("unverifiable"), verdict("consistent"), "... dost devriye unsurudur")

    assert final.verdict == "unverifiable"


def test_rules_and_llm_disagreeing_on_a_contradiction_needs_review() -> None:
    final, review = combine(verdict("contradicts"), verdict("consistent"), "1 kamyon goruldu")

    assert (final.verdict, review) == ("consistent", True)


def test_contradicted_reassurance_is_dangerous_even_if_the_llm_did_not_flag_it() -> None:
    final, review = combine(
        verdict("contradicts", "lowers_risk"),
        verdict("contradicts", "lowers_risk"),
        "hareketleri olagan",
    )

    assert (final.dangerous_reassurance, review) == (True, False)


def test_without_an_llm_the_rules_decide() -> None:
    final, review = combine(
        verdict("contradicts", context_flags=["olası örtü hikâyesi"]), None, "x"
    )

    assert (final.verdict, final.context_flags, review) == (
        "contradicts",
        ["olası örtü hikâyesi"],
        False,
    )


# --- kurallar ---------------------------------------------------------------------------


def test_olagan_about_an_approaching_vehicle_is_a_dangerous_contradiction() -> None:
    d = point_dossier("1 agir arac, hareketleri olagan", [truck_at_point("yaklaşıyor")])

    v = rules.judge(d, claim(vehicle_type="heavy", behavior="normal_traffic"))

    assert (v.verdict, v.harm, v.dangerous_reassurance) == ("contradicts", "lowers_risk", True)


def test_nothing_at_a_precise_point_in_a_clear_image_contradicts() -> None:
    far = {"iz": "T0041", "noktaya_uzaklik_m": 53.0, "tespit_tipi": "car", "tespit_guveni": 0.8}
    d = point_dossier("yuklu bir kamyon park halinde", [far], around=0)

    assert rules.judge(d, claim(vehicle_type="truck", cargo="loaded")).verdict == "contradicts"


def test_nothing_at_the_point_in_a_blurry_image_is_only_unverifiable() -> None:
    d = point_dossier("yuklu bir kamyon park halinde", [], quality="bulanık", around=0)

    assert rules.judge(d, claim(vehicle_type="truck")).verdict == "unverifiable"


def test_inflated_count_contradicts() -> None:
    d = point_dossier("5 kamyonun durdugu bildirildi", [truck_at_point("duruyor", 60)], around=1)

    v = rules.judge(d, claim(vehicle_type="truck", vehicle_count=5, behavior="stationary"))

    assert v.verdict == "contradicts"
    assert any(c.attribute == "sayı" and c.status == "mismatch" for c in v.checks)


def test_no_heavy_vehicles_claim_contradicts_when_a_truck_moves_in_the_zone() -> None:
    d = {
        "rapor_id": 1,
        "rapor_saati": "09:35",
        "kaynak": "resmi",
        "metin": "Kuzeydogu Kavsagi bolgesinde agir arac hareketi yok",
        "konum_turu": "bölge",
        "bolge": "Kuzeydogu Kavsagi",
        "bolge_rapor_saatinde": {
            "usse_yaklasan": [],
            "hareket_eden_agir_arac": [{"iz": "T0035", "tip": "truck"}],
        },
    }
    zone_claim = claim(location_type="zone", zone="Kuzeydogu Kavsagi", vehicle_type="light")

    v = rules.judge(d, zone_claim)

    assert (v.verdict, v.dangerous_reassurance) == ("contradicts", True)


def test_convoy_notice_near_an_approaching_heavy_group_is_flagged_as_cover() -> None:
    d = {
        "rapor_id": 1,
        "rapor_saati": "12:15",
        "kaynak": "üçüncü taraf",
        "metin": "Lojistik konvoyu yakit ikmali icin planlanan saatte yola cikacak.",
        "konum_turu": "yok",
        "baglam": {
            "tur": "konvoy/tatbikat duyurusu",
            "rapor_saatine_yakin_birlikte_hareket_eden_agir_arac_gruplari": [
                {
                    "saat": "12:10",
                    "bolge": "Kuzey Yolu",
                    "araclar": ["T0001", "T0028", "T0135"],
                    "usse_yaklasan": ["T0001", "T0028", "T0135"],
                }
            ],
        },
    }
    notice = claim(location_type="none", lat=None, lon=None, claim_type="friendly_claim")

    v = rules.judge(d, notice)

    assert (v.verdict, v.harm, v.context_flags) == (
        "unverifiable",
        "lowers_risk",
        ["olası örtü hikâyesi"],
    )


# --- değerlendirme akışı ------------------------------------------------------------------


class FakeDetector:
    version = "test"

    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK] if image.image_id == "img_000860" else []


class ReportLLM:
    """Yalnızca rapor doğrulama çağrılarına cevap verir; karar çağrıları başarısız olur."""

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int,
        extra_body: object = None,
    ) -> BaseModel:
        self.calls += 1
        return schema.model_validate(self.reply)


def service(claims: list[ClaimRecord], provider: ReportLLM | None = None) -> EvaluationService:
    router = None
    if provider is not None:
        config = load_model_config()
        providers: dict[str, Any] = {
            name: provider for name in {m.provider for m in config.models.values()}
        }
        router = LLMRouter(config, providers)
    repo = InMemoryRepository(PACKAGE, claims=claims)
    return EvaluationService(repo, FakeDetector(), router=router, images_dir=FIXTURE / "images")


OLAGAN = ClaimRecord(
    4,
    FieldReport(time(13, 30), ReportSource.OFFICIAL, "1 agir arac, hareketleri olagan"),
    claim(vehicle_type="heavy", behavior="normal_traffic"),
)


def test_reports_do_not_change_the_level_and_are_marked_dangerous_without_an_llm() -> None:
    brief = service([OLAGAN]).run("img_000860")

    [f] = brief.report_findings
    assert (f.verdict, f.effect, f.dangerous_reassurance, f.needs_review) == (
        "contradicts",
        "none",
        True,
        False,
    )
    t0122 = next(c for c in brief.contacts if c.track_id == "T0122")
    assert t0122.final_level == t0122.base_level == "critical"
    assert "rapor tespitle çelişiyor; tespit esas alındı" in t0122.level_reasons


def test_disagreement_goes_to_the_operator_and_a_dangerous_reassurance_stays_flagged() -> None:
    llm = ReportLLM(
        {
            "verdict": "consistent",
            "harm": "none",
            "dangerous_reassurance": False,
            "checks": [],
            "reasoning": "LLM uyumlu dedi",
        }
    )

    brief = service([OLAGAN], llm).run("img_000860")

    [f] = brief.report_findings
    # LLM "tutarlı" dedi; kurallar "olağan"ın yaklaşan kamyon için tehlikeli güvence olduğunu
    # buldu: tehlikeli güvence kazanır, ayrışma operatöre gider.
    assert (f.detail_verdict, f.rule_verdict, f.needs_review, f.dangerous_reassurance) == (
        "contradicts",
        "contradicts",
        True,
        True,
    )
    assert "operatör incelemeli" in f.reasoning
    assert llm.calls >= 1


def test_a_claim_whose_point_is_outside_the_frame_is_not_evaluated() -> None:
    elsewhere = ClaimRecord(
        5,
        FieldReport(time(13, 30), ReportSource.OFFICIAL, "1 kamyon"),
        claim(lat=39.99, lon=32.99, vehicle_type="truck"),
    )

    assert service([elsewhere]).run("img_000860").report_findings == []


def test_a_dangerous_reassurance_is_at_least_a_contradiction() -> None:
    """Kurallar tehlikeli güvence buldu, LLM "kısmen" dedi: nihai karar çelişkili."""
    rule = verdict("contradicts", "lowers_risk", dangerous_reassurance=True)

    final, _ = combine(rule, verdict("partial", "lowers_risk"), "hareketleri olagan")

    assert (final.verdict, final.dangerous_reassurance) == ("contradicts", True)


# --- Supabase deposu --------------------------------------------------------------------


class FakeConn:
    """`report_verifications` için yeterli kadar psycopg bağlantısı."""

    def __init__(self, table: dict[str, dict[str, Any]], log: list[str]) -> None:
        self.table, self.log = table, log

    def __enter__(self) -> "FakeConn":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "FakeConn":
        self.log.append(sql.split()[0])
        if sql.lstrip().startswith("insert"):
            key, out, model = params
            self.table.setdefault(key, {"out": out.obj, "model": model})
        elif sql.lstrip().startswith("update"):
            self.table[params[-1]]["verdict"] = params[2]
        self._rows = [
            (k, r["out"], r["model"], r.get("verdict"), None, None, [], None, None, None)
            for k, r in self.table.items()
        ]
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


def test_supabase_store_reads_once_asks_the_llm_only_on_a_miss_and_writes_changes() -> None:
    from app.db.models import ReportVerificationStore

    table: dict[str, dict[str, Any]] = {}
    log: list[str] = []
    store = ReportVerificationStore(lambda: FakeConn(table, log))  # type: ignore[arg-type,return-value]
    asked: list[int] = []

    def ask() -> dict[str, Any]:
        asked.append(1)
        return {"model": "glm/test", "out": {"verdict": "contradicts"}}

    first = store.get_or(["a"], ask)
    again = store.get_or(["a"], ask)
    key = next(iter(table))
    final = verdict("contradicts").model_dump()
    kwargs: dict[str, Any] = {"claim_id": 1, "image_id": "img", "final": final, "dossier": {}}
    store.annotate(key, rule_verdict="contradicts", needs_review=False, **kwargs)
    store.annotate(key, rule_verdict="contradicts", needs_review=False, **kwargs)

    assert first == again == {"model": "glm/test", "out": {"verdict": "contradicts"}}
    assert len(asked) == 1  # ikinci istek önbellekten
    assert log == ["select", "insert", "update"]  # değişmeyen sonuç yeniden yazılmaz
    assert store.size() == 1
