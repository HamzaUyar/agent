"""Değerlendirme servisi: LLM'in dikkat maddeleri, kodun doğrulaması ve brief (ADR-0002).

LLM sahte sağlayıcıdan cevap verir. Temas kimliği şemada enum; her neden veriyle
doğrulanır; ±1 kademe ayarı yalnızca doğrulanmış bir nedenle kabul edilir. "Değerlendirme"
bölümünü kod yazar; LLM'in özeti sayı, kimlik, bölge adı ya da İngilizce terim içerirse
atılır. Yedek modele geçiş, zaman sınırı ve otomatik özet gerçek kodla çalışır.
"""

import time as clock
from datetime import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.agent.decision import DecisionDraft, apply_attention, contact_labels, draft_schema
from app.agent.service import EvaluationService
from app.core.rules import load_rules
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.llm.client import LLMRouter, load_model_config
from app.schemas.api import AttentionFinding, Brief, ContactFinding, LatLon
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import Detection, FieldReport, ImageMeta, ReportSource, VehicleClass

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
# Track'i olmayan güçlü tespit: kayıt dışı temas.
PARKED = Detection(label=VehicleClass.CAR, confidence=0.9, x=100, y=100, w=20, h=20)
CONFIG = load_model_config()
CHAIN = [CONFIG.models[name] for name in CONFIG.tasks["reasoning"]]
PRIMARY, FALLBACK = CHAIN[0], CHAIN[1]

# img_000860, 14:10: T0122 (truck, üsse yaklaşıyor, KRİTİK); T0032 (kaçırılmış temas,
# 12:10'dan beri üsse 1,6 km'de duruyor, ORTA). T0032, canlı denemedeki T0020 gibi
# duran bir araç: "yaklasma" veriyle doğrulanamaz.
T0032_AT_1235 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0032" and p.time == time(12, 35)
)
CONSISTENT_CLAIM = ClaimRecord(
    claim_id=2,
    report=FieldReport(time(12, 35), ReportSource.OFFICIAL, "1 agir arac, hareketleri olagan"),
    claim=ReportClaim(
        location_type="coordinate",
        lat=T0032_AT_1235.lat,
        lon=T0032_AT_1235.lon,
        zone=None,
        vehicle_type=None,
        vehicle_count=1,
        color=None,
        behavior="normal_traffic",
        claim_type="observation",
        time_reference=None,
        is_verifiable=True,
    ),
)
THREAT_ABOUT_T0032 = ClaimRecord(
    claim_id=9,
    report=FieldReport(time(13, 0), ReportSource.OFFICIAL, "burada kamyon var"),
    claim=CONSISTENT_CLAIM.claim.model_copy(update={"claim_type": "threat_warning"}),
)
# T0032 duruyor; "yaklaşıyor" diyen rapor hareket verisiyle çelişir.
CONTRADICTS_T0032 = ClaimRecord(
    claim_id=5,
    report=FieldReport(time(13, 30), ReportSource.THIRD_PARTY, "arac yaklasiyor"),
    claim=CONSISTENT_CLAIM.claim.model_copy(update={"behavior": "approaching"}),
)
T0122_AT_1410 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0122" and p.time == time(14, 10)
)
ABOUT_T0122 = ClaimRecord(
    claim_id=3,
    report=FieldReport(time(14, 0), ReportSource.OFFICIAL, "tehdit uyarisi"),
    claim=CONSISTENT_CLAIM.claim.model_copy(
        update={"lat": T0122_AT_1410.lat, "lon": T0122_AT_1410.lon, "claim_type": "threat_warning"}
    ),
)

SUMMARY = "Ağır araç üsse yaklaşıyor; duran temas izlenmeli."


class FakeDetector:
    version = "test"

    def __init__(self, *extra: Detection) -> None:
        self.extra = list(extra)

    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK, *self.extra] if image.image_id == "img_000860" else []


class FakeProvider:
    def __init__(self, reply: Any = None, *, delay_s: float = 0.0, available: bool = True) -> None:
        self.reply = reply
        self.delay_s = delay_s
        self.available = available
        self.calls = 0
        self.schemas: list[type[BaseModel]] = []

    def is_available(self) -> bool:
        return self.available

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
        self.schemas.append(schema)
        if self.delay_s:
            clock.sleep(self.delay_s)
        if isinstance(self.reply, Exception):
            raise self.reply
        return schema.model_validate(self.reply)


