#!/usr/bin/env python3
"""Build demo.html — a no-install demo page with real examples embedded.

Takes the artifacts produced by the cli demos, re-signs them with the PUBLIC demo
key (examples/demo_signing.key, which has zero security value and is published so
readers can exercise the verify path), writes them to examples/sample_*.json, and
renders demo.html with both embedded.

  python3 tools/build_demo.py

Re-signing keeps the maintainer's real signing key out of published artifacts while
still showing the signature field. It is deterministic: same content, same key,
same signature.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from pcai import agent, certificate, signing  # noqa: E402

DEMO_KEY_PATH = os.path.join(HERE, "examples", "demo_signing.key")
TEMPLATE = os.path.join(HERE, "pcai", "verifier_template.html")
EXAMPLES_MARKER = "const EMBEDDED_EXAMPLES = null; //__EXAMPLES__"
OUT_HTML = os.path.join(HERE, "demo.html")


def _resign_certificate(cert: dict, key: bytes) -> dict:
    """Recompute the digest over the (unchanged) content and sign with `key`."""
    out = {k: v for k, v in cert.items()
           if k not in ("digest", "signature", "signature_scheme", "key_id")}
    out["digest"] = certificate._digest(out)
    out["signature_scheme"] = signing.SCHEME
    out["key_id"] = signing.key_id(key)
    out["signature"] = signing.sign(out["digest"], key)
    return out


def _resign_trajectory(traj: dict, key: bytes) -> dict:
    out = dict(traj)
    out["steps"] = [dict(s, certificate=_resign_certificate(s["certificate"], key))
                    for s in traj.get("steps", [])]
    out["trajectory_digest"] = agent._trajectory_digest(out["steps"])
    out["signature_scheme"] = signing.SCHEME
    out["key_id"] = signing.key_id(key)
    out["signature"] = signing.sign(out["trajectory_digest"], key)
    return out


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main() -> None:
    key = signing.load_or_create_key(DEMO_KEY_PATH)
    print(f"demo key {signing.key_id(key)} (public, zero security value)")
    examples = []

    traj = _load(os.path.join(HERE, "examples", "demo_trajectory.json"))
    if traj:
        traj = _resign_trajectory(traj, key)
        _write(os.path.join(HERE, "examples", "sample_trajectory.json"), traj)
        rep = agent.verify_trajectory(traj, key=key)
        print(f"  trajectory sample: trajectory_ok={rep['trajectory_ok']} "
              f"signature={rep['trajectory_signature']}")
        examples.append({"label": "Agent trajectory (verified-value chain)", "data": traj})

    cert = _load(os.path.join(HERE, "examples", "demo_certificate.json"))
    if cert:
        cert = _resign_certificate(cert, key)
        _write(os.path.join(HERE, "examples", "sample_certificate.json"), cert)
        rep = certificate.verify(cert, key=key)
        print(f"  certificate sample: digest_ok={rep['digest_ok']} "
              f"signature={rep['signature_status']}")
        examples.append({"label": "Single certificate (both domains)", "data": cert})

    if not examples:
        sys.exit("no source artifacts found — run: python3 cli.py --demo-agent  and  --demo-mixed")

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    html = html.replace(EXAMPLES_MARKER,
                        f"const EMBEDDED_EXAMPLES = {json.dumps(examples)}; //__EXAMPLES__")
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"demo -> {OUT_HTML}  ({len(examples)} examples embedded)")


if __name__ == "__main__":
    main()
