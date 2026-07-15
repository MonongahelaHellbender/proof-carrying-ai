"""Deterministic arithmetic checker — no model in the verdict path.

This module is the trust root of Proof-Carrying AI. It takes each claim's stated
computation (an arithmetic expression) and its asserted numeric result, and it
RECOMPUTES the arithmetic from scratch. The verdict comes from that recompute,
never from anything the language model said about its own work.

Two independent properties are checked per claim:

  1. GROUNDING  — does every number in the expression trace to a given fact, or
     to a value a prior grounded claim already derived? (operand provenance)
  2. ARITHMETIC — does the asserted result equal the recomputed result?

A claim is only VERIFIED when both hold. A claim whose arithmetic is internally
correct but whose operands were invented is UNGROUNDED — a distinct, honest
failure that a pure arithmetic check would miss.

Design constraints:
  * standard library only (no third-party deps)
  * no dynamic code is ever run — expressions are parsed with `ast` and walked
    by an explicit allow-list, so a malicious or malformed expression cannot run
    arbitrary code
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field

# The four honest headline verdicts. UNCHECKABLE and UNGROUNDED are first-class:
# they are counted, never hidden, and never silently upgraded to VERIFIED.
VERIFIED = "VERIFIED"        # grounded operands AND asserted == recomputed
FAILED = "FAILED"            # grounded operands BUT asserted != recomputed
UNGROUNDED = "UNGROUNDED"    # an operand is not a fact or a prior derived value
UNCHECKABLE = "UNCHECKABLE"  # no computation to check at all

CHECKER_ID = "arith-grounded-v1"
RETRIEVAL_CHECKER_ID = "retrieval-verbatim-v1"

# Only these operators are allowed. Note the deliberate ABSENCE of `**` (pow):
# a small exponent expression like 9**9**9 is a cheap denial-of-service, so we
# refuse it outright rather than trying to bound it.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Numbers embedded in free-text facts. The negative lookbehind for a word char
# or dot keeps us from reading the "1" out of "Q1" as a fact.
_NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


class UnsafeExpression(ValueError):
    """Raised when an expression contains anything outside the allow-list."""


def recompute(expr: str) -> float:
    """Recompute a pure-arithmetic expression by walking its parsed AST.

    Accepts numeric literals, + - * / // %, unary +/-, and parentheses.
    Anything else (names, function calls, attribute access, **, etc.) raises
    UnsafeExpression. No dynamic code is run.
    """
    return _reduce(_parse(expr))


def operands(expr: str) -> list[float]:
    """Return the numeric literals in an expression (its operands).

    '46300 / 3' -> [46300.0, 3.0]. Unary minus is a separate node, so the
    literal in '-1200' is reported as 1200.0.
    """
    out: list[float] = []
    for node in ast.walk(_parse(expr)):
        if isinstance(node, ast.Constant) and not isinstance(node.value, bool) \
                and isinstance(node.value, (int, float)):
            out.append(float(node.value))
    return out


def _parse(expr: str) -> ast.AST:
    try:
        return ast.parse(expr, mode="eval").body
    except SyntaxError as exc:
        raise UnsafeExpression(f"could not parse: {exc.msg}") from exc


def _reduce(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):  # bool is an int subclass; reject it
            raise UnsafeExpression("boolean literals are not numbers")
        if isinstance(node.value, (int, float)):
            return node.value
        raise UnsafeExpression(f"non-numeric literal: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_reduce(node.left), _reduce(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_reduce(node.operand))
    raise UnsafeExpression(f"disallowed syntax: {type(node).__name__}")


def parse_number(text):
    """Normalize a human-written number ('$1,250.00', '46,700', '15.5%') to float.

    Returns None if the text is not a bare number after stripping currency,
    thousands separators, percent signs, and whitespace.
    """
    if text is None:
        return None
    cleaned = str(text).strip().replace(",", "").replace("$", "").replace("%", "").strip()
    if cleaned == "":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_numbers(text: str) -> list[float]:
    """Pull every standalone number out of free-text facts."""
    nums = []
    for m in _NUMBER_RE.finditer(text or ""):
        v = parse_number(m.group())
        if v is not None:
            nums.append(v)
    return nums


def numbers_match(a: float, b: float, rel_tol: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    """Tolerant equality so 46700 == 46700.0 and 15566.6667 == 15566.666666..."""
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def _member(x: float, pool: list[float]) -> bool:
    return any(numbers_match(x, p) for p in pool)


def _fmt(x: float) -> str:
    """Format a computed number cleanly (drop trailing .0 for integers)."""
    if x == int(x):
        return str(int(x))
    return f"{x:.6g}"


# ---- arithmetic-only check (kept as a building block and for unit tests) ----

@dataclass
class CheckResult:
    verdict: str
    recomputed: float | None
    detail: str


def check_claim(computation: str, asserted_text) -> CheckResult:
    """Arithmetic self-consistency only: does asserted == recompute(expr)?

    This ignores grounding on purpose; check_claims() layers grounding on top.
    """
    if not computation or not computation.strip():
        return CheckResult(UNCHECKABLE, None, "no computation was provided")
    try:
        rec = recompute(computation)
    except UnsafeExpression as exc:
        return CheckResult(UNCHECKABLE, None, f"expression not checkable: {exc}")
    asserted = parse_number(asserted_text)
    if asserted is None:
        return CheckResult(UNCHECKABLE, rec, "no numeric asserted value to compare against")
    if numbers_match(rec, asserted):
        return CheckResult(VERIFIED, rec, f"{computation.strip()} = {_fmt(rec)}")
    return CheckResult(FAILED, rec, f"asserted {_fmt(asserted)}, but {computation.strip()} = {_fmt(rec)}")


# ---- verbatim-quote normalization for the retrieval domain ----

_WS_RE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Whitespace-collapsed, case-folded text for verbatim-quote membership.

    'Verbatim' here means: modulo runs of whitespace and letter case. That is a
    named, deliberate loosening — the model rarely reproduces exact spacing — and
    it still fails a fabricated or reworded quote.
    """
    return _WS_RE.sub(" ", s or "").strip().lower()


