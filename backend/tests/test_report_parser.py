"""Rapor ayrıştırıcı: sahte LLM sağlayıcılarıyla (ticket 05).

LLM'in cevabı sahte sağlayıcıdan gelir; koordinat ve bölge normalizasyonu ile
yedek model zinciri gerçek kodla çalışır.
"""

from datetime import time
from typing import Any

import pytest
from pydantic import BaseModel

from app.llm.client import LLMRouter, LLMUnavailableError, load_model_config
from app.pipelines.report_parser import ReportParser
from app.schemas.domain import FieldReport, GeoPoint, ReportSource, Zone

ZONES = [
    Zone("Dogu Yolu", GeoPoint(39.921840, 32.890542)),
    Zone("Bati Yerlesimi", GeoPoint(39.921840, 32.815578)),
]
CONFIG = load_model_config()
CHAIN = [CONFIG.models[name] for name in CONFIG.tasks["report_parse"]]
PRIMARY, FALLBACK = CHAIN[0], CHAIN[1]  # EVREN GLM-5.3 → organizatör GLM'i
assert PRIMARY.provider != FALLBACK.provider
MODEL = PRIMARY.model_id
FALLBACK_MODEL = FALLBACK.model_id
PRIMARY_LABEL = f"{PRIMARY.provider}/{PRIMARY.model_id}"
FALLBACK_LABEL = f"{FALLBACK.provider}/{FALLBACK.model_id}"


class FakeProvider:
    """Model kimliğine göre sabit cevap (sözlük) ya da hata döndürür."""

    def __init__(self, replies: dict[str, Any], available: bool = True) -> None:
        self.replies = replies
        self.available = available
        self.calls: list[str] = []
        self.extra_bodies: list[object] = []

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
        self.calls.append(model_id)
        self.extra_bodies.append(extra_body)
        reply = self.replies[model_id]
        if isinstance(reply, Exception):
            raise reply
        return schema.model_validate(reply)


def claim(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "location_type": "none",
        "lat": None,
        "lon": None,
        "zone": None,
        "vehicle_type": None,
        "vehicle_count": None,
        "color": None,
        "behavior": None,
        "claim_type": "observation",
        "time_reference": None,
        "is_verifiable": True,
    }
    return base | overrides


def parser(primary: FakeProvider, fallback: FakeProvider | None = None) -> ReportParser:
    """Zincirin ilk iki sağlayıcısı sahte; geri kalanlar kimlik bilgisi yokmuş gibi atlanır."""
    providers = {e.provider: FakeProvider({}, available=False) for e in CHAIN}
    providers[PRIMARY.provider] = primary
    providers[FALLBACK.provider] = fallback or FakeProvider({}, available=False)
    return ReportParser(LLMRouter(CONFIG, providers), ZONES)


def report(text: str, source: ReportSource = ReportSource.OFFICIAL) -> FieldReport:
    return FieldReport(time(13, 5), source, text)


TRUCK_TEXT = "39.9374N 32.8483E civarinda 1 kamyon goruldu, yukleri tespit edilemedi."


def test_coordinates_come_from_the_report_text_not_the_llm() -> None:
    llm = FakeProvider(
        {
            MODEL: {
                "claims": [
                    claim(
                        location_type="coordinate",
                        lat=39.0,
                        lon=32.0,
                        vehicle_type="truck",
                        vehicle_count=1,
                    )
                ]
            }
        }
    )

    result = parser(llm).parse(report(TRUCK_TEXT))

    [c] = result.claims
    assert (c.location_type, c.lat, c.lon) == ("coordinate", 39.9374, 32.8483)
    assert (c.vehicle_type, c.vehicle_count, c.claim_type) == ("truck", 1, "observation")
    assert result.model_id == PRIMARY_LABEL


def test_coordinates_the_text_does_not_contain_are_dropped() -> None:
    llm = FakeProvider({MODEL: {"claims": [claim(location_type="coordinate", lat=39.9, lon=32.8)]}})

    [c] = parser(llm).parse(report("Bolgede trafik akisi normal seyrediyor.")).claims

    assert (c.location_type, c.lat, c.lon) == ("none", None, None)


