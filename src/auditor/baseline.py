"""A rule-based baseline parser (no LLM), to show what the model adds.

Deliberately simple, like a typical regex scraper: split on 'and' / ',' / ';' into groups,
'or' into alternatives, pull out codes, grades and a few condition phrases.
"""
from __future__ import annotations

import re

from .schema import CourseRequirement, Group, PrereqParse, Timing

CODE = re.compile(r"\b([A-Z][A-Za-z]{1,6}(?:/[A-Za-z]{1,6})*)\s?-?(\d{1,4}[A-Za-z]?)\b")
GRADE = re.compile(r"(?:minimum grade(?: of)?|grade of)\s+([A-D][+-]?)|\b([A-D][+-]?) or (?:better|higher)", re.I)
CONDITION = re.compile(
    r"(consent of [a-z ]+|permission of [a-z ]+|instructor'?s permission|"
    r"(?:freshman|sophomore|junior|senior|graduate) standing|department(?:al)? approval|or equivalent)",
    re.I,
)
AND_SPLIT = re.compile(r"\band\b|;|,(?!\s*or\b)", re.I)
OR_SPLIT = re.compile(r"\bor\b", re.I)


def parse(prereq: str, coreq: str = "") -> PrereqParse:
    grade_m = GRADE.search(prereq)
    grade = (grade_m.group(1) or grade_m.group(2)).upper() if grade_m else None
    groups = []
    for chunk in AND_SPLIT.split(prereq):
        options = []
        for alt in OR_SPLIT.split(chunk):
            for subj, num in CODE.findall(alt):
                options.append(CourseRequirement(course=f"{subj} {num}", min_grade=grade))
        if options:
            groups.append(Group(options=options))
    for subj, num in CODE.findall(coreq):
        groups.append(Group(options=[CourseRequirement(course=f"{subj} {num}", timing=Timing.concurrent)]))
    conditions = [m.group(0) for m in CONDITION.finditer(prereq + " " + coreq)]
    return PrereqParse(groups=groups, conditions=conditions)
