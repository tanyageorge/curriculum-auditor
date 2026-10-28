"""Deterministic checks on a parser's output. The model reads; code verifies.

The main guardrail is grounding: every course code in the output must be traceable
to the input text, so the parser cannot invent prerequisites.
"""
from __future__ import annotations

import re

from .schema import PrereqParse, norm_code

_CODE_SPLIT = re.compile(r"^([A-Z/&]+?)(\d.*)$")
_WORDS = re.compile(r"[A-Za-z/&]+")
_NUMBERS = re.compile(r"\d+[A-Za-z]{0,3}")


def is_grounded(course: str, text: str) -> bool:
    """True if `course` can be traced to `text`.

    Accepts an exact match after normalization ('MATH 243' in '...MATH243...'), or a
    subject + number that both appear in the text, which covers shorthand such as
    'MATH 243 or 223' -> 'MATH 223' and cross-lists like 'ACM 95/100' -> 'ACM 100'.
    """
    code = norm_code(course)
    if not code:
        return False
    if code in norm_code(text):
        return True
    m = _CODE_SPLIT.match(code)
    if not m:
        return False
    subject, number = m.groups()
    words = {norm_code(w) for w in _WORDS.findall(text)}
    numbers = {n.upper() for n in _NUMBERS.findall(text)}
    subject_ok = subject in words or any(subject in w.split("/") for w in words)
    return subject_ok and number in numbers


def check(parse: PrereqParse, text: str) -> list[str]:
    """Return a list of problems with `parse` as a reading of `text` (empty = passes)."""
    issues = []
    for g_i, group in enumerate(parse.groups):
        seen = set()
        for opt in group.options:
            code = norm_code(opt.course)
            if not is_grounded(opt.course, text):
                issues.append(f"course '{opt.course}' does not appear in the text")
            if code in seen:
                issues.append(f"course '{opt.course}' is listed twice in group {g_i + 1}")
            seen.add(code)
    if parse.needs_review and not (parse.review_reason or "").strip():
        issues.append("needs_review is true but review_reason is empty")
    return issues
