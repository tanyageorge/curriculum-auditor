"""Loaders for the Mendeley curriculum corpus, the UIUC catalog, and hand-labeled gold sets.

Data files are not part of this repository; see README.md for where to download them.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

from .notation import from_text
from .schema import CourseRequirement, Group, PrereqParse, Timing

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MENDELEY = DATA / "mendeley"
UIUC = DATA / "uiuc"

# Caltech is in the corpus but its prerequisites were never parsed, so it has no reference.
NO_REFERENCE_INSTITUTIONS = {"California Institute of Technology"}


def _clean(s) -> str:
    return "" if pd.isna(s) else str(s).strip()


# --------------------------------------------------------------------------- Mendeley

def load_courses() -> pd.DataFrame:
    """One row per course per catalog edition, with a unique `course_id` = 'dataset::code'.

    Course ids that appear more than once in an edition (the corpus notes reused codes)
    are flagged with `ambiguous_id` so they can be excluded from evaluation.
    """
    df = pd.read_csv(MENDELEY / "courses.csv", dtype=str, keep_default_na=False, na_values=[""])
    df["course_id"] = df["dataset"] + "::" + df["code"]
    df["prerequisites_raw"] = df["prerequisites_raw"].map(_clean)
    df["corequisites_raw"] = df["corequisites_raw"].map(_clean)
    df["has_prereq_text"] = df["prerequisites_raw"] != ""
    df["ambiguous_id"] = df.duplicated("course_id", keep=False)
    return df


def load_edges() -> pd.DataFrame:
    e = pd.read_csv(MENDELEY / "prereq_edges.csv", dtype=str, keep_default_na=False, na_values=[""])
    e["course_id"] = e["dataset"] + "::" + e["target_course"]
    e["group_index"] = e["group_index"].astype(int)
    return e


def load_reference_parses(courses: Optional[pd.DataFrame] = None) -> dict[str, PrereqParse]:
    """Mendeley's parse of each course, keyed by course_id, as PrereqParse objects.

    Only courses with a usable reference are included: not Caltech, not 'unresolved',
    and either parsed (prereq_source grammar/claude) or carrying at least one edge.
    Note: most of these parses were produced with LLM assistance by the dataset authors,
    so they are a *silver* reference, not ground truth.
    """
    courses = load_courses() if courses is None else courses
    courses = courses[~courses["ambiguous_id"]]
    edges = load_edges()
    edges_by_course = {cid: sub for cid, sub in edges.groupby("course_id", sort=False)}

    refs: dict[str, PrereqParse] = {}
    for row in courses.itertuples(index=False):
        if not row.has_prereq_text or row.institution in NO_REFERENCE_INSTITUTIONS:
            continue
        source = _clean(row.prereq_source)
        sub = edges_by_course.get(row.course_id)
        if source == "unresolved" or (source not in {"grammar", "claude"} and sub is None):
            continue
        groups = []
        if sub is not None:
            for _, g in sub.sort_values("group_index").groupby("group_index", sort=True):
                groups.append(Group(options=[
                    CourseRequirement(
                        course=r.source_prereq,
                        timing=Timing(_clean(r.timing) or "before"),
                        min_grade=_clean(r.min_grade) or None,
                    )
                    for r in g.itertuples(index=False)
                ]))
        cond = _clean(row.conditions)
        refs[row.course_id] = PrereqParse(groups=groups, conditions=[cond] if cond else [])
    return refs


# --------------------------------------------------------------------------- difficulty

_SINGLE_CODE = re.compile(r"^[A-Za-z/&]{1,10}[ -]?\d{2,4}[A-Za-z]{0,3}\.?$")
_HARD_PATTERNS = re.compile(
    r"\bor\b|\(|;|concurren|co-?req|corequisite|either|one of|any of|equivalent", re.IGNORECASE
)


def difficulty(prereq: str, coreq: str = "", operator_stated: str = "True") -> str:
    """Rough difficulty tier of a prerequisite text: 'simple', 'moderate' or 'hard'.

    simple   = a single course code and nothing else
    hard     = alternatives, nesting, timing words, a corequisite, or no stated operator
    moderate = everything else (lists joined by 'and'/commas, grades, conditions)
    """
    p = prereq.strip()
    if coreq.strip() or str(operator_stated) == "False" or _HARD_PATTERNS.search(p):
        return "hard"
    if _SINGLE_CODE.match(p):
        return "simple"
    return "moderate"


def is_english(text: str) -> bool:
    return all(ord(ch) < 128 for ch in text)


# --------------------------------------------------------------------------- UIUC

_UIUC_PREREQ = re.compile(r"Prerequisites?:\s*(.+)$", re.IGNORECASE | re.DOTALL)


def load_uiuc() -> pd.DataFrame:
    """Unique UIUC courses with the prerequisite sentence pulled out of the description."""
    u = pd.read_csv(UIUC / "course-catalog.csv", dtype=str, keep_default_na=False)
    u = u.drop_duplicates(["Subject", "Number"], keep="last").copy()
    u["code"] = u["Subject"] + " " + u["Number"]
    u["prerequisites_raw"] = u["Description"].map(
        lambda d: (m.group(1).strip() if (m := _UIUC_PREREQ.search(d)) else "")
    )
    return u[["code", "Name", "Credit Hours", "Description", "prerequisites_raw"]].reset_index(drop=True)


# --------------------------------------------------------------------------- gold labels

GOLD_VERDICTS = {"ok", "fix", "ambiguous"}


def load_gold(path: Path, allow_partial: bool = False) -> dict[str, PrereqParse]:
    """Read a hand-labeled gold CSV (see evals/gold/ANNOTATION_GUIDE.md).

    ok        -> the proposed parse is correct
    fix       -> the 'corrected' column holds the correct parse
    ambiguous -> the text is genuinely ambiguous; 'corrected' holds the most reasonable
                 reading (or the proposed one if blank) and needs_review is set to True
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    gold: dict[str, PrereqParse] = {}
    for r in df.itertuples(index=False):
        verdict = r.verdict.strip().lower()
        if not verdict:
            if allow_partial:
                continue
            raise ValueError(f"{r.id}: no verdict")
        if verdict not in GOLD_VERDICTS:
            raise ValueError(f"{r.id}: unknown verdict {verdict!r}")
        text = r.corrected.strip() if verdict != "ok" and r.corrected.strip() else r.proposed
        if verdict == "fix" and not r.corrected.strip():
            raise ValueError(f"{r.id}: verdict 'fix' but 'corrected' is empty")
        parse = from_text(text)
        if verdict == "ambiguous":
            parse.needs_review = True
            parse.review_reason = r.notes.strip() or None
        gold[r.id] = parse
    return gold