def item(
    track_id: str, neden: str, dayanak: list[Any] | None = None, seviye: str | None = None
) -> dict[str, Any]:
    return {
        "track_id": track_id,
        "neden": neden,
        "dayanak": dayanak or [],
        "seviye_onerisi": seviye,
    }


def draft(items: list[dict[str, Any]], ozet: str = SUMMARY) -> dict[str, Any]:
    return {"dikkat": items, "ozet": ozet}


def run(
    primary: FakeProvider | None,
    fallback: FakeProvider | None = None,
    *,
    claims: list[ClaimRecord] | None = None,
    timeout_s: float | None = None,
    detector: FakeDetector | None = None,
) -> Brief:
    router = None
    if primary is not None:
        providers = {e.provider: FakeProvider(available=False) for e in CHAIN}
        providers[PRIMARY.provider] = primary
        providers[FALLBACK.provider] = fallback or FakeProvider(available=False)
        router = LLMRouter(CONFIG, providers)
    service = EvaluationService(
        InMemoryRepository(PACKAGE, claims=claims or []),
        detector or FakeDetector(),
        router=router,
        brief_timeout_s=timeout_s,
    )
    return service.run("img_000860")


def contact(brief: Brief, track_id: str) -> ContactFinding:
    [c] = [c for c in brief.contacts if c.track_id == track_id]
    return c


def level_of(brief: Brief, track_id: str) -> tuple[str, str]:
    c = contact(brief, track_id)
    return c.base_level, c.final_level


def attention(brief: Brief, contact_id: str) -> list[AttentionFinding]:
    return [a for a in brief.attention if a.contact == contact_id]


# --- şema ----------------------------------------------------------------------------


def test_track_id_is_an_enum_of_the_contacts_in_this_frame() -> None:
    primary = FakeProvider(draft([]))
    run(primary, detector=FakeDetector(PARKED))

    [schema] = primary.schemas
    [enum] = [
        prop["enum"]
        for definition in schema.model_json_schema()["$defs"].values()
        for name, prop in definition.get("properties", {}).items()
        if name == "track_id"
    ]
    assert enum == ["T0122", "kayit_disi_1", "T0032"]
    with pytest.raises(ValidationError):
        schema.model_validate(draft([item("T0012", "yaklasma")]))


def test_schema_is_built_per_call_from_the_contact_labels() -> None:
    parked = ContactFinding(
        kind="unregistered",
        label="car",
        effective_label="car",
        confidence=0.9,
        bbox=(1, 2, 3, 4),
        location=LatLon(lat=39.9, lon=32.8),
        distance_to_base_m=900,
        base_level="low",
        final_level="low",
        certainty="likely",
    )
    labels = contact_labels([parked, parked.model_copy(update={"track_id": "T0001"}), parked])

    assert labels == ["kayit_disi_1", "T0001", "kayit_disi_2"]
    draft_schema(labels).model_validate(draft([item("kayit_disi_2", "dikkat_gerekmiyor")]))
    with pytest.raises(ValidationError):
        draft_schema(["T0001"]).model_validate(draft([item("kayit_disi_2", "dikkat_gerekmiyor")]))


def test_without_contacts_the_attention_list_must_be_empty() -> None:
    schema = draft_schema([])

    schema.model_validate(draft([]))
    with pytest.raises(ValidationError):
        schema.model_validate(draft([item("T0001", "yaklasma")]))


# --- nedenlerin veriyle doğrulanması ------------------------------------------------


def test_approach_claimed_for_a_standing_contact_is_rejected_with_its_level_change() -> None:
    """Canlı denemede T0020 duruyordu ama LLM "yaklaştı" deyip yükseltti; kabul edilmişti."""
    brief = run(FakeProvider(draft([item("T0032", "yaklasma", ["trend"], "high")])))

    assert level_of(brief, "T0032") == ("medium", "medium")
    [a] = attention(brief, "T0032")
    assert a.accepted is False
    assert a.rejection is not None and "yaklaşmıyor" in a.rejection
    assert contact(brief, "T0032").adjustment_rejected == a.rejection
    assert "T0032" not in brief.text.split("Değerlendirme:")[1].split("\n")[0]


