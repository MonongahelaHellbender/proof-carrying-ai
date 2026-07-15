#!/usr/bin/env python3
"""Proof-Carrying AI — command line loop.

  python3 cli.py --demo             arithmetic demo (Q1 costs)
  python3 cli.py --demo-facts       retrieval demo (Acme summary, quotes vs sources)
  python3 cli.py --demo-mixed       one certificate spanning both domains
  python3 cli.py --question "..." --facts "..."   your own arithmetic question
  python3 cli.py --verify CERT.json               re-check a certificate (no model)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcai import agent, certificate, llm, signing  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "pcai", "verifier_template.html")
MARKER = "const EMBEDDED_CERT = null; //__CERT__"

DEMO_FACTS = ("Q1 costs: salaries = 42000, cloud = 3500, travel = 1200. "
              "The quarter has 3 months.")
DEMO_QUESTION = "What was the total Q1 cost, and what was the average cost per month?"

DEMO_SOURCES = [
    {"id": "S1", "text": "Acme Corp reported Q1 revenue of $4.2 million, up 12% from the "
                         "prior quarter. The company added 30 new enterprise customers."},
    {"id": "S2", "text": "Acme's headcount grew to 145 employees by the end of Q1, with the "
                         "engineering team now at 60 people."},
]
DEMO_FACTS_QUESTION = "Summarize Acme's Q1: revenue, growth, and headcount."

AGENT_GOAL = "Estimate Acme's annualized revenue run-rate from Q1."
AGENT_FACTS = "A year has 4 quarters."
AGENT_SOURCES = [
    {"id": "S1", "text": "Acme Corp reported Q1 revenue of $4.2 million, up 12% from the "
                         "prior quarter. The company added 30 new enterprise customers."},
]
AGENT_STEPS = [
    {"name": "retrieve Q1 revenue", "kind": "retrieve", "establishes_as": "Q1 revenue in millions",
     "instruction": "What was Acme's Q1 revenue? Quote the exact figure from the sources."},
    {"name": "annualize", "kind": "compute",
     "instruction": "Compute the annualized revenue: multiply the Q1 revenue in millions by "
                    "the 4 quarters in a year. Put only numbers in the expression."},
]

_BADGE = {"VERIFIED": "[GREEN ]", "FAILED": "[RED   ]",
          "UNGROUNDED": "[AMBER ]", "UNCHECKABLE": "[GREY  ]"}


def render_verifier(cert: dict, out_path: str) -> None:
    """Inject the certificate into the standalone verifier template."""
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    html = html.replace(MARKER, f"const EMBEDDED_CERT = {json.dumps(cert)}; //__CERT__")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def _print_summary(cert: dict) -> None:
    cov = cert["coverage"]
    print(f"\nQ: {cert['question']}")
    print(f"A: {cert['answer']}\n")
    for c in cert["claims"]:
        print(f"  {_BADGE[c['verdict_at_build']]} ({c['kind']}) {c['text']}")
        print(f"           {c['detail']}")
    print(f"\ncoverage: {cov['verified']} verified / {cov['failed']} failed / "
          f"{cov['ungrounded']} ungrounded / {cov['uncheckable']} uncheckable  "
          f"(coverage_ratio = {cov['coverage_ratio']})")


def _finish(cert: dict, cert_path: str, html_path: str) -> None:
    os.makedirs(os.path.dirname(cert_path) or ".", exist_ok=True)
    with open(cert_path, "w", encoding="utf-8") as f:
        json.dump(cert, f, indent=2)
    render_verifier(cert, html_path)
    _print_summary(cert)
    if cert.get("signature"):
        print(f"\nsigned: {cert['signature_scheme']} (key {cert['key_id']})")
    print(f"certificate -> {cert_path}")
    print(f"live verifier -> {html_path}")


def run_arithmetic(question, facts, model, cert_path, html_path, key) -> None:
    print(f"Asking {model} (arithmetic) ...")
    out = llm.parse_output(llm.generate(question, facts, model=model))
    _finish(certificate.build(question, facts, out, model, key=key), cert_path, html_path)


def run_facts(question, sources, model, cert_path, html_path, key) -> None:
    print(f"Asking {model} (retrieval) ...")
    out = llm.parse_output(llm.generate_facts(question, sources, model=model), default_kind="retrieval")
    _finish(certificate.build(question, "", out, model, sources=sources, key=key), cert_path, html_path)


def run_mixed(model, cert_path, html_path, key) -> None:
    print(f"Asking {model} (arithmetic + retrieval) ...")
    a = llm.parse_output(llm.generate(DEMO_QUESTION, DEMO_FACTS, model=model))
    r = llm.parse_output(llm.generate_facts(DEMO_FACTS_QUESTION, DEMO_SOURCES, model=model),
                         default_kind="retrieval")
    combined = llm.ModelOutput(
        answer=(a.answer + "  " + r.answer).strip(),
        claims=a.claims + r.claims,
        raw=a.raw + "\n---\n" + r.raw)
    question = "Mixed demo — Q1 costs (arithmetic) and Acme Q1 summary (retrieval)."
    cert = certificate.build(question, DEMO_FACTS, combined, model, sources=DEMO_SOURCES, key=key)
    _finish(cert, cert_path, html_path)


def _print_trajectory(traj: dict) -> None:
    print(f"\nGOAL: {traj['goal']}")
    print(f"initial facts: {traj['initial_facts']}")
    for s in traj["steps"]:
        print(f"\n-- step {s['n']}: {s['name']} ({s['kind']}) --")
        for c in s["certificate"]["claims"]:
            print(f"   {_BADGE[c['verdict_at_build']]} {c['text']}")
            print(f"            {c['detail']}")
        if s["establishes"]:
            print(f"   establishes: {', '.join(str(n) for n in s['establishes'])}")


def _print_trajectory_report(rep: dict) -> None:
    print("\n== independent trajectory re-check ==")
    for s in rep["steps"]:
        inj = "" if not s["injected_facts"] else f"  INJECTED (un-established): {s['injected_facts']}"
        print(f"  step {s['n']} {s['name']}: chain_ok={s['chain_ok']} "
              f"digest_ok={s['digest_ok']} signature={s['signature_status']}{inj}")
    print(f"\nchain_ok: {rep['chain_ok']}   trajectory_digest_ok: {rep['trajectory_digest_ok']}"
          f"   trajectory_signature: {rep['trajectory_signature']}")
    print(f"TRAJECTORY_OK: {rep['trajectory_ok']}")


def run_agent(model, out_traj, key) -> None:
    print(f"Asking {model} (agent trajectory) ...")
    traj = agent.run(AGENT_GOAL, AGENT_FACTS, AGENT_SOURCES, AGENT_STEPS, model=model, key=key)
    os.makedirs(os.path.dirname(out_traj) or ".", exist_ok=True)
    with open(out_traj, "w", encoding="utf-8") as f:
        json.dump(traj, f, indent=2)
    _print_trajectory(traj)
    _print_trajectory_report(agent.verify_trajectory(traj, key=key))
    print(f"\ntrajectory -> {out_traj}")


def verify_only(path: str, key) -> None:
    with open(path, encoding="utf-8") as f:
        cert = json.load(f)
    report = certificate.verify(cert, key=key)
    print(f"digest_ok: {report['digest_ok']}")
    print(f"signature: {report['signature_status']}"
          + (f" (key {report['key_id']})" if report.get('key_id') else ""))
    for c in report["claims"]:
        flag = "" if c["agrees_with_certificate"] else "  <-- DISAGREES WITH CERTIFICATE"
        print(f"  {c['recomputed_verdict']:12} ({c['kind']}) {c['text']}{flag}")
        print(f"               {c['detail']}")
    cov = report["coverage"]
    print(f"\nrecomputed coverage: {cov['verified']} verified / {cov['failed']} failed / "
          f"{cov['ungrounded']} ungrounded / {cov['uncheckable']} uncheckable  "
          f"(ratio = {cov['coverage_ratio']})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Proof-Carrying AI")
    ap.add_argument("--demo", action="store_true", help="arithmetic demo")
    ap.add_argument("--demo-facts", action="store_true", help="retrieval demo")
    ap.add_argument("--demo-mixed", action="store_true", help="mixed arithmetic + retrieval demo")
    ap.add_argument("--demo-agent", action="store_true", help="proof-carrying agent trajectory demo")
    ap.add_argument("--question")
    ap.add_argument("--facts", default="")
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--verify", metavar="CERT.json", help="re-check a certificate and exit")
    ap.add_argument("--key", default=signing.DEFAULT_KEY_PATH,
                    help="signing key file (created if absent)")
    ap.add_argument("--no-sign", action="store_true", help="do not sign the certificate")
    ap.add_argument("--out-cert", default=os.path.join(HERE, "examples", "demo_certificate.json"))
    ap.add_argument("--out-html", default=os.path.join(HERE, "verify.html"))
    args = ap.parse_args()

    if args.verify:
        verify_only(args.verify, signing.load_key(args.key))
        return

    key = None if args.no_sign else signing.load_or_create_key(args.key)
    if key is not None:
        print(f"signing key: {args.key} (key {signing.key_id(key)})")

    if args.demo_agent:
        run_agent(args.model, os.path.join(HERE, "examples", "demo_trajectory.json"), key)
    elif args.demo_mixed:
        run_mixed(args.model, args.out_cert, args.out_html, key)
    elif args.demo_facts:
        run_facts(DEMO_FACTS_QUESTION, DEMO_SOURCES, args.model, args.out_cert, args.out_html, key)
    elif args.demo:
        run_arithmetic(DEMO_QUESTION, DEMO_FACTS, args.model, args.out_cert, args.out_html, key)
    elif args.question:
        run_arithmetic(args.question, args.facts, args.model, args.out_cert, args.out_html, key)
    else:
        ap.error("provide --demo, --demo-facts, --demo-mixed, --question, or --verify")


if __name__ == "__main__":
    main()
