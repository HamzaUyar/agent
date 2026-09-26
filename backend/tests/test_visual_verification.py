"""Değerlendirme servisi: VLM ile görsel doğrulama (ticket 08).

VLM sahte bir doğrulayıcıdır; ne zaman çağrıldığı ve sonucun rapor kararına ve zayıf
tespit kararına nasıl yansıdığı gerçek kodla çalışır.
"""

import io
import threading
import time as clock
from datetime import time
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.llm.client import LLMRouter, load_model_config
from app.pipelines.vision import VlmVerifier
from app.schemas.api import Brief, ContactFinding, ReportFinding, VisualFinding
from app.schemas.claims import ClaimRecord, ReportClaim
from app.schemas.domain import (
    Detection,
    FieldReport,
    GeoPoint,
    ImageMeta,
    ReportSource,
    VehicleClass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)
WEAK_TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.35, x=727, y=284, w=58, h=34)
T0122_AT_1410 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0122" and p.time == time(14, 10)
)
T0032_AT_1340 = next(
    p.location for p in PACKAGE.track_points if p.track_id == "T0032" and p.time == time(13, 40)
)
OFFICIAL, THIRD = ReportSource.OFFICIAL, ReportSource.THIRD_PARTY


class FakeDetector:
    version = "test"

    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections

    def detect(self, image: ImageMeta) -> list[Detection]:
        return list(self._detections) if image.image_id == "img_000860" else []


class FakeVerifier:
    """Her kutu için aynı gözlemi döndürür; çağrıları kaydeder."""

    def __init__(self, finding: VisualFinding | None) -> None:
        self.finding = finding
        self.calls: list[tuple[str, tuple[float, float, float, float]]] = []

    def inspect(
        self, image: ImageMeta, bbox: tuple[float, float, float, float]
    ) -> VisualFinding | None:
        self.calls.append((image.image_id, bbox))
        return self.finding


def seen(color: Any = None, cargo: Any = None, *, is_vehicle: bool = True) -> VisualFinding:
    return VisualFinding(is_vehicle=is_vehicle, color=color, cargo=cargo, model="fake/vlm")


