"""Audit catalogs and write a findings file and a readable report per catalog.

  python scripts/run_audit.py --all                      # every catalog, Mendeley reference parses
  python scripts/run_audit.py --dataset aus@2023-2024 --parser muse   # parse with Muse Spark first

Writes results/audit/<dataset>.json and results/audit/<dataset>.md
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditor.audit import audit, report_markdown  # noqa: E402
from auditor.catalog import latest_editions, load_catalog  # noqa: E402
from auditor.data import ROOT, load_courses, load_reference_parses  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dataset")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--parser", choices=["silver", "muse"], default="silver")
    ap.add_argument("--max-terms", type=int, default=8)
    args = ap.parse_args()

    courses = load_courses()
    datasets = latest_editions(courses) if args.all else [args.dataset]
    refs = load_reference_parses(courses) if args.parser == "silver" else None
    parse_fn = None
    if args.parser == "muse":
        from auditor.parser import MuseParser
        mp = MuseParser()
        parse_fn = lambda p, c: mp.parse(p, c).parsed  # noqa: E731

    out = ROOT / "results" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    totals = {}
    for ds in datasets:
        cat, earlier = load_catalog(ds, courses, parse_fn=parse_fn, refs=refs)
        findings = audit(cat, earlier, max_terms=args.max_terms)
        institution = courses.loc[courses.dataset == ds, "institution"].iloc[0]
        name = f"{institution} ({ds}, {args.parser} parses)"
        (out / f"{ds}.json").write_text(json.dumps([asdict(f) for f in findings], indent=1))
        (out / f"{ds}.md").write_text(report_markdown(name, findings, len(cat)))
        sev = {s: sum(f.severity == s for f in findings) for s in ("blocking", "warning", "info")}
        totals[ds] = {"courses": len(cat), **sev}
        print(f"{ds:22} {len(cat):5} courses  blocking={sev['blocking']:3} warning={sev['warning']:3} info={sev['info']:3}")
    (out / f"summary_{args.parser}.json").write_text(json.dumps(totals, indent=1))


if __name__ == "__main__":
    main()