def test_coordinates_in_the_text_are_used_even_if_the_llm_missed_them() -> None:
    llm = FakeProvider({MODEL: {"claims": [claim(vehicle_type="truck")]}})

    [c] = parser(llm).parse(report(TRUCK_TEXT)).claims

    assert (c.location_type, c.lat, c.lon) == ("coordinate", 39.9374, 32.8483)


def test_zone_names_are_matched_to_known_zones() -> None:
    llm = FakeProvider(
        {
            MODEL: {
                "claims": [
                    claim(location_type="zone", zone="Batı Yerleşimi", behavior="normal_traffic")
                ]
            }
        }
    )

    [c] = parser(llm).parse(report("Bati Yerlesimi bolgesinde trafik akisi normal.")).claims

    assert (c.location_type, c.zone, c.behavior) == ("zone", "Bati Yerlesimi", "normal_traffic")


def test_unknown_zone_names_are_dropped() -> None:
    llm = FakeProvider({MODEL: {"claims": [claim(location_type="zone", zone="Mars Yolu")]}})

    [c] = parser(llm).parse(report("Mars Yolu bolgesinde hareketlilik var.")).claims

    assert (c.location_type, c.zone) == ("none", None)


def test_friendly_claim_with_vague_time_is_unverifiable() -> None:
    llm = FakeProvider(
        {
            MODEL: {
                "claims": [
                    claim(
                        claim_type="friendly_claim",
                        time_reference="gun icinde",
                        is_verifiable=False,
                    )
                ]
            }
        }
    )

    [c] = (
        parser(llm)
        .parse(
            report(
                "Planli tatbikat nedeniyle gun icinde bolgede dost unsurlar bulunacak.",
                ReportSource.THIRD_PARTY,
            )
        )
        .claims
    )

    assert (c.claim_type, c.time_reference, c.is_verifiable) == (
        "friendly_claim",
        "gun icinde",
        False,
    )


def test_a_report_can_hold_several_claims() -> None:
    llm = FakeProvider(
        {
            MODEL: {
                "claims": [
                    claim(vehicle_type="truck", color="mavi"),
                    claim(claim_type="friendly_claim"),
                ]
            }
        }
    )

    result = parser(llm).parse(
        report("39.9253N 32.8718E yakininda mavi bir kamyon; dost unsurdur.")
    )

    assert [c.claim_type for c in result.claims] == ["observation", "friendly_claim"]
    assert result.claims[0].color == "mavi"


def test_non_positive_vehicle_count_is_dropped() -> None:
    llm = FakeProvider({MODEL: {"claims": [claim(vehicle_type="car", vehicle_count=0)]}})

    [c] = parser(llm).parse(report("Bir arac goruldu.")).claims

    assert c.vehicle_count is None


# --- Model yönlendirme ve yedek model -----------------------------------------


def test_primary_model_failure_falls_back_to_the_next_model() -> None:
    primary = FakeProvider({MODEL: RuntimeError("503")})
    fallback = FakeProvider({FALLBACK_MODEL: {"claims": [claim(vehicle_type="truck")]}})

    result = parser(primary, fallback).parse(report(TRUCK_TEXT))

    assert result.model_id == FALLBACK_LABEL
    assert primary.calls == [MODEL] and fallback.calls == [FALLBACK_MODEL]


def test_invalid_output_from_primary_falls_back_to_the_next_model() -> None:
    primary = FakeProvider({MODEL: {"claims": [{"claim_type": "not-a-type"}]}})
    fallback = FakeProvider({FALLBACK_MODEL: {"claims": [claim()]}})

    assert parser(primary, fallback).parse(report(TRUCK_TEXT)).model_id == FALLBACK_LABEL


def test_model_without_credentials_is_skipped() -> None:
    primary = FakeProvider({MODEL: {"claims": [claim()]}}, available=False)
    fallback = FakeProvider({FALLBACK_MODEL: {"claims": [claim()]}})

    result = parser(primary, fallback).parse(report(TRUCK_TEXT))

    assert result.model_id == FALLBACK_LABEL
    assert primary.calls == []


