"""Supabase'teki ayrıştırılmış iddiaları JSON'a yazar (ağsız demo ve değerlendirme için).

Dosya `DATA_SOURCE=package` + `CLAIMS_PATH` ile API'de, `--package --claims` ile
script'lerde kullanılır; raporlar yeniden ayrıştırılmaz.

    python -m scripts.export_claims --out ../../stage2/claims.json
"""

import argparse
from pathlib import Path

from app.data_package import dump_claims
from app.db.models import fetch_claims
from app.db.session import connect


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="Yazılacak JSON dosyası")
    args = parser.parse_args()

    with connect() as conn:
        claims = fetch_claims(conn)
    dump_claims(claims, args.out)
    print(f"{len(claims)} iddia yazıldı: {args.out}")


if __name__ == "__main__":
    main()
