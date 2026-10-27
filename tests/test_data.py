import pytest

from auditor.data import MENDELEY, difficulty, load_courses, load_reference_parses
from auditor.schema import structure


@pytest.mark.parametrize("prereq,coreq,stated,tier", [
    ("MATH 101", "", "True", "simple"),
    ("CHEM481", "", "True", "simple"),
    ("MCM 225 and MCM 231", "", "True", "moderate"),
    ("MATH210 with a minimum grade D", "", "True", "moderate"),
    ("ENG 223 or ENG 224", "", "True", "hard"),
    ("STAT 101 MET 321", "", "False", "hard"),
    ("PHYS 141", "MATH 122", "True", "hard"),
])
def test_difficulty(prereq, coreq, stated, tier):
    assert difficulty(prereq, coreq, stated) == tier


needs_data = pytest.mark.skipif(not (MENDELEY / "courses.csv").exists(), reason="Mendeley data not downloaded")


@needs_data
def test_reference_parse_matches_known_example():
    # AUS MTH305: "MTH 102 or MTH 103 or MTH 111, and STA 201 or STA 202 or NGN 111 or QBA 201."
    refs = load_reference_parses()
    cid = next(c for c in refs if c.startswith("aus@") and c.endswith("::MTH305"))
    assert structure(refs[cid]) == frozenset({
        frozenset({"MTH102", "MTH103", "MTH111"}),
        frozenset({"STA201", "STA202", "NGN111", "QBA201"}),
    })


@needs_data
def test_course_ids_flag_duplicates():
    c = load_courses()
    assert c.loc[~c.ambiguous_id, "course_id"].is_unique