def test_verified_reason_allows_a_one_step_raise_with_a_code_written_reason() -> None:
    # T0032'nin ORTA'sı duraklamadan geliyor; tipinin bilinmemesi kuralların saymadığı bir neden.
    brief = run(FakeProvider(draft([item("T0032", "kacirilmis_temas", ["kind"], "high")])))

    assert level_of(brief, "T0032") == ("medium", "high")
    [a] = attention(brief, "T0032")
    assert (a.accepted, a.level_accepted, a.rejection) == (True, True, None)
    assert a.text == "karede ama tespit edilmedi (kaçırılmış temas), tipi bilinmiyor"
    assert contact(brief, "T0032").adjustment_reason == a.text
    assert brief.is_fallback is False
    assert brief.model == f"{PRIMARY.provider}/{PRIMARY.model_id}"


def test_assessment_is_written_by_code_from_accepted_items_and_the_clean_summary() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    item("T0122", "yaklasma", ["trend", "distance_to_base_30min_ago_km"]),
                    item("T0032", "kacirilmis_temas", ["kind"]),
                    item("T0032", "dolasma", ["base_distance_range_km"]),
                ]
            )
        )
    )

    lines = brief.text.splitlines()
    assert lines[0].startswith("img_000860 · Dogu Yolu · 14:10 · Risk: KRİTİK")
    assert "otomatik özet" not in lines[0]
    assert lines[1] == (
        f"Değerlendirme: {SUMMARY} "
        "T0122: üsse yaklaşıyor, 30 dk önce 5,5 km, şimdi 1,6 km, son 30 dk 2,1 m/s. "
        "T0032: karede ama tespit edilmedi (kaçırılmış temas), tipi bilinmiyor."
    )
    [circling] = [a for a in attention(brief, "T0032") if a.reason == "dolasma"]
    assert circling.accepted is False and circling.rejection is not None
    assert lines[-1] == f"Önerilen eylem: {brief.recommended_action}"


def test_no_attention_needed_is_rejected_when_the_data_shows_a_reason() -> None:
    brief = run(FakeProvider(draft([item("T0122", "dikkat_gerekmiyor")])))

    [a] = attention(brief, "T0122")
    assert a.accepted is False
    assert a.rejection is not None and "yaklaşma" in a.rejection


def test_threat_warning_needs_a_consistent_threat_claim_linked_to_that_contact() -> None:
    brief = run(
        FakeProvider(
            draft([item("T0032", "tehdit_uyarisi", [9]), item("T0122", "tehdit_uyarisi")])
        ),
        claims=[THREAT_ABOUT_T0032],
    )

    [t0032] = attention(brief, "T0032")
    assert t0032.accepted is True
    assert t0032.text == "13:00 tehdit uyarısı bu temasla tutarlı"
    [t0122] = attention(brief, "T0122")
    assert t0122.accepted is False


def test_report_contradiction_needs_a_contradicting_claim_linked_to_that_contact() -> None:
    brief = run(
        FakeProvider(
            draft([item("T0032", "rapor_celiskisi", [5]), item("T0122", "rapor_celiskisi")])
        ),
        claims=[CONTRADICTS_T0032],
    )

    assert [f.verdict for f in brief.report_findings if f.claim_id == 5] == ["contradicts"]
    [t0032] = attention(brief, "T0032")
    assert t0032.accepted is True
    assert t0032.text == "13:30 raporu tespitle çelişiyor; tespit esas alındı"
    assert attention(brief, "T0122")[0].accepted is False


def test_basis_claims_must_be_linked_to_that_contact() -> None:
    brief = run(
        FakeProvider(draft([item("T0122", "yaklasma", ["trend", 2])])),
        claims=[CONSISTENT_CLAIM],
    )

    [a] = attention(brief, "T0122")
    assert a.accepted is False
    assert a.rejection is not None and "bu temasa bağlı değil" in a.rejection


