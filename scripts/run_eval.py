"""Evaluate a parser on dev (vs. the silver Mendeley reference) or on the gold test set.

Examples
  python scripts/run_eval.py --parser baseline --split dev --n 300
  python scripts/run_eval.py --parser muse --split dev --n 300 --effort low
  python scripts/run_eval.py --parser muse --split gold --confirm-test     # test set: run rarely

Writes results/<run>_summary.json (commit it) and results/raw/<run>.jsonl
(per-course detail, ignored by git).
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from auditor import baseline  # noqa: E402
from auditor.data import ROOT, load_courses, load_gold, load_reference_parses  # noqa: E402
from auditor.metrics import compare, summarize  # noqa: E402
from auditor.notation import to_text  # noqa: E402

PRICE_IN, PRICE_OUT = 1.25e-6, 4.25e-6   # USD per token, muse-spark-1.3 Standard list price
SAMPLE_SEED = 7                          # fixed, so every dev run scores the same courses
GOLD_PATH = ROOT / "evals" / "gold" / "test_gold_to_annotate.csv"


def dev_items(n: int, courses: pd.DataFrame) -> list:
    """An n-course dev sample, split evenly across difficulty tiers, scored against silver."""
    refs = load_reference_parses(courses)
    dev = pd.read_csv(ROOT / "evals" / "splits" / "dev.csv")
    dev = dev[dev.has_reference & dev.course_id.isin(refs)]
    per_tier = max(1, n // 3)
    sample = pd.concat(
        g.sample(n=min(per_tier, len(g)), random_state=SAMPLE_SEED) for _, g in dev.groupby("tier")
    )
    return [(cid, tier, refs[cid]) for cid, tier in zip(sample.course_id, sample.tier)]


def gold_items() -> list:
    gold = load_gold(GOLD_PATH)
    tiers = pd.read_csv(GOLD_PATH).set_index("id")["tier"]
    return [(cid, tiers[cid], ref) for cid, ref in gold.items()]


def fmt(v) -> str:
    return "  -  " if v is None else f"{v:.3f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", choices=["muse", "baseline"], required=True)
    ap.add_argument("--split", choices=["dev", "gold"], default="dev")
    ap.add_argument("--n", type=int, default=300, help="dev sample size (split evenly across tiers)")
    ap.add_argument("--effort", default="minimal", help="reasoning effort for muse: minimal|low|medium|high")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--confirm-test", action="store_true", help="required to score on the gold test set")
    args = ap.parse_args()

    if args.split == "gold" and not args.confirm_test:
        sys.exit("Scoring on the gold TEST set is meant to be rare. Re-run with --confirm-test.")

    all_courses = load_courses()
    courses = all_courses[~all_courses.ambiguous_id].set_index("course_id")
    items = dev_items(args.n, all_courses) if args.split == "dev" else gold_items()

    mp = None
    if args.parser == "muse":
        from auditor.parser import MuseParser
        mp = MuseParser(reasoning_effort=args.effort)
        label = f"muse-{mp.model}-{args.effort}"
    else:
        label = "baseline"

    def work(item):
        cid, tier, ref = item
        row = courses.loc[cid]
        prereq, coreq = row.prerequisites_raw, row.corequisites_raw
        res = None
        if mp is None:
            pred = baseline.parse(prereq, coreq)
        else:
            res = mp.parse(prereq, coreq)
            pred = res.parsed
        row_out = {
            "id": cid, "tier": tier, "prerequisites_raw": prereq, "corequisites_raw": coreq,
            "pred": to_text(pred) if pred else None, "ref": to_text(ref),
            "pred_review_reason": pred.review_reason if pred else None,
            **compare(pred, ref),
        }
        if res is not None:
            row_out.update(attempts=res.attempts, issues=res.issues, error=res.error, cached=res.cached,
                           input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                           reasoning_tokens=res.reasoning_tokens, latency_s=res.latency_s)
        return row_out

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(work, items))
    wall = time.time() - t0

    summary = {
        "run": f"{datetime.now():%Y%m%d-%H%M%S}_{label}_{args.split}",
        "parser": label,
        "split": args.split,
        "reference": "gold (hand-labeled)" if args.split == "gold" else "silver (Mendeley parses)",
        "n": len(rows),
        "wall_s": round(wall, 1),
        "scores": summarize(rows, by="tier"),
    }
    if mp is not None:
        fresh = [r for r in rows if not r["cached"]]
        tin = sum(r["input_tokens"] for r in rows)
        tout = sum(r["output_tokens"] for r in rows)
        summary["cost"] = {
            "usd_per_course": round((tin * PRICE_IN + tout * PRICE_OUT) / len(rows), 5),
            "usd_this_run": round(sum(r["input_tokens"] * PRICE_IN + r["output_tokens"] * PRICE_OUT
                                      for r in fresh), 4),
            "reasoning_share_of_output": round(sum(r["reasoning_tokens"] for r in rows) / tout, 3) if tout else None,
            "median_latency_s": float(pd.Series([r["latency_s"] for r in rows]).median()),
            "retried": sum(r["attempts"] > 1 for r in rows),
            "guardrail_failures": sum(bool(r["issues"]) for r in rows),
            "api_errors": sum(bool(r["error"]) for r in rows),
            "cached": len(rows) - len(fresh),
        }

    out = ROOT / "results"
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / f"{summary['run']}_summary.json").write_text(json.dumps(summary, indent=2))
    with (out / "raw" / f"{summary['run']}.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    if args.split == "gold":
        with (out / "test_runs.log").open("a") as f:
            f.write(summary["run"] + "\n")

    print(f"\n{label} on {args.split} ({summary['reference']}), n={len(rows)}, {wall:.0f}s")
    print(f"{'tier':10} {'n':>4} {'struct':>7} {'full':>7} {'prec':>6} {'recall':>7} {'flagged':>8} {'unflag-acc':>10}")
    for tier in ["all", "simple", "moderate", "hard"]:
        s = summary["scores"].get(tier)
        if s:
            print(f"{tier:10} {s['n']:>4} {fmt(s['structure_exact']):>7} {fmt(s['full_exact']):>7} "
                  f"{fmt(s['course_precision']):>6} {fmt(s['course_recall']):>7} {fmt(s['flag_rate']):>8} "
                  f"{fmt(s['structure_exact_unflagged']):>10}")
    if "cost" in summary:
        print("cost:", summary["cost"])
    print(f"\nsaved results/{summary['run']}_summary.json")


if __name__ == "__main__":
    main()
