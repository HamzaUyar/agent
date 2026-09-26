"""Bütün görüntülerin tespitlerini bir kez çalıştırıp JSON dosyasına yazar.

Demo ve değerlendirme seti için: dosya `DETECTOR_MODE=mock` + `DETECTOR_MOCK_PATH` ile
kullanılınca değerlendirmeler anında başlar, EVREN'in anlık kesintilerinden etkilenmez
ve her çalıştırmada aynı tespitler kullanılır. Tespit bileşeni `.env`'den seçilir
(ör. `DETECTOR_MODE=evren`).

    DETECTOR_MODE=evren DATA_DIR=../../stage2 python -m scripts.export_detections \\
        ../../stage2 --out ../../stage2/detections_evren.json
"""

import argparse
import time
from pathlib import Path

from app.core.config import get_settings
from app.data_package import read_package
from app.pipelines.detection import Detector, build_detector, dump_mock_detections
from app.schemas.domain import Detection, ImageMeta


def export_detections(detector: Detector, images: list[ImageMeta], out: Path) -> None:
    detections: dict[str, list[Detection]] = {}
    for image in images:
        started = time.monotonic()
        detections[image.image_id] = detector.detect(image)
        found = detections[image.image_id]
        print(f"  {image.image_id}: {len(found)} araç ({time.monotonic() - started:.1f} sn)")
    dump_mock_detections(detections, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", type=Path, help="Veri paketi klasörü (images/ ve meta)")
    parser.add_argument("--out", type=Path, required=True, help="Yazılacak JSON dosyası")
    args = parser.parse_args()

    settings = get_settings().model_copy(update={"data_dir": args.package.resolve()})
    detector = build_detector(settings)
    package = read_package(args.package)
    print(f"{len(package.images)} görüntü · tespit: {detector.version}")
    export_detections(detector, package.images, args.out)
    print(f"Yazıldı: {args.out} (kullanım: DETECTOR_MODE=mock, DETECTOR_MOCK_PATH={args.out})")


if __name__ == "__main__":
    main()
