"""Sohbet agent'ının araçları (ikinci test noktası, ticket 10).

Araçlar yalnızca okur ve aktif değerlendirmenin çekim anıyla sınırlıdır (ADR-0001):
çekim anından sonraki hiçbir veri, varlığı dahil, görünmez.
"""

from dataclasses import replace
from datetime import time
from pathlib import Path
from typing import Any

from app.agent.service import EvaluationService
from app.agent.tools import ChatTools
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.schemas.api import Brief
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import (
    Corners,
    Detection,
    FieldReport,
    GeoPoint,
    ImageMeta,
    ReportSource,
    VehicleClass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
SPOT = GeoPoint(39.9253, 32.8718)


def coord_claim(claim_id: int, when: time, **overrides: Any) -> ClaimRecord:
    base: dict[str, Any] = {
        "location_type": "coordinate",
        "lat": SPOT.lat,
        "lon": SPOT.lon,
        "zone": None,
        "vehicle_type": "heavy",
        "vehicle_count": 1,
        "color": None,
        "behavior": None,
        "claim_type": "observation",
        "time_reference": None,
        "is_verifiable": True,
    }
    return ClaimRecord(
        claim_id,
        FieldReport(when, ReportSource.OFFICIAL, f"rapor {claim_id}"),
        ReportClaim.model_validate(base | overrides),
    )


CLAIMS = [
    coord_claim(2, time(12, 35)),
    coord_claim(3, time(13, 5), lat=39.9374, lon=32.8483),
    coord_claim(6, time(14, 20)),  # çekim anından (14:10) sonra
]

# Çekim anından sonra (14:30), T0122'nin geçtiği noktada bir kare.
LATER = ImageMeta(
    "img_000870",
    960,
    540,
    time(14, 30),
    Corners(
        GeoPoint(39.923303, 32.859299),
        GeoPoint(39.923303, 32.860701),
        GeoPoint(39.922697, 32.859299),
        GeoPoint(39.922697, 32.860701),
    ),
)


class FakeDetector:
    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK] if image.image_id == "img_000860" else []


def tools(evaluated: list[str] | None = None) -> ChatTools:
    package = read_package(FIXTURE)
    package = replace(package, images=[*package.images, LATER])
    repo = InMemoryRepository(package, claims=CLAIMS)
    service = EvaluationService(repo, FakeDetector())
    brief = service.run("img_000860")

    def evaluate_image(image_id: str) -> Brief:
        (evaluated if evaluated is not None else []).append(image_id)
        return service.run(image_id)

    image = repo.get_image("img_000860")
    assert image is not None
    return ChatTools(repo, image, brief, evaluate_image=evaluate_image)


def test_tool_specs_expose_the_five_read_only_tools() -> None:
    names = {spec["function"]["name"] for spec in tools().specs()}

    assert names == {
        "temas_gecmisi",
        "raporlari_ara",
        "rapor_degerlendirmesi",
        "goruntu_degerlendir",
        "track_diger_goruntulerde",
    }


def test_contact_history_stops_at_the_capture_time() -> None:
    result = tools().call("temas_gecmisi", {"track_id": "T0122"})

    times = [p["time"] for p in result["points"]]
    assert times[0] == "12:10" and times[-1] == "14:10"
    assert all(t <= "14:10" for t in times)
    assert result["trend"] == "approaching"
    assert result["stops"][0]["start"] == "12:10"


def test_contact_history_for_an_unknown_track_is_an_error() -> None:
    assert "hata" in tools().call("temas_gecmisi", {"track_id": "T9999"})


def test_report_search_hides_reports_after_the_capture_time() -> None:
    result = tools().call(
        "raporlari_ara", {"lat": SPOT.lat, "lon": SPOT.lon, "yaricap_m": 300, "bitis": "23:59"}
    )

    assert [r["claim_id"] for r in result["reports"]] == [2]


def test_report_search_by_time_window() -> None:
    result = tools().call("raporlari_ara", {"baslangic": "13:00", "bitis": "13:30"})

    assert [r["claim_id"] for r in result["reports"]] == [3]


def test_report_decision_is_explained_from_the_brief() -> None:
    result = tools().call("rapor_degerlendirmesi", {"claim_id": 2})

    assert result["verdict"] == "consistent"
    assert result["track_id"] == "T0032"
    assert "reasoning" in result


def test_report_outside_this_evaluation_is_explained_as_not_considered() -> None:
    result = tools().call("rapor_degerlendirmesi", {"claim_id": 3})

    assert "değerlendirmede ele alınmadı" in result["not"]


def test_report_after_the_capture_time_looks_exactly_like_a_missing_one() -> None:
    after = tools().call("rapor_degerlendirmesi", {"claim_id": 6})
    missing = tools().call("rapor_degerlendirmesi", {"claim_id": 999})

    assert after == {"hata": "6 kimlikli iddia bulunamadı"}
    assert missing == {"hata": "999 kimlikli iddia bulunamadı"}


def test_earlier_image_can_be_evaluated() -> None:
    evaluated: list[str] = []

    result = tools(evaluated).call("goruntu_degerlendir", {"image_id": "img_000100"})

    assert evaluated == ["img_000100"]
    assert result["risk_level"] == "low"
    assert result["zone"] == "Kuzey Yolu"


def test_image_after_the_capture_time_cannot_be_evaluated() -> None:
    evaluated: list[str] = []

    result = tools(evaluated).call("goruntu_degerlendir", {"image_id": "img_000870"})

    assert "hata" in result
    assert evaluated == []


def test_track_is_found_only_in_frames_up_to_the_capture_time() -> None:
    t = tools()

    assert [
        f["image_id"] for f in t.call("track_diger_goruntulerde", {"track_id": "T0200"})["frames"]
    ] == ["img_000100"]
    # T0122 14:30'da img_000870'in içinde ama o kare çekim anından sonra.
    assert [
        f["image_id"] for f in t.call("track_diger_goruntulerde", {"track_id": "T0122"})["frames"]
    ] == ["img_000860"]


def test_unknown_tool_or_bad_arguments_return_an_error_instead_of_raising() -> None:
    t = tools()

    assert "hata" in t.call("yok_boyle_arac", {})
    assert "hata" in t.call("temas_gecmisi", {})
    assert "hata" in t.call("rapor_degerlendirmesi", {"claim_id": "iki"})
