"""Görüntüsüz track'leri değerlendirir ve Supabase'e yazar.

Önce günün risk tablosunu yeni bir koşu olarak yazar (görüntüsüz track'ler `image_id`
boş, görüntü özetlerine katılmaz), sonra her görüntüsüz track için LLM'den kısa bir
değerlendirme alıp `track_assessments` tablosuna yazar. Sonuç `unframed_tracks_latest`
görünümünden okunur. Seviyeyi risk motoru verir; LLM seviyeyi değiştirmez.

    python -m scripts.assess_tracks            # hesapla, LLM ile değerlendir, yaz
    python -m scripts.assess_tracks --no-llm   # LLM'siz, otomatik özetle
    python -m scripts.assess_tracks --dry-run  # yazmadan, yalnızca ekrana
"""

import argparse

from app.agent import stages
from app.agent.risk_day import compute_day
from app.agent.track_brief import TrackBrief, related_claims, write_track_brief
from app.core.config import get_settings
from app.core.rules import default_rules, rules_version
from app.data_package import from_minutes
from app.db.models import fetch_claims, fetch_package
from app.db.repositories import InMemoryRepository
from app.db.risk_store import save_day, save_track_briefs
from app.db.session import connect
from app.llm.client import build_router
from app.pipelines.detection import build_detector


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-llm", action="store_true", help="LLM'siz, otomatik özetle")
    parser.add_argument("--dry-run", action="store_true", help="veritabanına yazma")
    args = parser.parse_args()

    settings = get_settings()
    rules = default_rules()
    with connect(settings) as conn:
        repo = InMemoryRepository(fetch_package(conn), claims=fetch_claims(conn))
    router = None if args.no_llm else build_router(settings, check_budget=True)
    day = compute_day(repo, build_detector(settings), rules)
    base = repo.base().location
    print(f"Görüntüsüz track: {len(day.unframed)} · kural sürümü {rules_version(rules)}")

    briefs: list[tuple[TrackBrief, float]] = []
    for track_id in day.unframed:
        risk = day.tracks[track_id]
        end = risk.current.t
        now = from_minutes(int(end))
        history = repo.track_history(track_id, until=now)
        motion = stages.motion_finding(history, base, now, repo.zones(), rules)
        claims = related_claims([(p.track_id, p.location) for p in history], repo.claims_until(now))
        brief = write_track_brief(
            router,
            risk,
            motion,
            claims,
            timeout_s=rules.brief.timeout_s,
            max_tokens=rules.brief.max_tokens,
        )
        briefs.append((brief, end))
        note = f" · otomatik özet ({brief.rejected})" if brief.is_fallback else ""
        print(f"{track_id} {brief.level} {brief.code}{note}\n  {brief.text}")

    if args.dry_run:
        return
    with connect(settings) as conn:
        source = settings.detections_source if settings.use_inference == "DEMO" else None
        run_id = save_day(conn, day, rules.engine, source)
        save_track_briefs(conn, run_id, rules_version(rules), briefs)
    print(f"Yazıldı: risk koşusu {run_id}, {len(briefs)} değerlendirme (unframed_tracks_latest)")


if __name__ == "__main__":
    main()
