"""Tests for the deterministic checker — the trust root.

Run: python3 -m pytest tests/  (or: python3 tests/test_checker.py)
No third-party deps required; falls back to a plain runner if pytest is absent.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pcai import checker as c
from pcai.llm import RawClaim


def test_recompute_basic():
    assert c.recompute("42000 + 3500 + 1200") == 46700
    assert c.recompute("(2 + 3) * 4") == 20
    assert abs(c.recompute("46700 / 3") - 15566.6666667) < 1e-3


def test_recompute_rejects_code():
    # Names, calls, attribute access, and ** must all be refused, not run.
    for bad in ["__import__('os')", "open('x')", "a + 1", "2 ** 64", "x.y"]:
        try:
            c.recompute(bad)
            assert False, f"should have refused: {bad}"
        except c.UnsafeExpression:
            pass


def test_verified():
    r = c.check_claim("42000 + 3500 + 1200", "46700")
    assert r.verdict == c.VERIFIED


def test_verified_with_formatting():
    # currency symbols and thousands separators normalize away
    r = c.check_claim("42000 + 3500 + 1200", "$46,700.00")
    assert r.verdict == c.VERIFIED


def test_failed():
    r = c.check_claim("42000 + 3500 + 1200", "46000")
    assert r.verdict == c.FAILED
    assert "46700" in r.detail


def test_uncheckable_no_computation():
    assert c.check_claim("", "46700").verdict == c.UNCHECKABLE


def test_uncheckable_bad_expression():
    assert c.check_claim("total of the costs", "46700").verdict == c.UNCHECKABLE


def test_coverage_counts_uncheckable():
    verdicts = [c.VERIFIED, c.FAILED, c.UNCHECKABLE]
    cov = c.coverage(verdicts)
    assert cov["total_claims"] == 3
    assert cov["checkable"] == 2
    assert cov["coverage_ratio"] == round(2 / 3, 4)


# ---- operand grounding ----

def test_operands_extracted():
    assert c.operands("46300 / 3") == [46300.0, 3.0]
    assert c.operands("(42000 + 3500) * -2") == [42000.0, 3500.0, 2.0]


def test_extract_numbers_ignores_letter_digits():
    # the "1" in "Q1" must NOT be read as a fact
    nums = c.extract_numbers("Q1 costs: 42000, 3500, 1200. 3 months.")
    assert 1.0 not in nums
    assert set(nums) == {42000.0, 3500.0, 1200.0, 3.0}


class _RC:
    """Minimal stand-in for llm.RawClaim."""
    def __init__(self, text, computation, asserted_text):
        self.text = text
        self.computation = computation
        self.asserted_text = asserted_text


FACTS = "Q1 costs: salaries = 42000, cloud = 3500, travel = 1200. The quarter has 3 months."


def test_grounded_and_correct_is_verified():
    claims = [_RC("total", "42000 + 3500 + 1200", "46700")]
    v = c.check_claims(claims, FACTS)
    assert v[0].verdict == c.VERIFIED
    assert v[0].grounded is True


def test_grounded_but_wrong_arithmetic_is_failed():
    claims = [_RC("total", "42000 + 3500 + 1200", "46300")]
    v = c.check_claims(claims, FACTS)
    assert v[0].verdict == c.FAILED


def test_fabricated_operand_is_ungrounded():
    # 46300 is not a fact and not a prior derived value -> UNGROUNDED
    claims = [_RC("avg", "46300 / 3", "15433.33")]
    v = c.check_claims(claims, FACTS)
    assert v[0].verdict == c.UNGROUNDED
    assert 46300.0 in v[0].ungrounded_operands


def test_prior_result_grounds_next_claim():
    # claim 2 uses 46700, which claim 1 derives from grounded facts
    claims = [
        _RC("total", "42000 + 3500 + 1200", "46700"),
        _RC("avg", "46700 / 3", "15566.67"),
    ]
    v = c.check_claims(claims, FACTS)
    assert v[0].verdict == c.VERIFIED
    assert v[1].verdict == c.VERIFIED  # 46700 grounded by the prior derivation


def test_provenance_uses_recomputed_not_asserted():
    # claim 1's ASSERTED total is wrong (46300), but the checker derives 46700.
    # claim 2 uses 46700 -> grounded; a claim using 46300 would be ungrounded.
    claims = [
        _RC("total", "42000 + 3500 + 1200", "46300"),   # FAILED, but derives 46700
        _RC("avg-real", "46700 / 3", "15566.67"),        # grounded by real derivation
        _RC("avg-fake", "46300 / 3", "15433.33"),        # 46300 was never real
    ]
    v = c.check_claims(claims, FACTS)
    assert v[0].verdict == c.FAILED
    assert v[1].verdict == c.VERIFIED
    assert v[2].verdict == c.UNGROUNDED


# ---- retrieval-grounded facts ----

SRC = [{"id": "S1", "text": "Acme reported Q1 revenue of $4.2 million, up 12% from the prior quarter."}]


def test_normalize_text():
    assert c.normalize_text("  Hello   World  ") == "hello world"


def test_retrieval_verified():
    claims = [RawClaim(kind="retrieval", text="revenue", source_id="S1",
                       quote="Q1 revenue of $4.2 million")]
    assert c.check_claims(claims, "", SRC)[0].verdict == c.VERIFIED


def test_retrieval_verified_after_normalization():
    # case-folded + whitespace-collapsed, and a lower-case source id still resolves
    claims = [RawClaim(kind="retrieval", text="growth", source_id="s1",
                       quote="UP 12%   from the prior quarter")]
    assert c.check_claims(claims, "", SRC)[0].verdict == c.VERIFIED


def test_retrieval_failed_on_misquote():
    claims = [RawClaim(kind="retrieval", text="revenue", source_id="S1",
                       quote="Q1 revenue of $5.0 billion")]
    assert c.check_claims(claims, "", SRC)[0].verdict == c.FAILED


def test_retrieval_ungrounded_on_invented_source():
    claims = [RawClaim(kind="retrieval", text="x", source_id="S9", quote="anything")]
    assert c.check_claims(claims, "", SRC)[0].verdict == c.UNGROUNDED


def test_retrieval_uncheckable_without_quote():
    claims = [RawClaim(kind="retrieval", text="x", source_id="", quote="")]
    assert c.check_claims(claims, "", SRC)[0].verdict == c.UNCHECKABLE


def test_mixed_arithmetic_and_retrieval_in_one_pass():
    claims = [
        _RC("total", "42000 + 3500 + 1200", "46700"),
        RawClaim(kind="retrieval", text="rev", source_id="S1", quote="Q1 revenue of $4.2 million"),
    ]
    v = c.check_claims(claims, FACTS, SRC)
    assert v[0].kind == "arithmetic" and v[0].verdict == c.VERIFIED
    assert v[1].kind == "retrieval" and v[1].verdict == c.VERIFIED


# ---- answer coverage: numbers stated in prose with no receipt ----

def test_answer_coverage_flags_numbers_with_no_receipt():
    # The answer states 45300 and 15000; the only claim asserts 46700. Both unbacked.
    v = c.check_claims([_RC("total", "42000 + 3500 + 1200", "46700")], FACTS)
    ac = c.answer_coverage("The total is $45300 and the monthly average is $15000.", v, FACTS)
    assert ac["answer_numbers"] == 2
    assert ac["backed"] == 0
    assert 45300.0 in ac["unbacked"] and 15000.0 in ac["unbacked"]


def test_answer_coverage_accepts_claim_quote_and_fact_backing():
    claims = [
        _RC("total", "42000 + 3500 + 1200", "46700"),
        RawClaim(kind="retrieval", text="rev", source_id="S1", quote="Q1 revenue of $4.2 million"),
    ]
    v = c.check_claims(claims, FACTS, SRC)
    # 46700 is a claim's asserted value, 3 is given in FACTS, 4.2 sits in a VERIFIED quote
    ac = c.answer_coverage("Total 46700 over 3 months; revenue 4.2 million.", v, FACTS)
    assert ac["unbacked"] == []
    assert ac["backed_ratio"] == 1.0


def test_answer_coverage_ignores_unverified_quote_as_backing():
    # A misquoted (FAILED) retrieval claim must not launder a number into "backed".
    claims = [RawClaim(kind="retrieval", text="rev", source_id="S1",
                       quote="Q1 revenue of $9.9 billion")]
    v = c.check_claims(claims, "", SRC)
    ac = c.answer_coverage("Revenue was 9.9 billion.", v, "")
    assert ac["unbacked"] == [9.9]


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            passed += 1
    print(f"\n{passed} tests passed")