def _source_map(sources) -> dict:
    """Index a list of {id, text, ...} sources by upper-cased id."""
    out = {}
    for s in (sources or []):
        sid = str(s.get("id", "")).strip().upper()
        if sid:
            out[sid] = s.get("text", "")
    return out


# ---- kind-dispatching check over an ordered list of mixed claims ----

@dataclass
class ClaimVerdict:
    kind: str                # 'arithmetic' | 'retrieval'
    text: str
    verdict: str             # headline: VERIFIED | FAILED | UNGROUNDED | UNCHECKABLE
    detail: str
    # arithmetic fields
    computation: str = ""
    asserted_value: object = None
    recomputed: object = None
    operands: list = field(default_factory=list)
    grounded: bool = False
    ungrounded_operands: list = field(default_factory=list)
    arithmetic: str = "NA"   # MATCH | MISMATCH | NA
    grounding_detail: str = ""
    # retrieval fields
    source_id: str = ""
    quote: str = ""
    found: bool = False


def check_claims(raw_claims, facts: str = "", sources=None) -> list[ClaimVerdict]:
    """Check a mixed list of claims, dispatching by kind.

    Arithmetic claims thread operand provenance in order. Retrieval claims are
    checked independently against the source corpus. Both stay model-free.
    """
    available = list(extract_numbers(facts))
    smap = _source_map(sources)
    results: list[ClaimVerdict] = []
    for rc in raw_claims:
        if getattr(rc, "kind", "arithmetic") == "retrieval":
            results.append(_check_retrieval(rc, smap))
        else:
            results.append(_check_arithmetic(rc, available))
    return results


