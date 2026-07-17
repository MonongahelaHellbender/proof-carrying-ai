"""Tests for verified-value trajectory chains and the cross-step chain check.

These build the step certificates directly (no model) so the chain logic is
tested deterministically.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pcai import agent, certificate, llm

S1 = [{"id": "S1", "text": "Acme Corp reported Q1 revenue of $4.2 million, up 12% from the prior quarter."}]
INITIAL = "A year has 4 quarters."


def _retrieve_cert(quote, key):
    out = llm.ModelOutput(answer="", raw="", claims=[
        llm.RawClaim(kind="retrieval", text="Q1 revenue", source_id="S1", quote=quote)])
    return certificate.build("retrieve", "", out, "m", sources=S1, key=key)


def _compute_cert(facts, expr, asserted, key):
    out = llm.ModelOutput(answer="", raw="", claims=[
        llm.RawClaim(kind="arithmetic", text="annualized", computation=expr, asserted_text=asserted)])
    return certificate.build("compute", facts, out, "m", key=key)


def _traj(step_certs, key):
    records = []
    for i, (name, kind, cert) in enumerate(step_certs, start=1):
        records.append({"n": i, "name": name, "kind": kind, "instruction": "",
                        "certificate": cert, "establishes": agent._established_numbers(cert["claims"])})
    return agent._assemble("goal", INITIAL, S1, "m", records, key)


def test_valid_chain():
    key = os.urandom(32)
    c1 = _retrieve_cert("Q1 revenue of $4.2 million", key)            # VERIFIED, establishes 4.2
    c2 = _compute_cert(INITIAL + " Established from prior steps: 4.2", "4.2 * 4", "16.8", key)
    rep = agent.verify_trajectory(_traj([("r", "retrieve", c1), ("c", "compute", c2)], key), key)
    assert rep["trajectory_ok"] is True
    assert rep["chain_ok"] is True
    assert rep["trajectory_signature"] == "valid"


def test_broken_chain_is_caught_though_each_step_passes():
    # Step 1 quotes text NOT in the source -> FAILED, establishes nothing.
    # Step 2 pretends 4.2 was established; its OWN certificate is VERIFIED, but the
    # trajectory verifier flags 4.2 as an injected (un-established) fact.
    key = os.urandom(32)
    c1 = _retrieve_cert("Q1 revenue of $9.9 billion", key)           # not in source -> FAILED
    c2 = _compute_cert(INITIAL + " Established from prior steps: 4.2", "4.2 * 4", "16.8", key)
    assert c2["claims"][0]["verdict_at_build"] == "VERIFIED"          # step 2 alone looks fine
    rep = agent.verify_trajectory(_traj([("r", "retrieve", c1), ("c", "compute", c2)], key), key)
    assert rep["chain_ok"] is False                                  # but the chain is broken
    assert rep["trajectory_ok"] is False
    assert any(abs(n - 4.2) < 1e-9 for n in rep["steps"][1]["injected_facts"])


def test_tampered_step_breaks_trajectory_digest():
    key = os.urandom(32)
    c1 = _retrieve_cert("Q1 revenue of $4.2 million", key)
    c2 = _compute_cert(INITIAL + " Established from prior steps: 4.2", "4.2 * 4", "16.8", key)
    traj = _traj([("r", "retrieve", c1), ("c", "compute", c2)], key)
    traj["steps"][0]["certificate"]["digest"] = "sha256:deadbeef"    # tamper a step
    rep = agent.verify_trajectory(traj, key)
    assert rep["trajectory_digest_ok"] is False
    assert rep["trajectory_ok"] is False


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            passed += 1
    print(f"\n{passed} tests passed")
