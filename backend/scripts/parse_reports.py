"""Raporları LLM ile iddialara ayırıp `report_claims` tablosuna yazar.

Varsayılan olarak yalnızca iddiası olmayan raporları işler; `--force` hepsini yeniden
ayrıştırır. Model zinciri `app/llm/models.toml` dosyasındaki `report_parse` görevidir.
"""

import argparse
import sys

from app.data_package import format_hhmm
from app.db.models import fetch_package, replace_claims, reports_to_parse
from app.db.session import connect
from app.llm.client import LLMUnavailableError, build_router
from app.pipelines.report_parser import ReportParser


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="Bütün raporları yeniden ayrıştır")
    args = parser.parse_args()

    failed = 0
    with connect() as conn:
        report_parser = ReportParser(build_router(), fetch_package(conn).zones)
        pending = reports_to_parse(conn, force=args.force)
        print(f"Ayrıştırılacak rapor: {len(pending)}")
        for report_id, report in pending:
            try:
                result = report_parser.parse(report)
            except LLMUnavailableError as exc:
                failed += 1
                print(f"  ✗ #{report_id} {format_hhmm(report.time)}: {exc}")
                continue
            replace_claims(conn, report_id, result.claims, result.model_id)
            kinds = ", ".join(c.claim_type for c in result.claims) or "iddia yok"
            print(f"  ✓ #{report_id} {format_hhmm(report.time)} ({result.model_id}): {kinds}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
