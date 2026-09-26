"""Frontend test verisini ve OpenAPI şemasını backend'in gerçek kodundan üretir.

Çalıştırma (frontend klasöründen): npm run fixtures
Backend'in sanal ortamıyla ve backend klasöründe çalışır; veritabanına bağlanmaz.
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
FRONTEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.agent.runner import EvaluationRunner  # noqa: E402
from app.agent.service import EvaluationService  # noqa: E402
from app.api.data import get_image, get_zones  # noqa: E402
from app.data_package import format_hhmm, read_package  # noqa: E402
from app.db.repositories import InMemoryRepository  # noqa: E402
from app.main import app  # noqa: E402
from app.pipelines.geo import nearest_zone  # noqa: E402
from app.schemas.api import ImageSummary  # noqa: E402
from app.schemas.domain import Detection, ImageMeta, VehicleClass  # noqa: E402

FIXTURES = FRONTEND / "tests" / "fixtures"
STAGE2 = BACKEND.parent / "stage2"
MOCK_PACKAGE = BACKEND / "tests" / "fixtures" / "mock_package"

# Referans örnek: kamyon (727, 284) → T0122; ayrıca eşi olmayan bir otomobil (kayıt dışı temas).
DETECTIONS = {
    "img_000860": [
        Detection(label=VehicleClass.TRUCK, confidence=0.91, x=727, y=284, w=58, h=34),
        Detection(label=VehicleClass.CAR, confidence=0.83, x=120, y=400, w=30, h=18),
    ]
}
# `last_risk_level` gerçekte veritabanındaki son değerlendirmeden gelir; testler için birkaç örnek.
LAST_LEVELS = {
    "img_000860": "high",
    "img_008333": "low",
    "img_004423": "medium",
}


class FakeDetector:
    version = "fixture"

    def detect(self, image: ImageMeta) -> list[Detection]:
        return list(DETECTIONS.get(image.image_id, []))


class MemoryStore:
    def start(self, *args: object) -> str:
        return "run-fixture-1"

    def add_step(self, *args: object) -> None: ...

    def finish(self, *args: object) -> None: ...

    def fail(self, *args: object) -> None: ...

    def latest_cached(self, *args: object) -> None:
        return None


def write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"yazıldı: {path.relative_to(FRONTEND)}")


def main() -> None:
    write(FRONTEND / "lib" / "api" / "openapi.json", app.openapi())

    repo = InMemoryRepository(read_package(MOCK_PACKAGE))
    runner = EvaluationRunner(
        EvaluationService(repo, FakeDetector()), MemoryStore(), detector_version="fixture"
    )
    events = [{"event": kind, "data": payload} for kind, payload in runner.stream("img_000860")]
    write(FIXTURES / "img_000860.events.json", events)

    stage = InMemoryRepository(read_package(STAGE2))
    zones = stage.zones()
    write(FIXTURES / "zones.json", get_zones(stage).model_dump(mode="json"))
    write(
        FIXTURES / "images.json",
        [
            ImageSummary(
                image_id=m.image_id,
                zone=nearest_zone(m.corners.center, zones).name,
                capture_time=format_hhmm(m.capture_time),
                last_risk_level=LAST_LEVELS.get(m.image_id),  # type: ignore[arg-type]
            ).model_dump(mode="json")
            for m in stage.list_images()
        ],
    )
    write(
        FIXTURES / "image_details.json",
        {m.image_id: get_image(m.image_id, stage).model_dump(mode="json") for m in stage.list_images()},
    )


if __name__ == "__main__":
    main()
