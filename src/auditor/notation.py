"""A short, human-editable text notation for PrereqParse, used for hand-labeling.

    NONE
    CSC 210 AND (MATH 243 OR MATH 223)
    MATH 210 [min C] AND PHYS 141 [concurrent] COND: consent of instructor; junior standing
    COND: senior standing

Rules
- Groups are joined by AND; alternatives inside a group by OR (parentheses optional).
- Optional tags in brackets after a course, comma-separated:
    [min C]               minimum grade
    [concurrent]          must be taken at the same time
    [prior or concurrent] may be taken before or at the same time
- Non-course requirements go after "COND:", separated by ";".
- AND / OR / COND are case-insensitive.
"""
from __future__ import annotations

import re

from .schema import CourseRequirement, Group, PrereqParse, Timing

_COND_SPLIT = re.compile(r"\bCOND:", re.IGNORECASE)
# split on AND / OR only outside [tags], since "[prior or concurrent]" contains "or"
_AND = re.compile(r"\s+AND\s+(?![^\[]*\])", re.IGNORECASE)
_OR = re.compile(r"\s+OR\s+(?![^\[]*\])", re.IGNORECASE)
_OPTION = re.compile(r"^(?P<code>[^\[\]]+?)\s*(?:\[(?P<tags>[^\]]*)\])?$")

_TIMING_TAGS = {
    "concurrent": Timing.concurrent,
    "co": Timing.concurrent,
    "coreq": Timing.concurrent,
    "prior or concurrent": Timing.before_or_concurrent,
    "pre/co": Timing.before_or_concurrent,
}
_TIMING_TEXT = {Timing.concurrent: "concurrent", Timing.before_or_concurrent: "prior or concurrent"}


def _parse_option(text: str) -> CourseRequirement:
    m = _OPTION.match(text.strip())
    if not m or not m.group("code").strip():
        raise ValueError(f"cannot read course option: {text!r}")
    timing, grade = Timing.before, None
    for tag in filter(None, (t.strip().lower() for t in (m.group("tags") or "").split(","))):
        if tag.startswith("min "):
            grade = tag[4:].strip().upper()
        elif tag in _TIMING_TAGS:
            timing = _TIMING_TAGS[tag]
        else:
            raise ValueError(f"unknown tag [{tag}] in {text!r}")
    return CourseRequirement(course=m.group("code").strip(), timing=timing, min_grade=grade)


def from_text(text: str) -> PrereqParse:
    text = (text or "").strip()
    if not text or text.upper() == "NONE":
        return PrereqParse()
    parts = _COND_SPLIT.split(text, maxsplit=1)
    course_part = parts[0].strip()
    conditions = [c.strip() for c in parts[1].split(";") if c.strip()] if len(parts) > 1 else []
    groups = []
    if course_part and course_part.upper() != "NONE":
        for g in _AND.split(course_part):
            g = g.strip()
            if g.startswith("(") and g.endswith(")"):
                g = g[1:-1]
            groups.append(Group(options=[_parse_option(o) for o in _OR.split(g)]))
    return PrereqParse(groups=groups, conditions=conditions)


def _option_text(o: CourseRequirement) -> str:
    tags = []
    if o.min_grade:
        tags.append(f"min {o.min_grade}")
    if o.timing in _TIMING_TEXT:
        tags.append(_TIMING_TEXT[o.timing])
    return o.course + (f" [{', '.join(tags)}]" if tags else "")


def to_text(parse: PrereqParse) -> str:
    groups = []
    for g in parse.groups:
        opts = [_option_text(o) for o in g.options]
        groups.append(opts[0] if len(opts) == 1 else "(" + " OR ".join(opts) + ")")
    text = " AND ".join(groups)
    if parse.conditions:
        text = (text + " " if text else "") + "COND: " + "; ".join(parse.conditions)
    return text or "NONE"
