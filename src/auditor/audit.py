"""Catalog audit: build the prerequisite graph from parsed requirements and find defects.

Everything here is deterministic code: the model only parses text; these checks are exact.

Checks
- missing_course   a prerequisite names a course that is not in the catalog (only for subjects
                   the catalog covers, so a partial catalog does not flood the report)
- renumbered       ...and that course existed in an earlier edition of the same catalog
- self_reference   a course lists itself as its own prerequisite
- cycle            courses that require each other through mandatory prerequisites
                   (a loop through an OR alternative is not blocking, so it is not flagged)
- long_chain       the shortest possible path to a course takes more terms than a degree allows

Severity: "blocking" = no student can satisfy the requirement as printed; "warning" = one OR
alternative is broken but others remain; "info" = worth a look (long chains are normal for
graduate courses).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

import networkx as nx

from .schema import PrereqParse, Timing, norm_code


@dataclass
class Course:
    code: str
    title: str = ""
    parse: PrereqParse = field(default_factory=PrereqParse)
    raw: str = ""                       # prerequisite text as printed (cited in findings)


@dataclass
class Finding:
    id: str
    check: str
    course: str
    detail: str
    evidence: str                       # the catalog text the finding is based on
    severity: str = "blocking"
    related: list[str] = field(default_factory=list)


_SUBJECT = re.compile(r"^([A-Z/&]+)")


def subject(code: str) -> str:
    """Department part of a code: 'MATH' in MATH243. All-digit codes (e.g. Kuwait University's
    0612371) carry the department in their first four digits."""
    code = norm_code(code)
    if code[:1].isdigit():
        return code[:4]
    m = _SUBJECT.match(code)
    return m.group(1) if m else ""


def mandatory_edges(courses: dict[str, Course]) -> Iterable[tuple[str, str]]:
    """(prereq, course) pairs that every student must satisfy: groups with a single option."""
    for c in courses.values():
        for g in c.parse.groups:
            if len(g.options) == 1 and g.options[0].timing == Timing.before:
                yield norm_code(g.options[0].course), norm_code(c.code)


def build_graph(courses: dict[str, Course]) -> nx.DiGraph:
    """Edge prereq -> course for every option; attribute `mandatory` for single-option groups."""
    g = nx.DiGraph()
    for key, c in courses.items():
        g.add_node(key, title=c.title)
    for c in courses.values():
        for grp in c.parse.groups:
            for o in grp.options:
                g.add_edge(norm_code(o.course), norm_code(c.code),
                           mandatory=len(grp.options) == 1, timing=o.timing.value)
    return g


def min_terms(courses: dict[str, Course]) -> dict[str, int]:
    """Fewest terms needed to be able to take each course, choosing the best OR option.

    terms(course) = 1 + max over groups of (min over options of terms(option)),
    where a concurrent option adds no term and unknown or cyclic courses count as 0.
    """
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def terms(code: str) -> int:
        if code in memo:
            return memo[code]
        c = courses.get(code)
        if c is None or code in visiting:
            return 0
        visiting.add(code)
        need = 0
        for grp in c.parse.groups:
            best = min(
                terms(norm_code(o.course)) - (1 if o.timing != Timing.before else 0)
                for o in grp.options
            )
            need = max(need, best)
        visiting.discard(code)
        memo[code] = need + 1
        return memo[code]

    return {k: terms(k) for k in courses}


def audit(courses: Iterable[Course], earlier_codes: Optional[dict[str, str]] = None,
          max_terms: int = 8) -> list[Finding]:
    """Run every check. `earlier_codes` maps normalized codes from earlier editions to the
    edition they last appeared in (enables the renumbered check)."""
    cat = {norm_code(c.code): c for c in courses}
    subjects = {subject(k) for k in cat}
    findings: list[Finding] = []

    def add(check, course, detail, related=(), severity="blocking"):
        c = cat[course]
        findings.append(Finding(f"F{len(findings) + 1:04d}", check, c.code, detail, c.raw,
                                severity, list(related)))

    for key, c in cat.items():
        for grp in c.parse.groups:
            sole = len(grp.options) == 1
            for o in grp.options:
                p = norm_code(o.course)
                if p == key:
                    add("self_reference", key, f"{c.code} lists itself as a prerequisite",
                        severity="blocking" if sole else "warning")
                elif p not in cat and subject(p) in subjects:
                    sev = "blocking" if sole else "warning"
                    alt = "" if sole else " (one of several alternatives)"
                    if earlier_codes and p in earlier_codes:
                        add("renumbered", key, f"{o.course}{alt} is not in this edition; it last appeared in "
                                               f"{earlier_codes[p]}", [o.course], sev)
                    else:
                        add("missing_course", key, f"{o.course}{alt} does not exist in this catalog",
                            [o.course], sev)

    g = nx.DiGraph()
    g.add_edges_from((a, b) for a, b in mandatory_edges(cat) if a in cat and a != b)
    for comp in nx.strongly_connected_components(g):
        if len(comp) > 1:
            members = sorted(comp)
            add("cycle", members[0], "mandatory prerequisite loop: " + " -> ".join(
                cat[m].code for m in members) + " -> " + cat[members[0]].code, [cat[m].code for m in members])

    for key, t in min_terms(cat).items():
        if t > max_terms:
            add("long_chain", key, f"needs at least {t} terms of prerequisites before it can be taken "
                                   f"(limit {max_terms})", severity="info")
    return findings


SEVERITY_ORDER = {"blocking": 0, "warning": 1, "info": 2}
CHECK_TITLES = {
    "self_reference": "Courses that require themselves",
    "cycle": "Prerequisite loops",
    "missing_course": "Prerequisites that are not in the catalog",
    "renumbered": "Prerequisites renumbered or removed in a later catalog",
    "long_chain": "Very long prerequisite chains",
}


def report_markdown(name: str, findings: list[Finding], n_courses: int) -> str:
    """A plain report generated from the findings (no model): every line cites a finding ID and
    quotes the catalog text it is based on."""
    counts = {s: sum(f.severity == s for f in findings) for s in SEVERITY_ORDER}
    lines = [f"# Prerequisite audit: {name}", "",
             f"{n_courses} courses checked. {counts['blocking']} blocking issues, {counts['warning']} warnings, "
             f"{counts['info']} notes.", ""]
    for check, title in CHECK_TITLES.items():
        fs = sorted((f for f in findings if f.check == check), key=lambda f: (SEVERITY_ORDER[f.severity], f.course))
        if not fs:
            continue
        lines += [f"## {title} ({len(fs)})", ""]
        for f in fs:
            lines.append(f"- **{f.course}** [{f.severity}, {f.id}]: {f.detail}. Catalog text: \"{f.evidence}\"")
        lines.append("")
    return "\n".join(lines)
