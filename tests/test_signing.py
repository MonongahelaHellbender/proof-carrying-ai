"""Tests for HMAC signing and signature verification.

Run: python3 tests/test_signing.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pcai import certificate, llm, signing


def test_sign_and_verify_roundtrip():
    key = os.urandom(32)
    digest = "sha256:abc123"
    assert signing.verify_signature(digest, signing.sign(digest, key), key) is True


def test_verify_fails_on_tampered_digest():
    key = os.urandom(32)
    sig = signing.sign("sha256:abc", key)
    assert signing.verify_signature("sha256:xyz", sig, key) is False


def test_verify_fails_on_wrong_key():
    sig = signing.sign("sha256:abc", os.urandom(32))
    assert signing.verify_signature("sha256:abc", sig, os.urandom(32)) is False


def _output():
    return llm.ModelOutput(answer="", raw="", claims=[
        llm.RawClaim(kind="arithmetic", text="t", computation="2 + 2", asserted_text="4")])


def test_signed_certificate_verifies():
    key = os.urandom(32)
    cert = certificate.build("q", "sum of 2 and 2", _output(), "m", key=key)
    rep = certificate.verify(cert, key=key)
    assert rep["digest_ok"] is True
    assert rep["signature_status"] == "valid"


def test_tampering_breaks_the_digest():
    key = os.urandom(32)
    cert = certificate.build("q", "sum of 2 and 2", _output(), "m", key=key)
    cert["claims"][0]["asserted_value"] = "5"          # tamper the content
    assert certificate.verify(cert, key=key)["digest_ok"] is False


def test_forged_digest_without_key_fails_signature():
    # The whole point: an attacker can recompute the public digest after tampering,
    # but cannot produce a matching signature without the secret key.
    key = os.urandom(32)
    cert = certificate.build("q", "sum of 2 and 2", _output(), "m", key=key)
    cert["claims"][0]["asserted_value"] = "5"
    cert["digest"] = certificate._digest(cert)          # re-hash the tampered content
    rep = certificate.verify(cert, key=key)
    assert rep["digest_ok"] is True                     # digest now matches content
    assert rep["signature_status"] == "invalid"         # but the signature does not


def test_unsigned_and_present_but_no_key():
    unsigned = certificate.build("q", "sum of 2 and 2", _output(), "m")
    assert certificate.verify(unsigned)["signature_status"] == "unsigned"
    signed = certificate.build("q", "sum of 2 and 2", _output(), "m", key=os.urandom(32))
    assert certificate.verify(signed)["signature_status"] == "present-but-no-key"


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            passed += 1
    print(f"\n{passed} tests passed")