def test_unregistered_contacts_get_a_code_label_and_no_attention_is_left_out_of_the_text() -> None:
    brief = run(
        FakeProvider(draft([item("kayit_disi_1", "dikkat_gerekmiyor")])),
        detector=FakeDetector(PARKED),
    )

    [a] = attention(brief, "kayit_disi_1")
    assert (a.accepted, a.track_id, a.text) == (True, None, "dikkat gerektiren bir durum yok")
    # Dikkat gerektirmeyen temaslar brief verisinde kalır; değerlendirme metnini doldurmaz.
    assert brief.text.splitlines()[1] == f"Değerlendirme: {SUMMARY}"


def test_items_about_the_same_contact_are_written_as_one_sentence() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    item("T0032", "kacirilmis_temas", ["kind"]),
                    item("T0122", "yaklasma", ["trend"]),
                    item("T0032", "uzun_duraklama", ["stops"]),
                ],
                ozet="",
            )
        ),
        FakeProvider(
            draft(
                [
                    item("T0032", "kacirilmis_temas", ["kind"]),
                    item("T0122", "yaklasma", ["trend"]),
                    item("T0032", "uzun_duraklama", ["stops"]),
                ],
                ozet="Sayı içeren özet: 3 araç.",
            )
        ),
    )

    assert brief.text.splitlines()[1] == (
        "Değerlendirme: T0032: karede ama tespit edilmedi (kaçırılmış temas), tipi bilinmiyor; "
        "üsse 1,6 km'de en az 120 dk'dır duruyor. "
        "T0122: üsse yaklaşıyor, 30 dk önce 5,5 km, şimdi 1,6 km, son 30 dk 2,1 m/s."
    )


# --- seviye ayarı ---------------------------------------------------------------------


def test_jump_of_more_than_one_level_is_rejected() -> None:
    brief = run(FakeProvider(draft([item("T0032", "kacirilmis_temas", ["kind"], "critical")])))

    assert level_of(brief, "T0032") == ("medium", "medium")
    [a] = attention(brief, "T0032")
    assert a.accepted is True  # neden doğru; seviye önerisi reddedildi
    assert a.level_accepted is False
    assert a.rejection is not None and "bir kademe" in a.rejection


def test_a_raising_reason_cannot_lower_and_no_attention_cannot_raise() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    item("T0122", "yaklasma", ["trend"], "high"),
                    item("T0032", "dikkat_gerekmiyor", [2], "high"),
                ]
            )
        ),
        claims=[CONSISTENT_CLAIM],
    )

    assert level_of(brief, "T0122") == ("critical", "critical")
    assert level_of(brief, "T0032") == ("medium", "medium")
    assert all(a.level_accepted is False for a in brief.attention)


def test_lowering_without_evidence_is_rejected() -> None:
    brief = run(FakeProvider(draft([item("T0032", "dikkat_gerekmiyor", [], "low")])))

    assert level_of(brief, "T0032") == ("medium", "medium")
    assert contact(brief, "T0032").adjustment_rejected is not None


def test_lowering_with_a_consistent_claim_about_that_contact_is_accepted() -> None:
    brief = run(
        FakeProvider(draft([item("T0032", "dikkat_gerekmiyor", [2], "low")])),
        claims=[CONSISTENT_CLAIM],
    )

    assert level_of(brief, "T0032") == ("medium", "low")
    [a] = attention(brief, "T0032")
    assert a.text == "dikkat gerektiren bir durum yok; 12:35 resmi raporu doğruluyor"


def test_lowering_citing_a_claim_about_another_contact_is_rejected() -> None:
    brief = run(
        FakeProvider(draft([item("T0122", "dikkat_gerekmiyor", [2], "high")])),
        claims=[CONSISTENT_CLAIM],
    )

    assert level_of(brief, "T0122") == ("critical", "critical")


def test_llm_cannot_lower_a_contact_that_a_report_has_raised() -> None:
    brief = run(
        FakeProvider(draft([item("T0032", "dikkat_gerekmiyor", [2], "medium")])),
        claims=[CONSISTENT_CLAIM, THREAT_ABOUT_T0032],
    )

    assert level_of(brief, "T0032") == ("medium", "high")  # tehdit uyarısı +1; LLM düşüremedi
    rejected = contact(brief, "T0032").adjustment_rejected
    assert rejected is not None and "yükseltti" in rejected


