"""İz sürme komutu (scripts/trace_evaluation.py): her kolun çıktısı görünür olmalı."""

import io
from pathlib import Path

from PIL import Image

from app.agent.service import EvaluationService
from app.data_package import read_package
from app.db.repositories import InMemoryRepository
from app.schemas.domain import Detection, ImageMeta, VehicleClass
from scripts.trace_evaluation import trace

FIXTURE = Path(__file__).parent / "fixtures" / "mock_package"
PACKAGE = read_package(FIXTURE)
TRUCK = Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34)


class FakeDetector:
    def detect(self, image: ImageMeta) -> list[Detection]:
        return [TRUCK] if image.image_id == "img_000860" else []


def test_trace_shows_every_arm_with_the_reference_values(tmp_path: Path) -> None:
    Image.new("RGB", (960, 540)).save(tmp_path / "img_000860.jpg")
    service = EvaluationService(InMemoryRepository(PACKAGE), FakeDetector())
    out = io.StringIO()

    brief = trace(service, "img_000860", out, images=tmp_path, image_out=tmp_path / "iz.png")

    text = out.getvalue()
    sections = [
        "Görüntü meta verisi",
        "KOL A · Tespit",
        "KOL A · Konum",
        "KOL B1 · Çekim anı konumları",
        "BİRLEŞİM 1 · Eşleşme",
        "KOL B2 · Hareket analizi",
        "BİRLEŞİM 2 · Temel seviye",
        "KOL C · Raporlar",
        "RİSK",
        "KARAR",
        "BRIEF",
    ]
    positions = [text.index(s) for s in sections]
    assert positions == sorted(positions)
    assert "(756, 301) px → 39.92531, 32.87183" in text
    assert "#1  → T0122  0.4 m · ikinci aday T0032 41 m" in text
    assert "T0032 karede ama tespit yok → kaçırılmış temas" in text
    assert "Görüntü seviyesi (en yüksek temas): KRİTİK" in text
    assert brief.risk_level == "critical"
    assert (tmp_path / "iz.png").exists()
