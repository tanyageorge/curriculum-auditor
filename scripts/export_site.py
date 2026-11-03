"""Export precomputed catalogs, findings and eval results as static JSON for the website.

  python scripts/export_site.py     # writes site/data/*.json

Mendeley catalogs use the dataset's reference parses (CC BY 4.0); UIUC uses Muse Spark parses
from scripts/parse_uiuc.py (UIUC data CC BY-SA 4.0). The site needs no server and no API key.
"""
import glob
import html
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditor.audit import Course, audit  # noqa: E402
from auditor.catalog import latest_editions, load_catalog  # noqa: E402
from auditor.data import ROOT, load_courses, load_reference_parses  # noqa: E402
from auditor.notation import to_text  # noqa: E402
from auditor.schema import PrereqParse, norm_code  # noqa: E402

OUT = ROOT / "site" / "data"
TIMING_CODE = {"before": "", "concurrent": "c", "before_or_concurrent": "p"}


def clean(s) -> str:
    return html.unescape(s) if isinstance(s, str) else ""


def course_rows(courses):
    rows = []
    for c in courses:
        p = c.parse
        rows.append({
            "k": norm_code(c.code), "c": c.code, "t": clean(c.title), "r": clean(c.raw),
            "p": to_text(p) if (p.groups or p.conditions) else "",
            "g": [[[norm_code(o.course), TIMING_CODE[o.timing.value]] for o in g.options] for g in p.groups],
            "nr": p.review_reason if p.needs_review else None,
        })
    return rows


def write_catalog(ds, name, source, courses, findings, complete=True):
    payload = {"id": ds, "name": name, "source": source, "complete": complete, "courses": course_rows(courses),
               "findings": [asdict(f) for f in findings]}
    (OUT / f"{ds.replace('@', '_')}.json").write_text(json.dumps(payload, separators=(",", ":")))
    sev = {s: sum(f.severity == s for f in findings) for s in ("blocking", "warning", "info")}
    return {"id": ds, "file": ds.replace("@", "_") + ".json", "name": name, "source": source, "courses": len(courses), **sev}


def latest(pattern):
    files = sorted(glob.glob(str(ROOT / "results" / pattern)))
    return json.loads(Path(files[-1]).read_text()) if files else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = []

    uiuc = ROOT / "results" / "uiuc_parsed.json"
    if uiuc.exists():
        courses = [Course(code=x["code"], title=x["title"], raw=x["raw"], parse=PrereqParse.model_validate(x["parse"]))
                   for x in json.loads(uiuc.read_text())]
        index.append(write_catalog("uiuc@2026-spring", "University of Illinois Urbana-Champaign, Spring 2026",
                                   "Prerequisites parsed by Muse Spark (this project)", courses,
                                   audit(courses, complete_catalog=False), complete=False))
    else:
        print("note: results/uiuc_parsed.json not found; run scripts/parse_uiuc.py to include UIUC")

    all_courses = load_courses()
    refs = load_reference_parses(all_courses)
    for ds in latest_editions(all_courses):
        courses, earlier = load_catalog(ds, all_courses, refs=refs)
        inst = all_courses.loc[all_courses.dataset == ds, "institution"].iloc[0]
        index.append(write_catalog(ds, f"{inst}, {ds.split('@')[1]}", "Prerequisite parses from the Mendeley research dataset",
                                   courses, audit(courses, earlier)))
        print(f"  {ds}: {len(courses)} courses")

    evals = {
        "gold_muse": latest("*_muse-minimal_gold_summary.json"),
        "gold_baseline": latest("*_baseline_gold_summary.json"),
        "dev_muse": latest("*muse-spark-1.3-minimal_dev_summary.json"),
        "dev_baseline": latest("*_baseline_dev_summary.json"),
        "ensemble": latest("*ensemble*_dev_summary.json"),
        "audit_planted": json.loads((ROOT / "results" / "audit_eval_summary.json").read_text()),
    }
    (OUT / "index.json").write_text(json.dumps({"catalogs": index, "evals": evals}, indent=1))
    total = sum(f.stat().st_size for f in OUT.glob("*.json"))
    print(f"wrote {len(index)} catalogs to site/data ({total / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