def test_lowering_citing_a_claim_whose_report_time_does_not_match_is_rejected() -> None:
    """İddia T0122'nin çekim anındaki noktasını gösteriyor ama T0122 12:35'te orada değildi."""
    stale = ClaimRecord(
        claim_id=7,
        report=FieldReport(time(12, 35), ReportSource.OFFICIAL, "1 agir arac, hareketleri olagan"),
        claim=CONSISTENT_CLAIM.claim.model_copy(
            update={"lat": T0122_AT_1410.lat, "lon": T0122_AT_1410.lon}
        ),
    )
    # T0122 yaklaşıyor; önce yaklaşma olmayan bir temas gerekir: burada düşürme önerisinin
    # kanıtı saat kontrolünden geçmediği için reddedilir.
    brief = run(
        FakeProvider(draft([item("T0122", "dikkat_gerekmiyor", [7], "high")])), claims=[stale]
    )

    assert level_of(brief, "T0122") == ("critical", "critical")
    rejected = contact(brief, "T0122").adjustment_rejected
    assert rejected is not None and "saat" in rejected


def test_raise_citing_another_contacts_report_is_rejected() -> None:
    brief = run(
        FakeProvider(draft([item("T0032", "uzun_duraklama", ["stops", 3], "high")])),
        claims=[CONSISTENT_CLAIM, ABOUT_T0122],
    )

    assert [f.track_id for f in brief.report_findings if f.claim_id == 3] == ["T0122"]
    assert contact(brief, "T0032").final_level == "medium"
    [a] = attention(brief, "T0032")
    assert a.rejection is not None and "bu temasa bağlı değil" in a.rejection


def test_image_level_and_action_follow_the_final_levels() -> None:
    brief = run(FakeProvider(draft([item("T0032", "kacirilmis_temas", ["kind"], "high")])))

    assert brief.risk_level == "critical"  # T0122 kritik kalıyor
    assert "alarm" in brief.recommended_action


# --- özet -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ozet",
    [
        "Araç son 30 dakikada yaklaştı.",
        "T0122 üsse yaklaşıyor.",
        "Doğu Yolu bölgesinde ağır araç var.",
        "Duran temas low seviyede.",
        "Birinci cümle. İkinci cümle. Üçüncü cümle.",
        "Park halindeki kayit_disi_1 izlenmeli.",
        # Canlı denemede: yazıyla sayı (duran temas bir taneydi) ve bölge adlarının yönleri.
        "İki başka temas üsse yakın uzun süredir duruyor.",
        "Kuzey ve doğu erişim yollarındaki hareketlilik izlenmeli.",
    ],
)
def test_summary_with_numbers_ids_zone_names_or_english_is_dropped(ozet: str) -> None:
    brief = run(FakeProvider(draft([item("T0122", "yaklasma", ["trend"])], ozet=ozet)))

    assert brief.summary is None
    assert brief.summary_rejected is not None
    assert ozet not in brief.text
    assert "Değerlendirme: T0122: üsse yaklaşıyor" in brief.text
    assert brief.is_fallback is False


@pytest.mark.parametrize(
    "ozet",
    [
        SUMMARY,
        "Kayıt dışı temas park halinde olabilir; üs çevresi sakin.",
        "Birden fazla temas üsse yaklaşıyor; ikinci bir kaynak gerekmiyor.",
    ],
)
def test_clean_summary_is_kept(ozet: str) -> None:
    brief = run(FakeProvider(draft([], ozet=ozet)))

    assert (brief.summary, brief.summary_rejected) == (ozet, None)
    assert f"Değerlendirme: {ozet}" in brief.text


PLACEHOLDERS = ["", "   ", "...", "…", "-", "Değerlendirme:"]


@pytest.mark.parametrize("empty", PLACEHOLDERS)
def test_empty_or_placeholder_summary_falls_through_to_the_next_model(empty: str) -> None:
    primary = FakeProvider(draft([], ozet=empty))
    fallback = FakeProvider(draft([]))

    brief = run(primary, fallback)

    assert brief.model == f"{FALLBACK.provider}/{FALLBACK.model_id}"
    assert f"Değerlendirme: {SUMMARY}" in brief.text


# --- yedek yol ------------------------------------------------------------------------


