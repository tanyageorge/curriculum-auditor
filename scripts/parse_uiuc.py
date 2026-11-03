"""Parse the whole UIUC Spring 2026 catalog with Muse Spark, then audit it.

  python scripts/parse_uiuc.py            # ~2,700 prerequisite texts, ~$7, ~5-10 min; resumable (cached)

UIUC is not in the Mendeley corpus and was never used for tuning: this is the out-of-sample demo.
There are no labels for it, so it is not scored.

Writes results/uiuc_parsed.json (courses + parses) and results/audit/uiuc@2026-spring.{json,md}.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditor.audit import Course, audit, report_markdown  # noqa: E402
from auditor.data import ROOT, load_uiuc  # noqa: E402
from auditor.parser import MuseParser  # noqa: E402
from auditor.schema import PrereqParse  # noqa: E402

DATASET = "uiuc@2026-spring"


def main():
    u = load_uiuc()
    mp = MuseParser()
    todo = [(r.code, r.prerequisites_raw) for r in u.itertuples() if r.prerequisites_raw]
    done = [0]

    def work(item):
        code, text = item
        res = mp.parse(text)
        done[0] += 1
        if done[0] % 200 == 0:
            print(f"  {done[0]}/{len(todo)} parsed")
        return code, res

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = dict(ex.map(work, todo))
    errors = [c for c, r in results.items() if r.error]
    print(f"parsed {len(results) - len(errors)}/{len(results)}; API errors: {len(errors)} (re-run to retry)")

    courses = []
    for r in u.itertuples():
        res = results.get(r.code)
        parse = res.parsed if res and res.parsed else PrereqParse()
        courses.append(Course(code=r.code, title=r.Name, parse=parse, raw=r.prerequisites_raw))
    findings = audit(courses, complete_catalog=False)   # one term's offerings, not the full catalog

    out = ROOT / "results"
    (out / "uiuc_parsed.json").write_text(json.dumps(
        [{"code": c.code, "title": c.title, "raw": c.raw, "parse": c.parse.model_dump(mode="json")} for c in courses]))
    (out / "audit").mkdir(exist_ok=True)
    (out / "audit" / f"{DATASET}.json").write_text(json.dumps([asdict(f) for f in findings], indent=1))
    (out / "audit" / f"{DATASET}.md").write_text(
        report_markdown(f"University of Illinois Urbana-Champaign ({DATASET}, Muse Spark parses)", findings, len(courses)))
    sev = {s: sum(f.severity == s for f in findings) for s in ("blocking", "warning", "info")}
    flagged = sum(1 for c in courses if c.parse.needs_review)
    print(f"{len(courses)} courses; flagged for review: {flagged}; findings: {sev}")


if __name__ == "__main__":
    main()
