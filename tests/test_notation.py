import pytest

from auditor.notation import from_text, to_text
from auditor.schema import Timing, structure


def test_none():
    assert from_text("NONE").groups == [] and from_text("").groups == []


def test_and_or():
    p = from_text("CSC 210 AND (MATH 243 OR MATH 223)")
    assert structure(p) == frozenset({frozenset({"CSC210"}), frozenset({"MATH243", "MATH223"})})


def test_tags_and_conditions():
    p = from_text("MATH 210 [min C] and PHYS 141 [concurrent] COND: consent of instructor; junior standing")
    assert p.groups[0].options[0].min_grade == "C"
    assert p.groups[1].options[0].timing == Timing.concurrent
    assert p.conditions == ["consent of instructor", "junior standing"]


def test_conditions_only():
    p = from_text("COND: senior standing")
    assert p.groups == [] and p.conditions == ["senior standing"]


@pytest.mark.parametrize("text", [
    "NONE",
    "CSC 210",
    "CSC 210 AND (MATH 243 OR MATH 223)",
    "(A 1 [min D] OR B 2 [prior or concurrent]) AND C 3 COND: senior standing",
    "COND: consent of instructor",
])
def test_round_trip(text):
    assert to_text(from_text(text)) == text


def test_unknown_tag_rejected():
    with pytest.raises(ValueError):
        from_text("CSC 210 [maybe]")
