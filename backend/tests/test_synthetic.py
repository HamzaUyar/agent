"""Sentetik 2. aşama paketi (scripts/make_synthetic_data.py).

Üretecin kurduğu senaryoyu değerlendirme servisinin birebir geri çıkarması beklenir:
kural tabanlı çalıştırmada (LLM'siz) seviye, eşleşme ve rapor kararlarının hepsi doğru
olmalı. Bir sapma ya üreteçte ya da pipeline'da bir hataya işaret eder.
"""

import random
from pathlib import Path

import pytest
from PIL import Image

from app.agent.service import EvaluationService
from app.data_package import load_claims, read_package
from app.db.repositories import InMemoryRepository
from app.eval_set import load_labels, run_eval_set
from app.pipelines.detection import RecordedDetector, load_detections_json
from scripts.make_synthetic_data import (
    PATTERN,
    SyntheticPackage,
    generate_with_retries,
    read_annotations,
    write_outputs,
)

N_IMAGES = 2 * len(PATTERN)


@pytest.fixture(scope="module")
def kaggle_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Kaggle biçiminde küçük bir eğitim klasörü: 40 görüntü, görüntü başına 2–8 araç."""
    root = tmp_path_factory.mktemp("kaggle")
    (root / "images").mkdir()
    rng = random.Random(3)
    rows = ["image_id,x,y,w,h,label"]
    for n in range(40):
        image_id = f"img_{n:06d}"
        Image.new("RGB", (640, 480), (90, 90, 90)).save(root / "images" / f"{image_id}.jpg")
        count = rng.randint(2, 8)
        for k in range(count):
            label = "truck" if k == 0 and n % 2 == 0 else rng.choice(["car", "car", "van", "bus"])
            w, h = (70, 28) if label in ("truck", "bus") else (44, 22)
            x, y = 20 + (k % 4) * 150, 30 + (k // 4) * 200 + rng.randint(0, 40)
            rows.append(f"{image_id},{x},{y},{w},{h},{label}")
    (root / "annotations.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def synthetic(kaggle_dir: Path) -> SyntheticPackage:
    return generate_with_retries(read_annotations(kaggle_dir), seed=11, n_images=N_IMAGES)


@pytest.fixture(scope="module")
def written(synthetic: SyntheticPackage, tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("synthetic")
    write_outputs(synthetic, out)
    return out


def test_every_archetype_and_report_kind_is_present(synthetic: SyntheticPackage) -> None:
    assert len(synthetic.scenes) == N_IMAGES
    assert {s.archetype for s in synthetic.scenes} == {a for a, _ in PATTERN}
    assert {s.report.kind for s in synthetic.scenes if s.report} >= {
        k for _, k in PATTERN if k is not None
    }


def test_written_package_round_trips(written: Path, synthetic: SyntheticPackage) -> None:
    package = read_package(written / "package")

    assert {m.image_id for m in package.images} == package.image_files
    assert len(package.track_points) == len(synthetic.package.track_points)
    assert len(load_claims(written / "claims.json")) == len(synthetic.claims)
    assert load_detections_json(written / "detections.json") == synthetic.detections
    assert len(load_labels(written / "labels.toml").images) == N_IMAGES


def test_pipeline_recovers_the_scenario_exactly(written: Path) -> None:
    package = read_package(written / "package")
    repo = InMemoryRepository(package, claims=load_claims(written / "claims.json"))
    detector = RecordedDetector(
        load_detections_json(written / "detections.json"), version="sentetik"
    )
    service = EvaluationService(repo, detector)

    result = run_eval_set(service, load_labels(written / "labels.toml"))

    s = result.summary
    wrong = [r for r in result.images if not r.level_ok or r.missing_matches or r.extra_matches]
    wrong_reports = [(r.image_id, c) for r in result.images for c in r.reports if not c.ok]
    assert s.failed == 0, [r.error for r in result.images if r.error]
    assert wrong == [], result.render()
    assert wrong_reports == [], result.render()
    assert s.contradictions_caught == s.contradictions_labeled > 0


def test_generation_is_deterministic(kaggle_dir: Path, synthetic: SyntheticPackage) -> None:
    again = generate_with_retries(read_annotations(kaggle_dir), seed=11, n_images=N_IMAGES)

    assert again.package == synthetic.package
    assert again.detections == synthetic.detections


def test_low_coverage_leaves_background_vehicles_unregistered(kaggle_dir: Path) -> None:
    full = generate_with_retries(read_annotations(kaggle_dir), seed=11, n_images=N_IMAGES)
    sparse = generate_with_retries(
        read_annotations(kaggle_dir), seed=11, n_images=N_IMAGES, coverage=0.3
    )

    def untracked(p: SyntheticPackage) -> int:
        return sum(v.track_id is None for s in p.scenes for v in s.vehicles)

    assert untracked(sparse) > untracked(full)
