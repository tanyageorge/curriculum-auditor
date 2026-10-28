"""Scoring a predicted parse against a reference parse."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from .schema import PrereqParse, full_structure, norm_code, structure


def _codes(p: PrereqParse) -> set[str]:
    return {norm_code(o.course) for g in p.groups for o in g.options}


def compare(pred: Optional[PrereqParse], ref: PrereqParse) -> dict:
    """Per-course scores. `pred` is None when the parser produced nothing usable."""
    if pred is None:
        return {"structure_exact": 0, "full_exact": 0, "tp": 0, "fp": 0, "fn": len(_codes(ref)),
                "flagged": 0, "ref_flagged": int(ref.needs_review)}
    p, r = _codes(pred), _codes(ref)
    return {
        "structure_exact": int(structure(pred) == structure(ref)),       # same AND/OR structure
        "full_exact": int(full_structure(pred) == full_structure(ref)),  # + timing and grades
        "tp": len(p & r), "fp": len(p - r), "fn": len(r - p),            # course level
        "flagged": int(pred.needs_review),
        "ref_flagged": int(ref.needs_review),
    }


def summarize(rows: Iterable[dict], by: Optional[str] = None) -> dict:
    """Aggregate per-course rows (from compare(), optionally carrying a grouping key)."""
    groups = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        if by:
            groups[row[by]].append(row)
    out = {}
    for name, rs in groups.items():
        n = len(rs)
        tp, fp, fn = (sum(r[k] for r in rs) for k in ("tp", "fp", "fn"))
        unflagged = [r for r in rs if not r["flagged"]]
        out[name] = {
            "n": n,
            "structure_exact": round(sum(r["structure_exact"] for r in rs) / n, 4),
            "full_exact": round(sum(r["full_exact"] for r in rs) / n, 4),
            "course_precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "course_recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "flag_rate": round((n - len(unflagged)) / n, 4),
            # Is flagging useful? Accuracy on what the parser did NOT flag should be higher.
            "structure_exact_unflagged": round(sum(r["structure_exact"] for r in unflagged) / len(unflagged), 4)
            if unflagged else None,
        }
    return out
