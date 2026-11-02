"""Planted-defect evaluation of the audit checks.

For several real catalogs (Mendeley reference parses), plant known defects in a copy, re-run the
audit, and measure: did each planted defect get found (recall), and did anything new appear that
the planted defects don't explain (false alarms)?

  python scripts/eval_audit.py            # writes results/audit_eval_summary.json
"""
import copy
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditor.audit import audit, subject  # noqa: E402
from auditor.catalog import load_catalog  # noqa: E402
from auditor.data import ROOT, load_courses, load_reference_parses  # noqa: E402
from auditor.schema import CourseRequirement, Group, Timing, norm_code  # noqa: E402

CATALOGS = ["aus@2023-2024", "uaeu@2025_2026", "qu@2024-2025", "khalifa@2025-2026", "kfupm@2025-2026"]
SEEDS = range(5)
PER_TYPE = 4


def sole_edges(cat):
    """(prereq, course) where prereq is a single-option, taken-before, existing course.
    (A loop through a corequisite is not blocking: both can be taken together.)"""
    return [(norm_code(g.options[0].course), k) for k, c in cat.items() for g in c.parse.groups
            if len(g.options) == 1 and g.options[0].timing == Timing.before
            and norm_code(g.options[0].course) in cat and norm_code(g.options[0].course) != k]


def plant(cat, rng):
    cat = copy.deepcopy(cat)
    used, planted = set(), []
    keys = sorted(cat)

    def free(*ks):
        return not (set(ks) & used)

    # 1. a requirement on a course that does not exist
    for k in rng.sample(keys, len(keys)):
        if len([p for p in planted if p[0] == "missing_course"]) == PER_TYPE:
            break
        fake = f"{subject(k)}9{rng.randint(10, 99)}Z"
        if free(k) and fake not in cat:
            cat[k].parse.groups.append(Group(options=[CourseRequirement(course=fake)]))
            used.add(k); planted.append(("missing_course", k, fake))
    # 2. a required course removed from the catalog
    edges = sole_edges(cat); rng.shuffle(edges)
    for pre, k in edges:
        if len([p for p in planted if p[0] == "removed"]) == PER_TYPE:
            break
        if free(pre, k) and pre in cat:
            del cat[pre]; used.update({pre, k}); planted.append(("removed", k, pre))
    # 3. a loop: make a prerequisite require the course that depends on it
    edges = sole_edges(cat); rng.shuffle(edges)
    for pre, k in edges:
        if len([p for p in planted if p[0] == "cycle"]) == PER_TYPE:
            break
        if free(pre, k):
            cat[pre].parse.groups.append(Group(options=[CourseRequirement(course=cat[k].code)]))
            used.update({pre, k}); planted.append(("cycle", k, pre))
    # 4. a course that requires itself
    for k in rng.sample(sorted(cat), len(cat)):
        if len([p for p in planted if p[0] == "self_reference"]) == PER_TYPE:
            break
        if free(k):
            cat[k].parse.groups.append(Group(options=[CourseRequirement(course=cat[k].code)]))
            used.add(k); planted.append(("self_reference", k, k))
    return cat, planted


def found(planted, findings):
    kind, course, other = planted
    for f in findings:
        fc = norm_code(f.course)
        rel = {norm_code(r) for r in f.related}
        if kind == "missing_course" and f.check == "missing_course" and fc == course and other in rel:
            return True
        if kind == "removed" and f.check in ("missing_course", "renumbered") and fc == course and other in rel:
            return True
        if kind == "cycle" and f.check == "cycle" and {course, other} <= rel | {fc}:
            return True
        if kind == "self_reference" and f.check == "self_reference" and fc == course:
            return True
    return False


def signature(f):
    return (f.check, norm_code(f.course), tuple(sorted(norm_code(r) for r in f.related)))


def main():
    courses = load_courses()
    refs = load_reference_parses(courses)
    hits, totals, false_alarms, chain_shifts, base_n = defaultdict(int), defaultdict(int), 0, 0, 0
    for ds in CATALOGS:
        courses_list, earlier = load_catalog(ds, courses, refs=refs)
        cat = {norm_code(c.code): c for c in courses_list}
        base = {signature(f) for f in audit(cat.values(), earlier)}
        base_n += len(base)
        for seed in SEEDS:
            mod, planted = plant(cat, random.Random(f"{ds}-{seed}"))
            findings = audit(mod.values(), earlier)
            for p in planted:
                totals[p[0]] += 1
                hits[p[0]] += found(p, findings)
            touched = {p[1] for p in planted} | {p[2] for p in planted}
            for f in findings:
                if signature(f) not in base:
                    if f.check == "long_chain":   # planted edges lengthen downstream chains: expected
                        chain_shifts += 1
                        continue
                    explained = norm_code(f.course) in touched or {norm_code(r) for r in f.related} & touched
                    false_alarms += not explained
    summary = {
        "catalogs": CATALOGS, "seeds": len(SEEDS), "defects_per_type_per_run": PER_TYPE,
        "recall": {k: round(hits[k] / totals[k], 4) for k in totals},
        "planted": dict(totals),
        "false_alarms": false_alarms,
        "downstream_long_chain_notices": chain_shifts,
        "baseline_findings_total": base_n,
    }
    out = ROOT / "results" / "audit_eval_summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