def _check_arithmetic(rc, available: list) -> ClaimVerdict:
    """Ground operands against `available` (mutated in place) and recompute.

    Crucially, the value appended to the provenance pool is the value WE
    recomputed, not the value the model asserted — so a fabricated operand stays
    ungrounded even if the model reused it downstream.
    """
    comp = (rc.computation or "").strip()
    asserted_text = rc.asserted_text
    if not comp:
        return ClaimVerdict(kind="arithmetic", text=rc.text, verdict=UNCHECKABLE,
                            detail="no computation was provided", computation=comp,
                            asserted_value=asserted_text, grounding_detail="no computation to ground")
    try:
        rec = recompute(comp)
        ops = operands(comp)
    except UnsafeExpression as exc:
        return ClaimVerdict(kind="arithmetic", text=rc.text, verdict=UNCHECKABLE,
                            detail=f"expression not checkable: {exc}", computation=comp,
                            asserted_value=asserted_text, grounding_detail="no computation to ground")

    ungrounded = [op for op in ops if not _member(op, available)]
    grounded = not ungrounded
    asserted = parse_number(asserted_text)
    if asserted is None:
        arithmetic = "NA"
    elif numbers_match(rec, asserted):
        arithmetic = "MATCH"
    else:
        arithmetic = "MISMATCH"

    if not grounded:
        verdict = UNGROUNDED
    elif arithmetic == "MATCH":
        verdict = VERIFIED
    elif arithmetic == "MISMATCH":
        verdict = FAILED
    else:
        verdict = UNCHECKABLE

    if grounded:
        available.append(rec)

    return ClaimVerdict(
        kind="arithmetic", text=rc.text, verdict=verdict,
        detail=_detail(verdict, comp, rec, asserted, ungrounded),
        computation=comp, asserted_value=asserted_text, recomputed=rec, operands=ops,
        grounded=grounded, ungrounded_operands=ungrounded, arithmetic=arithmetic,
        grounding_detail=_grounding_detail(grounded, ops, ungrounded))


def _check_retrieval(rc, smap: dict) -> ClaimVerdict:
    """Verify a quoted span appears verbatim in the cited source.

    VERIFIED  — the quote is present in the named source.
    FAILED    — the source exists, but the quote is not in it (fabricated/misquoted).
    UNGROUNDED— the cited source id is not in the provided corpus (invented source).
    UNCHECKABLE — no quote or no source cited.
    """
    quote = (rc.quote or "").strip()
    sid = (rc.source_id or "").strip()
    if not quote or not sid:
        return ClaimVerdict(kind="retrieval", text=rc.text, verdict=UNCHECKABLE,
                            detail="no quote or source to check", source_id=sid, quote=quote)
    if sid.upper() not in smap:
        return ClaimVerdict(kind="retrieval", text=rc.text, verdict=UNGROUNDED,
                            detail=f"cited source {sid} is not in the provided corpus",
                            source_id=sid, quote=quote)
    found = normalize_text(quote) in normalize_text(smap[sid.upper()])
    verdict = VERIFIED if found else FAILED
    detail = (f"quote found verbatim in source {sid}" if found
              else f"quote NOT found in source {sid} (fabricated or misquoted)")
    return ClaimVerdict(kind="retrieval", text=rc.text, verdict=verdict, detail=detail,
                        source_id=sid, quote=quote, found=found)


def _detail(verdict, comp, rec, asserted, ungrounded) -> str:
    if verdict == VERIFIED:
        return f"{comp} = {_fmt(rec)}  (operands grounded)"
    if verdict == FAILED:
        return f"asserted {_fmt(asserted)}, but {comp} = {_fmt(rec)}  (operands grounded)"
    if verdict == UNGROUNDED:
        bad = ", ".join(_fmt(u) for u in ungrounded)
        return f"operand(s) not in facts or prior results: {bad}   [{comp} = {_fmt(rec)}]"
    return f"{comp} = {_fmt(rec)}  (grounded, but no asserted value to compare)"


def _grounding_detail(grounded, ops, ungrounded) -> str:
    shown = ", ".join(_fmt(o) for o in ops) if ops else "(none)"
    if grounded:
        return f"operands {shown} — all trace to a fact or a prior result"
    bad = ", ".join(_fmt(u) for u in ungrounded)
    return f"operands {shown}; ungrounded: {bad}"


def coverage(verdicts: list[str]) -> dict:
    """Coverage denominator: how much of the answer was checkable.

    checkable = verified + failed + ungrounded  (all three are real check
    outcomes). UNCHECKABLE claims had no computation to check and drag the
    ratio down honestly. coverage_ratio = checkable / total.
    """
    total = len(verdicts)
    verified = verdicts.count(VERIFIED)
    failed = verdicts.count(FAILED)
    ungrounded = verdicts.count(UNGROUNDED)
    uncheckable = verdicts.count(UNCHECKABLE)
    checkable = verified + failed + ungrounded
    return {
        "total_claims": total,
        "checkable": checkable,
        "verified": verified,
        "failed": failed,
        "ungrounded": ungrounded,
        "uncheckable": uncheckable,
        "coverage_ratio": round(checkable / total, 4) if total else 0.0,
    }
