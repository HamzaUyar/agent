"""Görüntü dosyalarını Supabase Storage'a yükler ve `images.file_path`'i günceller.

Yalnızca `images` tablosunda kaydı olan görüntüler yüklenir. Tekrar çalıştırılabilir:
nesnelerin üzerine yazılır. `SUPABASE_URL` ve `SUPABASE_SERVICE_ROLE_KEY` gerekir.
"""

import argparse
import mimetypes
from pathlib import Path

from app.core.config import get_settings
from app.data_package import IMAGE_SUFFIXES
from app.db.session import connect
from app.storage import build_storage, storage_path


def image_files(images_dir: Path) -> dict[str, Path]:
    """Klasördeki görüntü dosyaları, kimliğe göre (macOS `._` artıkları atlanır)."""
    return {
        p.stem: p
        for p in sorted(images_dir.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith(".")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "images_dir", type=Path, nargs="?", help="Görüntü klasörü (varsayılan: DATA_DIR/images)"
    )
    args = parser.parse_args()

    settings = get_settings()
    storage = build_storage(settings)
    if storage is None:
        raise SystemExit("SUPABASE_URL ve SUPABASE_SERVICE_ROLE_KEY tanımlanmalı (.env)")
    images_dir = args.images_dir or settings.resolved_data_dir / "images"
    files = image_files(images_dir)

    with connect() as conn:
        known = {row[0] for row in conn.execute("select id from public.images").fetchall()}
        missing = sorted(known - files.keys())
        uploaded = 0
        for image_id in sorted(known & files.keys()):
            path = files[image_id]
            target = storage_path(settings.storage_bucket, path.name)
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            storage.upload(target, path.read_bytes(), content_type)
            with conn.transaction():
                conn.execute(
                    "update public.images set file_path = %s where id = %s", (target, image_id)
                )
            uploaded += 1
            print(f"{image_id} → {target}")

    print(f"Yüklendi: {uploaded}/{len(known)} · bucket: {settings.storage_bucket}")
    if missing:
        print(f"Dosyası olmayan görüntüler: {', '.join(missing)}")


if __name__ == "__main__":
    main()