def claim_at(point: GeoPoint, **overrides: Any) -> ReportClaim:
    base: dict[str, Any] = {
        "location_type": "coordinate",
        "lat": point.lat,
        "lon": point.lon,
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


def record(claim_id: int, when: time, source: ReportSource, c: ReportClaim) -> ClaimRecord:
    return ClaimRecord(claim_id=claim_id, report=FieldReport(when, source, "rapor"), claim=c)


def evaluate(
    claims: list[ClaimRecord],
    verifier: FakeVerifier | None,
    detections: list[Detection] | None = None,
) -> Brief:
    repo = InMemoryRepository(PACKAGE, claims=claims)
    detector = FakeDetector([TRUCK] if detections is None else detections)
    return EvaluationService(repo, detector, verifier=verifier).run("img_000860")


def finding(brief: Brief, claim_id: int) -> ReportFinding:
    [f] = [f for f in brief.report_findings if f.claim_id == claim_id]
    return f


def contact(brief: Brief, track_id: str) -> ContactFinding:
    [c] = [c for c in brief.contacts if c.track_id == track_id]
    return c


# --- Yalnızca gerektiğinde -------------------------------------------------------


def test_vlm_is_not_called_without_color_or_cargo_claims_or_weak_detections() -> None:
    verifier = FakeVerifier(seen("beyaz"))
    plain = record(10, time(14, 10), OFFICIAL, claim_at(T0122_AT_1410, vehicle_type="truck"))

    brief = evaluate([plain], verifier)

    assert verifier.calls == []
    assert contact(brief, "T0122").visual is None


def test_vlm_is_called_once_for_the_box_of_a_contact_with_a_color_claim() -> None:
    verifier = FakeVerifier(seen("mavi"))
    blue = record(10, time(14, 10), THIRD, claim_at(T0122_AT_1410, color="mavi"))
    also_blue = record(11, time(14, 10), OFFICIAL, claim_at(T0122_AT_1410, color="Mavi"))

    brief = evaluate([blue, also_blue], verifier)

    assert verifier.calls == [("img_000860", (727, 284, 58, 34))]
    assert contact(brief, "T0122").visual == seen("mavi")


def test_color_claim_about_an_undetected_contact_stays_unverified_without_vlm() -> None:
    # 13:40'ta noktada park halindeki T0032 var; karede kaçırılmış, kutusu yok.
    verifier = FakeVerifier(seen("mavi"))
    blue = record(10, time(13, 40), OFFICIAL, claim_at(T0032_AT_1340, color="mavi"))

    brief = evaluate([blue], verifier)

    assert verifier.calls == []
    assert finding(brief, 10).track_id == "T0032"
    assert finding(brief, 10).certainty == "likely"
    assert "renk doğrulanamadı" in finding(brief, 10).reasoning


# --- Renk ve yük rapor kararına yansır -------------------------------------------


def test_color_mismatch_makes_the_report_contradict() -> None:
    package_level = evaluate([], None)
    blue = record(10, time(14, 10), THIRD, claim_at(T0122_AT_1410, color="mavi"))

    brief = evaluate([blue], FakeVerifier(seen("beyaz")))

    f = finding(brief, 10)
    assert (f.verdict, f.effect) == ("contradicts", "none")
    assert "renk" in f.reasoning
    assert f.certainty == "likely"  # görsel özellik: VLM'e dayalı çelişki kesin sayılmaz
    assert contact(package_level, "T0122").final_level == "critical"
    assert contact(brief, "T0122").final_level == "critical"


def test_color_mismatch_does_not_change_the_contact_level() -> None:
    # T0032 kaçırılmış; kutusunu bu testte zayıf olmayan ikinci bir tespit veriyor.
    verifier = FakeVerifier(seen("beyaz"))
    blue = record(10, time(13, 40), OFFICIAL, claim_at(T0032_AT_1340, color="mavi"))
    t0032_box = _box_over("T0032")

    brief = evaluate([blue], verifier, [TRUCK, t0032_box])

    c = contact(brief, "T0032")
    assert (c.base_level, c.final_level) == ("medium", "medium")  # VLM değil tespit esas
    assert finding(brief, 10).verdict == "contradicts"


def test_matching_color_lets_an_official_friendly_claim_verify_a_friend() -> None:
    friend = record(
        10,
        time(14, 10),
        OFFICIAL,
        claim_at(T0122_AT_1410, claim_type="friendly_claim", vehicle_type="truck", color="mavi"),
    )

    brief = evaluate([friend], FakeVerifier(seen("mavi")))

    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("consistent", "lowers")
    assert contact(brief, "T0122").final_level == "low"
    assert contact(brief, "T0122").verified_friend is True


def test_color_named_with_turkish_characters_or_shade_matches_the_palette() -> None:
    friend = record(
        10,
        time(14, 10),
        OFFICIAL,
        claim_at(T0122_AT_1410, claim_type="friendly_claim", color="koyu yeşil"),
    )

    brief = evaluate([friend], FakeVerifier(seen("yesil")))

    assert finding(brief, 10).effect == "lowers"


def test_vlm_unable_to_tell_the_color_keeps_the_friendly_claim_unverified() -> None:
    friend = record(
        10,
        time(14, 10),
        OFFICIAL,
        claim_at(T0122_AT_1410, claim_type="friendly_claim", color="mavi"),
    )

    brief = evaluate([friend], FakeVerifier(seen(color=None)))

    assert (finding(brief, 10).verdict, finding(brief, 10).effect) == ("unverifiable", "none")
    assert contact(brief, "T0122").final_level == "critical"


def test_vlm_failure_leaves_the_color_unverified() -> None:
    friend = record(
        10,
        time(14, 10),
        OFFICIAL,
        claim_at(T0122_AT_1410, claim_type="friendly_claim", color="mavi"),
    )

    brief = evaluate([friend], FakeVerifier(None))

    assert finding(brief, 10).verdict == "unverifiable"
    assert contact(brief, "T0122").visual is None


def test_cargo_mismatch_contradicts() -> None:
    loaded = record(10, time(14, 10), OFFICIAL, claim_at(T0122_AT_1410, cargo="loaded"))

    brief = evaluate([loaded], FakeVerifier(seen("beyaz", "empty")))

    assert finding(brief, 10).verdict == "contradicts"
    assert "yük" in finding(brief, 10).reasoning


def test_cargo_match_is_consistent() -> None:
    loaded = record(10, time(14, 10), OFFICIAL, claim_at(T0122_AT_1410, cargo="loaded"))

    brief = evaluate([loaded], FakeVerifier(seen("beyaz", "loaded")))

    assert (finding(brief, 10).verdict, finding(brief, 10).certainty) == ("consistent", "certain")


# --- Zayıf tespit kararına yansır ------------------------------------------------


def test_weak_detection_is_checked_and_confirmed_vehicle_becomes_likely() -> None:
    verifier = FakeVerifier(seen("beyaz"))

    brief = evaluate([], verifier, [WEAK_TRUCK])

    c = contact(brief, "T0122")
    assert verifier.calls == [("img_000860", (727, 284, 58, 34))]
    assert c.kind == "matched"
    assert c.is_weak is True
    assert c.certainty == "likely"
    assert c.visual == seen("beyaz")


def test_vlm_cannot_drop_a_weak_detection_that_a_track_confirms() -> None:
    """Track 1 m içinde: orada bir araç var. VLM seçemese de kutu kalır, kesinlik zayıf kalır."""
    brief = evaluate([], FakeVerifier(seen(is_vehicle=False)), [WEAK_TRUCK])

    c = contact(brief, "T0122")
    assert (c.kind, c.label, c.certainty) == ("matched", "truck", "weak")
    assert c.bbox is not None
    assert "araç görsel olarak seçilemedi" in brief.text


def test_weak_detection_without_a_vlm_answer_stays_weak() -> None:
    brief = evaluate([], FakeVerifier(None), [WEAK_TRUCK])

    c = contact(brief, "T0122")
    assert (c.kind, c.certainty) == ("matched", "weak")


def test_weak_detection_color_is_reused_for_reports_without_a_second_call() -> None:
    verifier = FakeVerifier(seen("mavi"))
    blue = record(10, time(14, 10), THIRD, claim_at(T0122_AT_1410, color="mavi"))

    brief = evaluate([blue], verifier, [WEAK_TRUCK])

    assert len(verifier.calls) == 1
    assert finding(brief, 10).verdict == "consistent"


def test_unmatched_weak_detection_is_not_sent_to_the_vlm() -> None:
    verifier = FakeVerifier(seen("beyaz"))
    stray = Detection(label=VehicleClass.CAR, confidence=0.3, x=10, y=10, w=20, h=20)

    evaluate([], verifier, [TRUCK, stray])

    assert verifier.calls == []


def test_brief_text_mentions_the_visual_check() -> None:
    blue = record(10, time(14, 10), THIRD, claim_at(T0122_AT_1410, color="mavi"))

    brief = evaluate([blue], FakeVerifier(seen("beyaz", "loaded")))

    assert "görsel: beyaz, yüklü" in brief.text


# --- yardımcı -----------------------------------------------------------------


def _box_over(track_id: str) -> Detection:
    """Track'in çekim anındaki konumuna denk gelen güçlü bir kutu."""
    image = next(m for m in PACKAGE.images if m.image_id == "img_000860")
    [point] = [
        p.location
        for p in PACKAGE.track_points
        if p.track_id == track_id and p.time == image.capture_time
    ]
    c = image.corners
    cx = (point.lon - c.top_left.lon) / (c.top_right.lon - c.top_left.lon) * image.width_px
    cy = (c.top_left.lat - point.lat) / (c.top_left.lat - c.bottom_left.lat) * image.height_px
    return Detection(label=VehicleClass.CAR, confidence=0.9, x=cx - 10, y=cy - 10, w=20, h=20)


# --- Gerçek doğrulayıcı: kırpma ve VLM zinciri (sahte sağlayıcıyla) --------------


class FakeVisionProvider:
    def __init__(self, reply: dict[str, Any], *, delay_s: float = 0.0) -> None:
        self.reply = reply
        self.delay_s = delay_s
        self.images: list[bytes] = []

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
        image: bytes | None = None,
    ) -> BaseModel:
        assert image is not None
        self.images.append(image)
        if self.delay_s:
            clock.sleep(self.delay_s)
        return schema.model_validate(self.reply)


