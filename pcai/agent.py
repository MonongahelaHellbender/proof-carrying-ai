"""Verified-value trajectory chain — a multi-step agent trajectory, each step with a signed receipt.

An agent takes several steps toward a goal. Each step produces its OWN signed
certificate. Later steps may use numbers ESTABLISHED by earlier steps — but only
numbers an earlier step VERIFIABLY grounded: the result of a correct computation
from grounded inputs, or a number quoted verbatim from a real source.

The trajectory verifier re-checks every step's receipt AND confirms the chain:
no step may treat as an established fact any number that a prior VERIFIED step did
not actually establish. That cross-step check catches a broken chain that per-step
verification alone would pass — the point of proof-carrying *agents* rather than
independent receipts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from . import certificate, checker, llm, signing

TRAJECTORY_VERSION = "0.1"


def _numbers_from_claim(claim: dict) -> list:
    """The numbers a single VERIFIED claim establishes for later steps:
    the recomputed result of a computation, or the numbers in a verified quote."""
    if claim.get("kind") == "retrieval":
        return checker.extract_numbers(claim.get("quote", ""))
    try:
        return [checker.recompute(claim.get("computation", ""))]
    except checker.UnsafeExpression:
        return []


def _established_numbers(claims) -> list:
    """Numbers a step establishes, per its build-time VERIFIED claims."""
    out = []
    for c in claims:
        if c.get("verdict_at_build") == checker.VERIFIED:
            out.extend(_numbers_from_claim(c))
    return out


def _trajectory_digest(step_records) -> str:
    step_digests = [s["certificate"].get("digest", "") for s in step_records]
    blob = json.dumps(step_digests, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _assemble(goal, initial_facts, sources, model, step_records, key) -> dict:
    traj = {
        "trajectory_version": TRAJECTORY_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "goal": goal,
        "initial_facts": initial_facts,
        "sources": sources,
        "steps": step_records,
        "trajectory_digest": _trajectory_digest(step_records),
    }
    if key is not None:
        traj["signature_scheme"] = signing.SCHEME
        traj["key_id"] = signing.key_id(key)
        traj["signature"] = signing.sign(traj["trajectory_digest"], key)
    return traj


def run(goal, initial_facts, sources, steps, model="llama3.2:3b", key=None) -> dict:
    """Run an agent trajectory.

    `steps` is a list of {name, kind ('retrieve'|'compute'), instruction} with an
    optional `establishes_as` label. Each step is answered by the local model,
    checked, and signed. A step's first verified number is carried forward under
    its label as a fact for later steps, so the compute step gets a clean number.
    """
    labeled: dict = {}
    step_records = []
    for i, step in enumerate(steps, start=1):
        aug_facts = initial_facts
        if labeled:
            extra = "; ".join(f"{k} = {checker._fmt(v)}" for k, v in labeled.items())
            aug_facts = f"{initial_facts} {extra}.".strip()

        if step["kind"] == "retrieve":
            out = llm.parse_output(llm.generate_facts(step["instruction"], sources, model=model),
                                   default_kind="retrieval")
            cert = certificate.build(step["instruction"], "", out, model, sources=sources, key=key)
        else:
            out = llm.parse_output(llm.generate(step["instruction"], aug_facts, model=model))
            cert = certificate.build(step["instruction"], aug_facts, out, model, key=key)

        new_nums = _established_numbers(cert.get("claims", []))
        if step.get("establishes_as") and new_nums:
            labeled[step["establishes_as"]] = new_nums[0]

        step_records.append({
            "n": i, "name": step["name"], "kind": step["kind"],
            "instruction": step["instruction"], "certificate": cert,
            "establishes": new_nums,
        })
    return _assemble(goal, initial_facts, sources, model, step_records, key)


def verify_trajectory(traj: dict, key=None) -> dict:
    """Re-check a trajectory from scratch: every receipt, and the chain.

    Independently rebuilds the pool of established numbers step by step, so it can
    tell whether each step only used facts that were actually established before it.
    """
    allowed = list(checker.extract_numbers(traj.get("initial_facts", "")))
    step_reports = []
    chain_ok = True

    for s in traj.get("steps", []):
        cert = s["certificate"]
        rep = certificate.verify(cert, key=key)

        # Chain integrity: every number this step treats as a fact must already be
        # allowed (initial facts, or established by a prior VERIFIED step).
        step_fact_nums = checker.extract_numbers(cert.get("facts", ""))
        injected = [n for n in step_fact_nums if not checker._member(n, allowed)]
        step_chain_ok = not injected and rep["digest_ok"]
        if key is not None and rep["signature_status"] == "invalid":
            step_chain_ok = False
        if not step_chain_ok:
            chain_ok = False

        # Grow the allowed pool from THIS step's claims, gated on the INDEPENDENT
        # re-check verdict (rep) — not the verdict stored in the certificate.
        for stored, fresh in zip(cert.get("claims", []), rep["claims"]):
            if fresh.get("recomputed_verdict") != checker.VERIFIED:
                continue
            for n in _numbers_from_claim(stored):
                if not checker._member(n, allowed):
                    allowed.append(n)

        step_reports.append({
            "n": s.get("n"), "name": s.get("name"), "kind": s.get("kind"),
            "digest_ok": rep["digest_ok"],
            "signature_status": rep["signature_status"],
            "coverage": rep["coverage"],
            "injected_facts": injected,
            "chain_ok": step_chain_ok,
        })

    recomputed = _trajectory_digest(traj.get("steps", []))
    trajectory_digest_ok = recomputed == traj.get("trajectory_digest")

    sig = traj.get("signature")
    if not sig:
        traj_sig = "unsigned"
    elif key is None:
        traj_sig = "present-but-no-key"
    elif signing.verify_signature(traj.get("trajectory_digest"), sig, key):
        traj_sig = "valid"
    else:
        traj_sig = "invalid"

    trajectory_ok = (chain_ok and trajectory_digest_ok
                     and traj_sig != "invalid")

    return {
        "steps": step_reports,
        "chain_ok": chain_ok,
        "trajectory_digest_ok": trajectory_digest_ok,
        "trajectory_signature": traj_sig,
        "trajectory_ok": trajectory_ok,
    }
