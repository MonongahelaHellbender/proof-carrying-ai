# Related work — the pre-public gate

Verified against the papers' full texts on 2026-07-17 (not abstracts alone). Every claim below about
another paper was checked against that paper's own words; quotes are verbatim.

## The name collision that must be addressed before anything public

**Proof-Carrying Agent Actions (PCAA)** — arXiv 2606.04104 (June 2026), *Proof-Carrying Agent
Actions: Model-Agnostic Runtime Governance for Heterogeneous Agent Systems.*
**Published BEFORE this repo's v0.5 (2026-07-15) used the phrase "proof-carrying agents."** The name
is taken in the agent context and any public artifact from this repo must differentiate explicitly.

**CAVA** — arXiv 2607.13716 (July 2026), *Canonical Action Verification and Attestation for Runtime
Governance of Agentic AI Systems* — positions itself "below Proof-Carrying Agent Actions (PCAA):
PCAA defines the deployer-owned route-review-prove governance process, while CAVA defines the stable
action object that process governs."

## Same name, different axis — the four checked discriminators

Checked in PCAA's full text (2606.04104v1):

1. **What the verifier re-derives.** PCAA recomputes *governance* state ("an active comparison
   between stored governance state and recomputed governance state under the current replay
   contract") — routing, policy snapshots, manifests. It does NOT redo arithmetic or re-check quoted
   spans against sources. This repo's verifier re-derives every CONTENT verdict itself (Python and
   independently in browser JS) and never trusts the certificate's stored verdict.
2. **What the certificate attests.** PCAA: authorization and policy path — "what action was
   authorized, under whose authority, with what approval semantics" (approval receipts,
   enforceability classes, boundary facts). This repo: whether the claim CONTENT is grounded and
   correct (asserted arithmetic == recompute; quoted span verbatim in the cited source).
3. **Cross-step value provenance.** Absent in PCAA — its five checkpoints sequence actions, but no
   rule restricts a later step's use of NUMBERS to those a prior verified step established. That
   chain rule is this repo's v0.5 core (a broken chain is caught even when each step's own
   certificate reads VERIFIED).
4. **Coverage honesty.** PCAA has a structurally similar concept — "receipt completeness"
   ρ(a) = |expected ∩ observed| / |expected| receipts, reported at 0.516 — but over RECEIPTS
   OBSERVED, not over CLAIMS CHECKABLE. Convergent honesty discipline, different denominator. Cite
   it as kin; do not claim the coverage idea as unique.

**Honest summary: PCAA/CAVA govern whether an action was APPROVED and can be replayed; this repo
verifies whether an answer's CONTENT is true to its own arithmetic and sources. Complementary, not
competing — this checker could sit inside a PCAA-governed step as the content-correctness layer the
governance stack explicitly does not provide.**

## Naming consequence (decision: Melissa's)

The phrase "proof-carrying agents" should not be used publicly as if coined here — PCAA predates it
in this niche. Recommended: keep the repo name (proof-carrying-ai; the proof-carrying lineage is
Necula's, see below, and the ANSWER/content scope is distinct), rename the v0.5 feature to
**verified-value trajectory chain** (or similar), and cite PCAA/CAVA with the differentiation above
wherever the agent feature is described.

## Shared lineage

- **Necula, Proof-Carrying Code (POPL 1997)** — the common ancestor; PCAA cites it (their ref [9]),
  and this repo inherits the same inversion (the artifact carries what makes it checkable; the
  verifier is small and trusts nothing else).
- In-house kin: agent-trace-shield (verbatim grounding vs a tool log), claim-guard (recompute),
  oracle-shield (deterministic oracles), the coverage-denominator discipline across the assurance
  lane.
