"""Rapor doğrulama sonuçlarını bütün görüntüler için doldurur (demo öncesi bir kez).

Supabase modunda sonuçlar `report_verifications` tablosuna, yerel pakette dosyaya yazılır.

Değerlendirme akışıyla aynı veri, tespit ve iddialar kullanılır; böylece demoda rapor adımı
önbellekten anında gelir. Karar/brief LLM'i çağrılmaz. Görüntüler paralel işlenir; gateway'in
eşzamanlı istek sınırını (4) LLM istemcisi zaten uygular.

    python -m scripts.fill_report_cache              # .env'deki kaynak (Supabase)
    python -m scripts.fill_report_cache --package ../../stage2 --claims claims.json
"""

import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.agent import stages
from scripts.common import add_source_args, build_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_source_args(parser)
    parser.add_argument("--workers", type=int, default=4, help="Aynı anda işlenen görüntü")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    service = build_service(args)
    repo = service.repository
    verifier = service.report_verifier
    images = repo.list_images()
    before = verifier.cache().size()
    started = time.monotonic()

    def fill(image_id: str) -> tuple[str, int, int]:
        ctx = stages.image_context(repo, service.require_image(image_id))
        verified = verifier.verify(ctx.image, ctx.zone, ctx.now, repo.claims_until(ctx.now))
        review = sum(v.needs_review for v in verified)
        return image_id, len(verified), review

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for image_id, n, review in pool.map(fill, [i.image_id for i in images]):
            print(f"{image_id}: {n} rapor, {review} operatör incelemeli")

    cache = verifier.cache()
    after = cache.size()
    print(
        f"{len(images)} görüntü, {time.monotonic() - started:.0f} sn; önbellekte "
        f"{after} cevap ({after - before} yeni) → {cache.where()}"
    )


if __name__ == "__main__":
    main()