def test_reply_outside_the_schema_falls_through_to_the_next_model() -> None:
    primary = FakeProvider(draft([item("T0122", "tehlikeli")]))
    brief = run(primary, FakeProvider(draft([])))

    assert brief.model == f"{FALLBACK.provider}/{FALLBACK.model_id}"


def test_no_model_answering_within_the_schema_gives_the_automatic_summary() -> None:
    brief = run(
        FakeProvider(draft([item("T0999", "yaklasma")])),
        FakeProvider({"adjustments": [], "assessment": "eski şema"}),
    )

    assert brief.is_fallback is True
    assert brief.model is None
    assert brief.fallback_reason == "kullanılabilir model yok"
    assert "(otomatik özet)" in brief.text
    assert brief.attention == []
    assert level_of(brief, "T0122") == ("critical", "critical")


def test_failing_primary_falls_back_to_the_next_model() -> None:
    brief = run(FakeProvider(RuntimeError("503")), FakeProvider(draft([])))

    assert brief.is_fallback is False
    assert brief.model == f"{FALLBACK.provider}/{FALLBACK.model_id}"


def test_all_models_failing_gives_the_automatic_summary_with_code_levels() -> None:
    brief = run(FakeProvider(RuntimeError("503")), FakeProvider(RuntimeError("timeout")))

    assert brief.is_fallback is True
    assert brief.fallback_reason is not None
    assert "otomatik özet" in brief.text
    assert level_of(brief, "T0122") == ("critical", "critical")


def test_slow_llm_hits_the_time_limit_and_gives_the_automatic_summary() -> None:
    brief = run(FakeProvider(draft([]), delay_s=1.0), timeout_s=0.1)

    assert brief.is_fallback is True
    assert brief.fallback_reason is not None and "zaman" in brief.fallback_reason


def test_without_an_llm_the_brief_is_the_automatic_summary() -> None:
    brief = run(None)

    assert brief.is_fallback is True
    assert brief.model is None
    assert brief.attention == []
    assert "Değerlendirme" not in brief.text


def test_decision_step_is_streamed_between_risk_and_brief() -> None:
    service = EvaluationService(
        InMemoryRepository(PACKAGE),
        FakeDetector(),
        router=LLMRouter(CONFIG, {PRIMARY.provider: FakeProvider(draft([]))}),
    )
    names = [e.name for e in service.evaluate("img_000860")]

    assert names[-3:] == ["risk", "karar", "brief"]


def test_a_report_contradiction_does_not_change_the_level() -> None:
    """ADR-0002: çelişen rapor seviyeyi değiştirmez; tespit esas alınır."""
    brief = run(
        FakeProvider(draft([item("T0032", "rapor_celiskisi", [5], "high")])),
        claims=[CONTRADICTS_T0032],
    )

    assert level_of(brief, "T0032") == ("medium", "medium")
    [a] = attention(brief, "T0032")
    assert (a.accepted, a.level_accepted) == (True, False)
    assert a.rejection is not None and "seviyeyi değiştirmez" in a.rejection


def test_a_rejected_proposal_does_not_block_a_verified_one_for_the_same_contact() -> None:
    brief = run(
        FakeProvider(
            draft(
                [
                    item("T0032", "yaklasma", ["trend"], "high"),
                    item("T0032", "kacirilmis_temas", ["kind"], "high"),
                    item("T0032", "uzun_duraklama", ["stops"], "critical"),
                ]
            )
        )
    )

    assert level_of(brief, "T0032") == ("medium", "high")
    assert [a.level_accepted for a in attention(brief, "T0032")] == [False, True, None]
    assert contact(brief, "T0032").adjustment_rejected is None


# --- kuralların zaten saydığı neden ---------------------------------------------------


def test_raise_with_the_reason_the_rules_already_counted_is_rejected() -> None:
    """Canlı denemede ORTA'sı yaklaşmadan gelen temas "yaklaşma" ile YÜKSEK'e çıkıyordu;
    aynı girdi bir koşuda ORTA, bir koşuda YÜKSEK veriyordu."""
    brief = run(FakeProvider(draft([item("T0032", "uzun_duraklama", ["stops"], "high")])))

    assert contact(brief, "T0032").level_basis == ["uzun_duraklama"]
    assert level_of(brief, "T0032") == ("medium", "medium")
    [a] = attention(brief, "T0032")
    assert (a.accepted, a.level_accepted) == (True, False)
    assert a.text == "üsse 1,6 km'de en az 120 dk'dır duruyor"
    assert a.rejection is not None and "zaten sayıldı" in a.rejection
    assert contact(brief, "T0032").adjustment_rejected == a.rejection


