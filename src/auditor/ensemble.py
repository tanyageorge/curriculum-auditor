"""Two independent parsers; disagreement routes the course to human review.

Muse Spark (Meta Model API) is the primary parser. Muse Spark Open (open weights, served by
Baseten) parses the same text independently. If their AND/OR course structures match, the
primary's answer stands. If they differ, the primary's answer is kept but flagged, with the
second reading attached, so a person can decide.
"""
from __future__ import annotations

from typing import Optional

from .notation import to_text
from .schema import PrereqParse, structure


def combine(primary: Optional[PrereqParse], second: Optional[PrereqParse]) -> tuple[Optional[PrereqParse], bool]:
    """Return (final parse, disagreed)."""
    if primary is None:
        return second, False
    if second is None:
        return primary, False
    if structure(primary) == structure(second):
        return primary, False
    flagged = primary.model_copy(deep=True)
    flagged.needs_review = True
    note = f"parsers disagree; second reading: {to_text(second)}"
    flagged.review_reason = f"{primary.review_reason}; {note}" if primary.review_reason else note
    return flagged, True
