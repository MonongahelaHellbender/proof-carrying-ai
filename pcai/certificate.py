"""The certificate: a portable, checkable receipt for an answer.

A certificate records, per claim, the raw inputs a verifier needs to reach its
OWN verdict, and enough context (facts, source corpus) to recompute grounding.
It also stores `verdict_at_build` — the verdict the checker reached when the
certificate was made — but ONLY so a verifier can demonstrate it was ignored.
`verify()` recomputes everything from `facts` and `sources`.

Two claim kinds share one schema and one coverage denominator:
  * arithmetic — operand grounding + recompute
  * retrieval  — a quoted span must appear verbatim in the cited source

Tamper-evidence: the certificate body carries a sha256 `digest`. This detects
naive edits and binds the claims to their hash. It is NOT a cryptographic
signature — there is no private key, so anyone can recompute the digest after
editing. It proves integrity of a file in transit, not authorship.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from . import checker, signing

CERTIFICATE_VERSION = "0.4"

# Fields that are ABOUT the certificate rather than part of its signed content.
# The digest and signature are computed over everything except these.
_META_FIELDS = ("digest", "signature", "signature_scheme", "key_id")

HONESTY_NOTE = (
    "Verdicts are grounded, not proof of truth about the world. For arithmetic (CLAIM) "
    "claims, VERIFIED means every operand traces to a fact or a prior derived value AND the "
    "asserted number equals the recompute. For retrieval (FACT) claims, VERIFIED means the "
    "quoted text appears verbatim (whitespace- and case-normalized) in the cited source — it "
    "grounds the quote to the source, not the source to reality. UNGROUNDED means an invented "
    "operand or an invented source id. FAILED means the checkable assertion is false (wrong "
    "arithmetic, or a quote not in the source). UNCHECKABLE claims are counted, never hidden. "
    "coverage_ratio = checkable / total. A signature, when present, is HMAC-SHA256: it proves "
    "the certificate was made by a holder of the signing key (shared-key authenticity, verified "
    "with that key), NOT a public signature anyone can check without the secret."
)


def _digest(body: dict) -> str:
    """sha256 over the canonical JSON of the signable content (excludes meta)."""
    signable = {k: v for k, v in body.items() if k not in _META_FIELDS}
    canonical = json.dumps(signable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _claim_dict(i: int, cv: checker.ClaimVerdict) -> dict:
    base = {
        "id": f"c{i}",
        "text": cv.text,
        "kind": cv.kind,
        # The verdict the checker reached at build time. NOT authoritative: a
        # verifier recomputes it. The name says exactly what it is.
        "verdict_at_build": cv.verdict,
        "detail": cv.detail,
    }
    if cv.kind == "retrieval":
        base.update({
            "quote": cv.quote,
            "source_id": cv.source_id,
            "checker_id": checker.RETRIEVAL_CHECKER_ID,
            "found": cv.found,
        })
    else:
        base.update({
            "computation": cv.computation,
            "asserted_value": cv.asserted_value,
            "operands": cv.operands,
            "checker_id": checker.CHECKER_ID,
            "grounded": cv.grounded,
            "ungrounded_operands": cv.ungrounded_operands,
            "arithmetic": cv.arithmetic,
            "recomputed_value": cv.recomputed,
            "grounding_detail": cv.grounding_detail,
        })
    return base


def build(question, facts, model_output, model, sources=None, key=None) -> dict:
    """Assemble a certificate from a model output, recomputing every verdict.

    If `key` (bytes) is given, attach an HMAC-SHA256 signature over the digest.
    """
    sources = sources or []
    verdicts = checker.check_claims(model_output.claims, facts, sources)
    claims = [_claim_dict(i, cv) for i, cv in enumerate(verdicts, start=1)]

    body = {
        "certificate_version": CERTIFICATE_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "question": question,
        "facts": facts,
        "fact_values": checker.extract_numbers(facts),  # shown, not trusted
        "sources": sources,
        "answer": model_output.answer,
        "claims": claims,
        "coverage": checker.coverage([cv.verdict for cv in verdicts]),
        "honesty_note": HONESTY_NOTE,
    }
    body["digest"] = _digest(body)
    if key is not None:
        body["signature_scheme"] = signing.SCHEME
        body["key_id"] = signing.key_id(key)
        body["signature"] = signing.sign(body["digest"], key)
    return body


def _raw_from_claim(c: dict):
    from .llm import RawClaim
    if c.get("kind") == "retrieval":
        return RawClaim(kind="retrieval", text=c.get("text", ""),
                        source_id=c.get("source_id", ""), quote=c.get("quote", ""))
    return RawClaim(kind="arithmetic", text=c.get("text", ""),
                    computation=c.get("computation", ""),
                    asserted_text=c.get("asserted_value") or "")


def verify(cert: dict, key=None) -> dict:
    """Re-check a certificate from scratch. This is the trust boundary.

    Rebuilds each verdict — arithmetic grounding and retrieval quotes alike —
    from `facts` and `sources`. It never trusts `verdict_at_build`. If `key` is
    given and the certificate carries a signature, the signature is checked too.
    """
    raw = [_raw_from_claim(c) for c in cert.get("claims", [])]
    verdicts = checker.check_claims(raw, cert.get("facts", ""), cert.get("sources", []))

    fresh = []
    for claim, cv in zip(cert.get("claims", []), verdicts):
        fresh.append({
            "id": claim.get("id"),
            "kind": cv.kind,
            "text": cv.text,
            "verdict_at_build": claim.get("verdict_at_build"),
            "recomputed_verdict": cv.verdict,
            "agrees_with_certificate": cv.verdict == claim.get("verdict_at_build"),
            "detail": cv.detail,
        })

    stored_digest = cert.get("digest")
    digest_ok = (stored_digest == _digest(cert))

    signature = cert.get("signature")
    if not signature:
        signature_status = "unsigned"
    elif key is None:
        signature_status = "present-but-no-key"
    elif signing.verify_signature(stored_digest, signature, key):
        signature_status = "valid"
    else:
        signature_status = "invalid"

    return {
        "claims": fresh,
        "coverage": checker.coverage([cv.verdict for cv in verdicts]),
        "digest_ok": digest_ok,
        "stored_digest": stored_digest,
        "signature_status": signature_status,
        "key_id": cert.get("key_id"),
    }
