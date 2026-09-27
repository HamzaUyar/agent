"""Rapor doğrulama yaklaşımlarını doğru cevap setiyle (eval/report_gold.json) karşılaştırır.

Yaklaşımlar:
    B  genişletilmiş kurallar (reports_v2/rules.py)
    C  tek LLM çağrısı (reports_v2/agents.py)
    D  çok ajanlı ekip: görsel müfettiş, müfettiş, şüpheci, hakem, gün analisti

    python -m scripts.eval_reports B C D --package ../../stage2 --claims claims.json \\
        --detections detections.json --out sonuc/
LLM cevapları `--out/cache.json`'a yazılır; tekrar çalıştırmak ücretsizdir.
"""

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.data_package import load_claims
from app.reports_v2 import agents, context, rules
from app.reports_v2 import evidence as ev

_LIE = ("contradicts", "partial")
GOLD = Path(__file__).resolve().parents[1] / "eval" / "report_gold.json"


def run_b(args: argparse.Namespace, data: ev.Data) -> dict[int, dict[str, Any]]:
    claims = {c.claim_id: c.claim for c in load_claims(args.claims)}
    return {
        i: rules.judge(context.add_context(data, ev.dossier(data, i)), claims[i]).model_dump()
        for i in range(len(data.package.reports))
    }


def run_llm(args: argparse.Namespace, data: ev.Data, approach: str) -> dict[int, dict[str, Any]]:
    from app.llm.client import build_router

    router = build_router(check_budget=True)
    cache = agents.Cache(args.out / "cache.json")
    ids = list(range(len(data.package.reports)))[: args.limit or None]

    def one(i: int) -> tuple[int, dict[str, Any]]:
        d = context.add_context(data, ev.dossier(data, i))
        if args.compact:
            d = ev.compact(d)
        try:
            if approach == "C":
                v, _, _ = agents.single_llm(router, cache, d)
                return i, v.model_dump()
            v, trace = agents.team(router, cache, data, d)
            return i, {**v.model_dump(), "trace": trace}
        except Exception as exc:
            return i, {
                "verdict": "error",
                "reasoning": str(exc)[:300],
                "harm": "none",
                "dangerous_reassurance": False,
            }

    with ThreadPoolExecutor(args.workers) as pool:
        results = dict(pool.map(one, ids))
    if approach == "D" and not args.limit:
        rows = [
            {
                "id": i,
                "saat": data.package.reports[i].time.strftime("%H:%M"),
                "kaynak": data.package.reports[i].source.value,
                "metin": data.package.reports[i].text,
                "on_karar": r["verdict"],
                "gerekce": r.get("reasoning", "")[:160],
            }
            for i, r in results.items()
        ]
        review = agents.day_review(router, cache, rows)
        for rev in review.revisions:
            if rev.report_id in results and rev.related_ids:
                r = results[rev.report_id]
                r["day_revision"] = {
                    "from": r["verdict"],
                    "reason": rev.reason,
                    "related": rev.related_ids,
                }
                r["verdict"] = rev.new_verdict
    print(f"{approach}: yeni LLM çağrısı {cache.calls}")
    return results


def score(pred: dict[int, dict[str, Any]], gold: list[dict[str, Any]]) -> dict[str, Any]:
    g = {r["id"]: r for r in gold}
    p = {i: pred.get(i, {"verdict": "(yok)"})["verdict"] for i in g}
    lies = [i for i, r in g.items() if r["verdict"] == "contradicts"]
    danger = [i for i in lies if g[i]["harm"] == "lowers_risk"]
    truth = [i for i, r in g.items() if r["verdict"] == "consistent"]
    return {
        "yalan_yakalanan": f"{sum(p[i] == 'contradicts' for i in lies)}/{len(lies)}",
        "yalan_yakalanan_kismen_dahil": f"{sum(p[i] in _LIE for i in lies)}/{len(lies)}",
        "tehlikeli_guvence_yakalanan": f"{sum(p[i] == 'contradicts' for i in danger)}"
        f"/{len(danger)}",
        "dogru_rapora_celiskili_deme": f"{sum(p[i] == 'contradicts' for i in truth)}/{len(truth)}",
        "tam_isabet": f"{sum(p[i] == g[i]['verdict'] for i in g)}/{len(g)}",
        "hata": sum(v == "error" for v in p.values()),
        "baglam_bayraklari": _flags(pred, gold),
        "dagilim": dict(Counter(p.values())),
    }


def _flags(pred: dict[int, dict[str, Any]], gold: list[dict[str, Any]]) -> str:
    want = {r["id"]: set(r.get("flags", [])) for r in gold}
    got = {i: set(pred.get(i, {}).get("context_flags", [])) for i in want}
    tp = sum(len(want[i] & got[i]) for i in want)
    extra = sum(len(got[i] - want[i]) for i in want)
    return f"beklenen {sum(map(len, want.values()))}, bulunan {tp}, fazladan {extra}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("approaches", nargs="+", choices=["B", "C", "D"])
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--claims", type=Path, required=True)
    ap.add_argument("--detections", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--compact", action="store_true", help="LLM'e kısa kanıt dosyası gönder")
    ap.add_argument("--limit", type=int, default=0, help="Yalnızca ilk N rapor (deneme)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    gold = json.loads(GOLD.read_text(encoding="utf-8"))["reports"]
    if args.limit:
        gold = gold[: args.limit]
    data = ev.load(args.package, args.detections)
    summary = {}
    for a in args.approaches:
        t = time.time()
        pred = run_b(args, data) if a == "B" else run_llm(args, data, a)
        (args.out / f"{a}.json").write_text(
            json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        summary[a] = {**score(pred, gold), "sure_sn": round(time.time() - t)}
        print(a, json.dumps(summary[a], ensure_ascii=False))
    (args.out / "ozet.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