def vlm(provider: FakeVisionProvider, images_dir: Path, timeout_s: float = 5) -> VlmVerifier:
    config = load_model_config()
    first = config.models[config.tasks["vision"][0]]
    return VlmVerifier(
        LLMRouter(config, {first.provider: provider}), images_dir, timeout_s=timeout_s
    )


IMG_000860 = next(m for m in PACKAGE.images if m.image_id == "img_000860")


def test_vlm_verifier_sends_an_enlarged_crop_of_the_box(tmp_path: Path) -> None:
    Image.new("RGB", (IMG_000860.width_px, IMG_000860.height_px), "white").save(
        tmp_path / "img_000860.jpg"
    )
    provider = FakeVisionProvider({"is_vehicle": True, "color": "beyaz", "cargo": None})

    result = vlm(provider, tmp_path).inspect(IMG_000860, (727, 284, 58, 34))

    assert result is not None
    assert (result.is_vehicle, result.color, result.cargo) == (True, "beyaz", None)
    assert result.model == "evren/qwen3-vl-30b"
    [sent] = provider.images
    with Image.open(io.BytesIO(sent)) as crop:
        assert crop.format == "JPEG"
        assert max(crop.size) >= 384


def test_vlm_verifier_without_the_image_file_returns_none(tmp_path: Path) -> None:
    provider = FakeVisionProvider({"is_vehicle": True, "color": None, "cargo": None})

    assert vlm(provider, tmp_path).inspect(IMG_000860, (727, 284, 58, 34)) is None
    assert provider.images == []


