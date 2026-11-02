"""Assemble a catalog edition for auditing: its courses, their parses, and earlier editions."""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from .audit import Course
from .data import load_courses, load_reference_parses
from .schema import PrereqParse, norm_code


def latest_editions(courses: pd.DataFrame) -> list[str]:
    """The most recent dataset (slug@edition) of each catalog, excluding Caltech (never parsed)."""
    df = courses[~courses.institution.str.startswith("California")]
    df = df.assign(slug=df.dataset.str.split("@").str[0])
    return sorted(df.sort_values("edition").groupby("slug")["dataset"].last())


def load_catalog(dataset: str, courses: Optional[pd.DataFrame] = None,
                 parse_fn: Optional[Callable[[str, str], Optional[PrereqParse]]] = None,
                 refs: Optional[dict] = None) -> tuple[list[Course], dict[str, str]]:
    """Courses of one edition plus {old code: note} for codes only in earlier editions.

    parse_fn(prereq, coreq) supplies parses (e.g. Muse Spark); default = Mendeley reference parses.
    """
    courses = load_courses() if courses is None else courses
    ed = courses[(courses.dataset == dataset) & ~courses.ambiguous_id]
    if parse_fn is None and refs is None:
        refs = load_reference_parses(courses)
    refs = refs or {}
    out = []
    for r in ed.itertuples(index=False):
        if parse_fn is not None and r.has_prereq_text:
            parse = parse_fn(r.prerequisites_raw, r.corequisites_raw) or PrereqParse()
        else:
            parse = refs.get(r.course_id, PrereqParse())
        raw = r.prerequisites_raw + (f" | Corequisite: {r.corequisites_raw}" if r.corequisites_raw else "")
        out.append(Course(code=r.code, title=r.title, parse=parse, raw=raw))

    # earlier editions of the same catalog -> codes that disappeared (and what they became)
    slug, edition = dataset.split("@")
    current = {norm_code(c) for c in ed.code}
    canon_now = dict(zip(ed.canonical_code, ed.code))
    earlier = courses[(courses.dataset.str.split("@").str[0] == slug) & (courses.edition < edition)]
    earlier_codes: dict[str, str] = {}
    for r in earlier.sort_values("edition").itertuples(index=False):
        k = norm_code(r.code)
        if k not in current:
            now = canon_now.get(r.canonical_code)
            earlier_codes[k] = f"the {r.edition} catalog" + (f" (now {now})" if now and norm_code(now) != k else "")
    return out, earlier_codes
