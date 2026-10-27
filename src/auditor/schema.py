"""Structured representation of a parsed prerequisite requirement.

A requirement is stored in conjunctive normal form (CNF): every group must be
satisfied (AND), and a group is satisfied by any one of its options (OR).

    "CSC 210 and (MATH 243 or MATH 223)"
    -> groups = [[CSC 210], [MATH 243, MATH 223]]

This matches the representation of the Mendeley reference data, so a parser's
output can be compared with it directly. Known limit: CNF cannot express
"(A and B) or C" without rewriting it as "(A or C) and (B or C)".
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Timing(str, Enum):
    before = "before"                              # must be completed first
    concurrent = "concurrent"                      # must be taken at the same time
    before_or_concurrent = "before_or_concurrent"  # either is fine


class CourseRequirement(BaseModel):
    course: str = Field(description="Course code exactly as written in the text, e.g. 'MATH 243'.")
    timing: Timing = Field(default=Timing.before, description="When the course must be taken.")
    min_grade: Optional[str] = Field(default=None, description="Minimum grade if stated, e.g. 'C'. Null if not stated.")


class Group(BaseModel):
    options: list[CourseRequirement] = Field(
        min_length=1, description="Alternatives: satisfying ANY one option satisfies the group."
    )


class PrereqParse(BaseModel):
    groups: list[Group] = Field(
        default_factory=list, description="ALL groups must be satisfied. Empty if no course is required."
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Non-course requirements, quoted from the text, e.g. 'consent of instructor', 'junior standing'.",
    )
    needs_review: bool = Field(
        default=False, description="True if the text is ambiguous and the structure had to be guessed."
    )
    review_reason: Optional[str] = Field(default=None, description="Why review is needed, if needs_review is true.")


_NON_CODE = re.compile(r"[^A-Z0-9/]")


def norm_code(code: str) -> str:
    """Normalize a course code for comparison: 'math 243', 'MATH-243.' -> 'MATH243'."""
    return _NON_CODE.sub("", code.upper())


def structure(parse: PrereqParse) -> frozenset:
    """Order-insensitive course structure: a set of groups, each a set of normalized codes."""
    return frozenset(frozenset(norm_code(o.course) for o in g.options) for g in parse.groups)


def full_structure(parse: PrereqParse) -> frozenset:
    """Like structure(), but each option also carries its timing and minimum grade."""
    return frozenset(
        frozenset((norm_code(o.course), o.timing.value, (o.min_grade or "").upper()) for o in g.options)
        for g in parse.groups
    )