def test_all_models_failing_raises() -> None:
    primary = FakeProvider({MODEL: RuntimeError("503"), "deepseek-v4.1-flash": RuntimeError("503")})
    fallback = FakeProvider({FALLBACK_MODEL: RuntimeError("timeout")})

    with pytest.raises(LLMUnavailableError) as exc:
        parser(primary, fallback).parse(report(TRUCK_TEXT))

    assert [model for model, _ in exc.value.attempts] == [e.model_id for e in CHAIN]


def test_task_routing_comes_from_the_models_file() -> None:
    chains = {
        task: [CONFIG.models[name].model_id for name in names]
        for task, names in CONFIG.tasks.items()
    }

    # Görev tanımı s4: metin görevleri organizatör gateway'inin glm-5.3-flash'ıyla başlar;
    # EVREN yedektir. VLM zincirinde GLM yok (görüntülü istekte şemaya uymuyor).
    assert chains.pop("vision")[0] == "qwen3-vl-30b"
    assert "glm-5.3-flash" not in [CONFIG.models[n].model_id for n in CONFIG.tasks["vision"]]
    # Rapor doğrulamadaki görsel bakış yalnızca organizatör gateway'inden (EVREN yok).
    assert chains.pop("look") == ["glm-5.3-flash"]
    for task, chain in chains.items():
        assert chain[0] == "glm-5.3-flash", task
        assert CONFIG.models[CONFIG.tasks[task][0]].provider == "glm", task
        assert CONFIG.models[CONFIG.tasks[task][1]].provider == "evren", task


def test_text_coordinates_are_kept_when_the_named_zone_is_unknown() -> None:
    llm = FakeProvider({MODEL: {"claims": [claim(location_type="zone", zone="Dogu Kavsak")]}})

    [c] = (
        parser(llm).parse(report("39.9253N 32.8718E civari Dogu Kavsak bolgesinde kamyon.")).claims
    )

    assert (c.location_type, c.lat, c.lon, c.zone) == ("coordinate", 39.9253, 32.8718, None)


def test_model_specific_request_options_reach_the_provider() -> None:
    llm = FakeProvider({MODEL: {"claims": [claim()]}})

    parser(llm).parse(report(TRUCK_TEXT))

    assert llm.extra_bodies == [PRIMARY.extra_body or None]
    # Gateway'de düşünme kapatılamaz ve `thinking` hata verir (görev tanımı s11).
    assert PRIMARY.extra_body == {"reasoning_effort": "low"}


def test_negated_heavy_vehicle_claim_becomes_light() -> None:
    """Gerçek veri: GLM "agir arac hareketi yok, yalnizca binek" raporunu "heavy" ayrıştırdı."""
    llm = FakeProvider(
        {
            MODEL: {
                "claims": [
                    claim(location_type="zone", zone="Guneybati Yolu", vehicle_type="heavy"),
                    claim(location_type="zone", zone="Guneybati Yolu", vehicle_type="car"),
                ]
            }
        }
    )
    text = "Guneybati Yolu bolgesinde agir arac hareketi yok, yalnizca binek araclar goruluyor."

    claims = parser(llm).parse(report(text)).claims

    assert [c.vehicle_type for c in claims] == ["light", "light"]


def test_affirmative_heavy_vehicle_claim_is_kept() -> None:
    llm = FakeProvider({MODEL: {"claims": [claim(vehicle_type="heavy")]}})

    [c] = parser(llm).parse(report("39.9253N 32.8718E cevresinde 1 agir arac bulunuyor.")).claims

    assert c.vehicle_type == "heavy"


def test_a_json_answer_wrapped_in_the_schema_shape_is_unwrapped() -> None:
    from app.llm.client import parse_schema_json

    class Look(BaseModel):
        tip: str
        emin: str

    wrapped = '{"description": "kamyon gibi", "properties": {"tip": "kamyon", "emin": "orta"}}'

    assert parse_schema_json(wrapped, Look) == Look(tip="kamyon", emin="orta")
    assert parse_schema_json('```json\n{"tip": "a", "emin": "b"}\n```', Look).tip == "a"