def test_a_threat_warning_that_already_raised_the_level_cannot_raise_it_again() -> None:
    brief = run(
        FakeProvider(draft([item("T0032", "tehdit_uyarisi", [9], "critical")])),
        claims=[THREAT_ABOUT_T0032],
    )

    assert contact(brief, "T0032").level_basis == ["uzun_duraklama", "tehdit_uyarisi"]
    assert level_of(brief, "T0032") == ("medium", "high")
    [a] = attention(brief, "T0032")
    assert a.level_accepted is False
    assert a.rejection is not None and "zaten sayıldı" in a.rejection


def test_the_rules_basis_is_given_to_the_llm() -> None:
    primary = FakeProvider(draft([]))
    run(primary)

    [schema] = primary.schemas
    [dayanak] = [
        prop
        for definition in schema.model_json_schema()["$defs"].values()
        for name, prop in definition.get("properties", {}).items()
        if name == "dayanak"
    ]
    assert "level_basis" in str(dayanak)


# --- kayıt dışı temas -----------------------------------------------------------------

# PARKED üssün 1 km'sinden uzakta, track'i olmayan araç (ADR-0003: düşük).
FAR_PARKED = PARKED


def near_base_contact() -> ContactFinding:
    return ContactFinding(
        kind="unregistered",
        label="car",
        effective_label="car",
        confidence=0.9,
        bbox=(1, 2, 3, 4),
        location=LatLon(lat=39.9, lon=32.8),
        distance_to_base_m=600,
        base_level="medium",
        final_level="medium",
        level_basis=["kayit_disi"],
        certainty="likely",
    )


def test_unregistered_reason_is_verified_from_the_contact_kind() -> None:
    brief = run(
        FakeProvider(
            draft([item("kayit_disi_1", "kayit_disi", ["kind"]), item("T0122", "kayit_disi")])
        ),
        detector=FakeDetector(FAR_PARKED),
    )

    [parked] = attention(brief, "kayit_disi_1")
    assert parked.accepted is True
    assert parked.text is not None and parked.text.startswith("track'i yok (kayıt dışı)")
    [t0122] = attention(brief, "T0122")
    assert t0122.accepted is False
    assert t0122.rejection is not None and "track'i var" in t0122.rejection
    assert "kayıt dışı temas 1: track'i yok" in brief.text


def test_unregistered_reason_alone_cannot_raise_the_level() -> None:
    """ADR-0003: track'in yokluğu kendi başına risk değildir; kurallar onu zaten sayıyor."""
    brief = run(
        FakeProvider(draft([item("kayit_disi_1", "kayit_disi", ["kind"], "medium")])),
        detector=FakeDetector(FAR_PARKED),
    )

    [parked] = [c for c in brief.contacts if c.kind == "unregistered"]
    assert parked.level_basis == ["kayit_disi"]
    assert (parked.base_level, parked.final_level) == ("low", "low")
    [a] = attention(brief, "kayit_disi_1")
    assert (a.accepted, a.level_accepted) == (True, False)


def test_far_parked_unregistered_car_may_need_no_attention() -> None:
    brief = run(
        FakeProvider(draft([item("kayit_disi_1", "dikkat_gerekmiyor")])),
        detector=FakeDetector(FAR_PARKED),
    )

    [a] = attention(brief, "kayit_disi_1")
    assert a.accepted is True


def test_no_attention_is_rejected_for_an_unregistered_contact_near_the_base() -> None:
    levels = load_rules().levels
    near = near_base_contact()
    assert near.distance_to_base_m < levels.unregistered_alert_m
    proposal = DecisionDraft.model_validate(draft([item("kayit_disi_1", "dikkat_gerekmiyor")]))

    _, [a], _, _ = apply_attention([near], proposal, [], levels)

    assert a.accepted is False
    assert a.rejection is not None and "kayıt dışı" in a.rejection
