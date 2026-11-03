from auditor.audit import Course, audit, min_terms, report_markdown
from auditor.notation import from_text
from auditor.schema import norm_code


def cat(**reqs):
    return [Course(code=k, parse=from_text(v), raw=v) for k, v in reqs.items()]


def checks(findings):
    return sorted((f.check, f.course, f.severity) for f in findings)


def test_clean_catalog_has_no_findings():
    assert audit(cat(**{"CS 1": "NONE", "CS 2": "CS 1", "CS 3": "CS 2 AND (CS 1 OR MA 1)", "MA 1": "NONE"})) == []


def test_missing_required_vs_alternative():
    f = audit(cat(**{"CS 1": "NONE", "CS 2": "CS 9", "CS 3": "(CS 1 OR CS 8)"}))
    assert checks(f) == [("missing_course", "CS 2", "blocking"), ("missing_course", "CS 3", "warning")]


def test_other_subjects_not_flagged_in_partial_catalog():
    assert audit(cat(**{"CS 1": "PHYS 101"})) == []          # no PHYS courses in this catalog


def test_renumbered_uses_earlier_editions():
    f = audit(cat(**{"CS 2": "CS 1"}), earlier_codes={"CS1": "the 2020 catalog (now CS 101)"})
    assert f[0].check == "renumbered" and "now CS 101" in f[0].detail


def test_self_reference_and_cycle():
    f = audit(cat(**{"CS 1": "CS 1", "CS 2": "CS 3", "CS 3": "CS 2"}))
    assert ("self_reference", "CS 1", "blocking") in checks(f)
    assert any(x.check == "cycle" and set(map(norm_code, x.related)) == {"CS2", "CS3"} for x in f)


def test_loop_through_alternative_or_corequisite_is_not_a_cycle():
    assert audit(cat(**{"CS 1": "NONE", "CS 2": "(CS 3 OR CS 1)", "CS 3": "CS 2"})) == []
    assert audit(cat(**{"CS 2": "CS 3 [concurrent]", "CS 3": "CS 2"})) == []


def test_min_terms_takes_best_alternative_and_concurrency():
    c = {norm_code(x.code): x for x in cat(**{"A 1": "NONE", "A 2": "A 1", "A 3": "A 2", "B 1": "(A 3 OR A 1)",
                                              "B 2": "A 2 [concurrent]"})}
    t = min_terms(c)
    assert (t["A3"], t["B1"], t["B2"]) == (3, 2, 2)


def test_long_chain_and_report_cites_evidence():
    chain = {f"C {i}": (f"C {i-1}" if i > 1 else "NONE") for i in range(1, 11)}
    f = audit(cat(**chain), max_terms=8)
    assert {x.course for x in f if x.check == "long_chain"} == {"C 9", "C 10"}
    md = report_markdown("Test", f, 10)
    assert "C 10" in md and 'Catalog text: "C 9"' in md and f[0].id in md


def test_numeric_codes_use_department_prefix():
    # 0612xxx = one department; a missing 0600xxx course from another department is not flagged
    f = audit(cat(**{"0612371": "0612999 AND 0600207"}))
    assert [(x.check, x.related) for x in f] == [("missing_course", ["0612999"])]


def test_incomplete_catalog_skips_missing_checks_but_keeps_structural_ones():
    f = audit(cat(**{"CS 2": "CS 1", "CS 3": "CS 3"}), complete_catalog=False)
    assert [x.check for x in f] == ["self_reference"]
