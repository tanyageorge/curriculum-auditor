"""Parser agent: Muse Spark turns prerequisite text into a PrereqParse.

Each call is checked by the deterministic guardrails. If the output is invalid or cites
a course that is not in the text, the model gets the specific problems back and one more
try. If it still fails, the result is returned flagged for human review rather than
silently accepted. Results are cached on disk so no input is ever paid for twice.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .data import ROOT
from .guardrails import check
from .llm import default_model, get_client, response_format
from .schema import PrereqParse

PROMPT_VERSION = "v2"  # v2: numeric course codes, N/A placeholders, leaked course headings

SYSTEM_PROMPT = """You convert university course prerequisite text into structured data.

Output the requirement in conjunctive normal form:
- groups: ALL groups must be satisfied (AND).
- options inside a group: ANY ONE option satisfies the group (OR).

Rules
1. Copy course codes as written, e.g. "MATH 243". Never add a course that is not in the text.
   If a code is shortened by context ("MATH 243 or 223"), write it out in full ("MATH 223").
2. "A and B" -> two groups. "A or B" -> one group with two options.
   Commas usually mean AND, but a list ending in "or" is one group: "A, B, or C" -> one group of three.
3. "(A and B) or C" cannot be a single group; rewrite it as (A or C) and (B or C).
4. timing: "concurrent", "corequisite", "taken at the same time" -> concurrent;
   "prior or concurrent", "may be taken concurrently" -> before_or_concurrent; otherwise before.
   Courses in the corequisite text are concurrent unless the text says otherwise.
5. min_grade only when a grade is stated ("C or better", "minimum grade D" -> "C", "D"), on the
   courses the text attaches it to. Otherwise null.
6. conditions: non-course requirements, quoted briefly: class standing, consent or permission,
   placement, GPA, "or equivalent", admission to a program. If a condition is an alternative to a
   course ("A or consent of instructor"), keep A as a group and record "or consent of instructor".
7. needs_review = true when the structure cannot be read from the text alone: course codes with no
   "and"/"or" between them, "and" and "or" mixed with nothing that fixes the grouping, symbols such
   as * or † that may change the meaning, or references like "as specified". Give a one-sentence
   review_reason, and still give your best reading.
8. If the text requires no course, groups is empty.
9. Course codes can be all digits or digits with a dash ("0612371", "0612-454"). They are courses.
10. "None", "N/A", "Nil" or "-" next to a course code are placeholders from the catalog layout, not
    "no requirement": keep the course ("ENGL145 N/A" -> ENGL145).
11. Catalog text is sometimes extracted with the NEXT course's heading stuck on the end: a code
    followed by a title, e.g. "0612371 CPE 482 Software Requirements Analysis". The trailing code +
    title is not a prerequisite: keep "0612371", drop "CPE 482", set needs_review and say why.

Examples (shorthand: AND between groups, OR inside a group)
- "ECON 101 and STAT 200 or STAT 210"  -> ECON 101 AND (STAT 200 OR STAT 210)
- "BIO 120, CHEM 110, or CHEM 115"      -> (BIO 120 OR CHEM 110 OR CHEM 115)
- "PHYS 201; MATH 230 (may be taken concurrently)" -> PHYS 201 AND MATH 230 [before_or_concurrent]
- "Junior standing or consent of instructor" -> no groups; conditions: junior standing; or consent of instructor
- "HIST 110 HIST 120" -> HIST 110 AND HIST 120, needs_review: no operator stated between the codes
- "0533201 BIO 340 Cell Biology" -> 0533201, needs_review: trailing code and title look like the next course's heading
"""


@dataclass
class ParseResult:
    parse: Optional[dict]          # PrereqParse as a dict; None if no attempt produced valid output
    attempts: int
    issues: list[str]              # guardrail problems left in the final answer
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    latency_s: float = 0.0
    error: Optional[str] = None
    cached: bool = False

    @property
    def parsed(self) -> Optional[PrereqParse]:
        return PrereqParse.model_validate(self.parse) if self.parse is not None else None


def format_input(prereq: str, coreq: str = "") -> str:
    text = f"Prerequisite text: {prereq.strip() or '(none)'}"
    if coreq.strip():
        text += f"\nCorequisite text: {coreq.strip()}"
    return text


class MuseParser:
    def __init__(self, model: Optional[str] = None, reasoning_effort: str = "minimal",
                 max_attempts: int = 2, cache_path: Optional[Path] = None, client=None):
        self.model = model or default_model()
        self.effort = reasoning_effort
        self.max_attempts = max_attempts
        self.client = client
        self.cache_path = cache_path or ROOT / "results" / "raw" / "parse_cache.jsonl"
        self._lock = threading.Lock()
        self._cache = self._load_cache()

    # ------------------------------------------------------------------ cache
    def _key(self, prereq: str, coreq: str) -> str:
        raw = json.dumps([self.model, self.effort, PROMPT_VERSION, prereq, coreq])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _load_cache(self) -> dict:
        cache = {}
        if self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    cache[row["key"]] = row["result"]
        return cache

    def _store(self, key: str, result: ParseResult) -> None:
        with self._lock:
            self._cache[key] = asdict(result)
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("a") as f:
                f.write(json.dumps({"key": key, "result": asdict(result)}) + "\n")

    # ------------------------------------------------------------------ parse
    def parse(self, prereq: str, coreq: str = "") -> ParseResult:
        key = self._key(prereq, coreq)
        if key in self._cache:
            return ParseResult(**{**self._cache[key], "cached": True})

        client = self.client or get_client()
        source_text = f"{prereq} {coreq}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": format_input(prereq, coreq)},
        ]
        result = ParseResult(parse=None, attempts=0, issues=[])
        t0 = time.time()
        for attempt in range(1, self.max_attempts + 1):
            result.attempts = attempt
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=response_format(PrereqParse, "prereq_parse"),
                    reasoning_effort=self.effort,
                )
            except Exception as exc:  # network / API errors: record and stop
                result.error = f"{type(exc).__name__}: {exc}"
                break
            usage = getattr(resp, "usage", None)
            if usage is not None:
                result.input_tokens += usage.prompt_tokens or 0
                result.output_tokens += usage.completion_tokens or 0
                details = getattr(usage, "completion_tokens_details", None)
                result.reasoning_tokens += (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
            raw = resp.choices[0].message.content or ""
            try:
                parsed = PrereqParse.model_validate_json(raw)
            except ValidationError as exc:
                problems = [f"output did not match the schema: {exc.errors()[0]['msg']}"]
            else:
                problems = check(parsed, source_text)
                result.parse = parsed.model_dump(mode="json")
            result.issues = problems
            if not problems:
                break
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Your answer has these problems:\n- " + "\n- ".join(problems)
                                            + "\nFix them and answer again."},
            ]

        if result.parse is not None and result.issues:
            # Guardrail still failing after the retry: keep the answer but force human review.
            flagged = PrereqParse.model_validate(result.parse)
            flagged.needs_review = True
            flagged.review_reason = "guardrail: " + "; ".join(result.issues)
            result.parse = flagged.model_dump(mode="json")
        result.latency_s = round(time.time() - t0, 2)
        if result.error is None:
            self._store(key, result)
        return result
