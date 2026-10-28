"""Parser agent, guardrails, baseline and metrics, tested without calling the API."""
import json
from types import SimpleNamespace

from auditor import baseline
from auditor.guardrails import check, is_grounded
from auditor.metrics import compare, summarize
from auditor.notation import from_text
from auditor.parser import MuseParser
from auditor.schema import structure


# --------------------------------------------------------------------------- guardrails

def test_grounding_accepts_exact_and_shorthand():
    assert is_grounded("MATH 243", "CSC 210 and (MATH 243 or MATH 223)")
    assert is_grounded("MATH 223", "MATH 243 or 223")            # subject carried over
    assert is_grounded("ACM 100", "ACM 95/100")                  # cross-listed number
    assert is_grounded("CHEM481", "CHEM 481")                    # spacing differs


def test_grounding_rejects_invented_course():
    assert not is_grounded("MATH 101", "CSC 210 and MATH 243")
    assert not is_grounded("PHYS 243", "CSC 210 and MATH 243")


def test_check_flags_invented_course_and_missing_reason():
    p = from_text("CSC 210 AND MATH 999")
    p.needs_review = True
    issues = check(p, "CSC 210 and MATH 243")
    assert any("MATH 999" in i for i in issues)
    assert any("review_reason" in i for i in issues)


# --------------------------------------------------------------------------- baseline

def test_baseline_simple_and_or():
    p = baseline.parse("MTH 102 or MTH 103, and STA 201")
    assert structure(p) == frozenset({frozenset({"MTH102", "MTH103"}), frozenset({"STA201"})})


def test_baseline_grade_and_condition():
    p = baseline.parse("MATH 210 with a minimum grade of C; junior standing")
    assert p.groups[0].options[0].min_grade == "C"
    assert p.conditions == ["junior standing"]


# --------------------------------------------------------------------------- metrics

def test_compare_and_summarize():
    ref = from_text("A 1 AND (B 2 OR C 3)")
    good = compare(from_text("(C 3 OR B 2) AND A 1"), ref)      # order doesn't matter
    bad = compare(from_text("A 1 AND B 2 AND D 4"), ref)
    assert good["structure_exact"] == 1 and bad["structure_exact"] == 0
    assert (bad["tp"], bad["fp"], bad["fn"]) == (2, 1, 1)
    s = summarize([{**good, "tier": "hard"}, {**bad, "tier": "hard"}], by="tier")
    assert s["all"]["structure_exact"] == 0.5 and s["hard"]["n"] == 2
    assert compare(None, ref)["fn"] == 3


# --------------------------------------------------------------------------- parser agent

class FakeClient:
    """Returns canned JSON answers in order, recording each request."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.answers.pop(0)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50,
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=40))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


def answer(text, needs_review=False, reason=None):
    p = from_text(text)
    p.needs_review, p.review_reason = needs_review, reason
    return json.dumps(p.model_dump(mode="json"))


def make_parser(tmp_path, answers):
    client = FakeClient(answers)
    return MuseParser(model="fake", client=client, cache_path=tmp_path / "cache.jsonl"), client


def test_parser_happy_path_and_cache(tmp_path):
    mp, client = make_parser(tmp_path, [answer("CSC 210 AND (MATH 243 OR MATH 223)")])
    r = mp.parse("CSC 210 and (MATH 243 or MATH 223)")
    assert r.attempts == 1 and not r.issues and r.output_tokens == 50 and r.reasoning_tokens == 40
    assert structure(r.parsed) == frozenset({frozenset({"CSC210"}), frozenset({"MATH243", "MATH223"})})
    # second call is served from cache: no new API request
    r2 = mp.parse("CSC 210 and (MATH 243 or MATH 223)")
    assert r2.cached and len(client.calls) == 1
    # cache survives a restart
    mp3 = MuseParser(model="fake", client=FakeClient([]), cache_path=tmp_path / "cache.jsonl")
    assert mp3.parse("CSC 210 and (MATH 243 or MATH 223)").cached


def test_parser_retries_on_invented_course(tmp_path):
    mp, client = make_parser(tmp_path, [answer("CSC 210 AND MATH 999"), answer("CSC 210 AND MATH 243")])
    r = mp.parse("CSC 210 and MATH 243")
    assert r.attempts == 2 and not r.issues and not r.parsed.needs_review
    feedback = client.calls[1]["messages"][-1]["content"]
    assert "MATH 999" in feedback                       # model was told exactly what was wrong


def test_parser_flags_when_guardrail_keeps_failing(tmp_path):
    mp, _ = make_parser(tmp_path, [answer("MATH 999"), answer("MATH 998")])
    r = mp.parse("CSC 210")
    assert r.parsed.needs_review and r.parsed.review_reason.startswith("guardrail:")


def test_parser_handles_invalid_json(tmp_path):
    mp, _ = make_parser(tmp_path, ["not json", answer("CSC 210")])
    r = mp.parse("CSC 210")
    assert r.attempts == 2 and not r.issues


def test_parser_records_api_error_without_caching(tmp_path):
    class Boom(FakeClient):
        def _create(self, **kwargs):
            raise TimeoutError("network")
    mp = MuseParser(model="fake", client=Boom([]), cache_path=tmp_path / "cache.jsonl")
    r = mp.parse("CSC 210")
    assert r.error and r.parse is None
    assert not (tmp_path / "cache.jsonl").exists()      # failures are retried next run, not cached