def test_vlm_verifier_timeout_returns_none(tmp_path: Path) -> None:
    Image.new("RGB", (100, 100)).save(tmp_path / "img_000860.png")
    provider = FakeVisionProvider({"is_vehicle": True, "color": None, "cargo": None}, delay_s=0.5)

    assert vlm(provider, tmp_path, timeout_s=0.05).inspect(IMG_000860, (10, 10, 20, 20)) is None


def test_vlm_verifier_with_an_unreadable_image_returns_none(tmp_path: Path) -> None:
    (tmp_path / "img_000860.jpg").write_bytes(b"not an image")
    provider = FakeVisionProvider({"is_vehicle": True, "color": None, "cargo": None})

    assert vlm(provider, tmp_path).inspect(IMG_000860, (727, 284, 58, 34)) is None


class BarrierVerifier(FakeVerifier):
    """İki çağrı aynı anda gelmezse bariyer zaman aşımına uğrar: sıralı çağrıyı yakalar."""

    def __init__(self, finding: VisualFinding | None) -> None:
        super().__init__(finding)
        self.barrier = threading.Barrier(2, timeout=2)

    def inspect(
        self, image: ImageMeta, bbox: tuple[float, float, float, float]
    ) -> VisualFinding | None:
        self.barrier.wait()
        return super().inspect(image, bbox)


def box_at(point: GeoPoint, image_id: str = "img_000860") -> Detection:
    [image] = [m for m in PACKAGE.images if m.image_id == image_id]
    c = image.corners
    x = (point.lon - c.top_left.lon) / (c.top_right.lon - c.top_left.lon) * image.width_px
    y = (c.top_left.lat - point.lat) / (c.top_left.lat - c.bottom_left.lat) * image.height_px
    return Detection(label=VehicleClass.CAR, confidence=0.35, x=x - 10, y=y - 10, w=20, h=20)


def test_weak_detections_are_checked_in_parallel() -> None:
    """Her VLM çağrısı ~10 sn; kutular sırayla değil aynı anda sorulur."""
    t0032_now = next(
        p.location for p in PACKAGE.track_points if p.track_id == "T0032" and p.time == time(14, 10)
    )
    verifier = BarrierVerifier(seen("beyaz"))

    brief = evaluate([], verifier, [WEAK_TRUCK, box_at(t0032_now)])

    assert len(verifier.calls) == 2
    assert {contact(brief, t).certainty for t in ("T0122", "T0032")} == {"likely"}
