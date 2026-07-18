# Related work — name-collision resolution and lineage

**Scope note.** This document is a *name-collision resolution* plus a lineage statement. It is
deliberately NOT a systematic prior-art survey of verification, attribution, or provenance, and
should not be read as one.

**Verification levels differ by section, on purpose:**

- The **PCAA / CAVA** sections were verified against those papers' full texts on 2026-07-17 (not
  abstracts alone). Every claim about them was checked against that paper's own words; quotes are
  verbatim.
- The **Wider lineage** section was identified and citation-checked (titles, venues, identifiers) but
  those works were **not** read in full text. They are cited as ancestry, not differentiated claim by
  claim.

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
   certificate reads VERIFIED). **The idea itself is decades old and is not claimed here:** value
   lineage is foundational in database provenance (Buneman/Khanna/Tan, ICDT 2001; Green/
   Karvounarakis/Tannen, PODS 2007) and in information-flow and taint analysis (Denning, CACM 1976).
   What is new is the *application*: lineage over MODEL-GENERATED values, enforced by a verifier with
   no model in its verdict path, surfacing the un-established value at the step that USES it. See
   **Wider lineage** below.
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

## Wider lineage (the neighbours a referee will expect)

Three established lines of work are the ancestors of this repo's three mechanisms. **None is claimed
as novel here.** Each is named so the composition can be judged on what it actually adds.

1. **Deterministic recomputation instead of trusting model arithmetic** — *PAL: Program-aided
   Language Models* (Gao et al., arXiv:2211.10435, ICML 2023) and *Program of Thoughts Prompting*
   (Chen et al., arXiv:2211.12588, TMLR 2023). Both offload the computation from the model to an
   external runtime. This repo's arithmetic lane is the same move, with two differences: the
   expression is recorded in a portable certificate rather than consumed inline, and the operands
   must additionally be GROUNDED — each must trace to a given fact or a prior verified result.

2. **Attribution / verifiable generation** — *ALCE* (Gao et al., arXiv:2305.14627, EMNLP 2023),
   attributed question answering (Bohnet et al., 2022), and the surrounding attribution-evaluation
   line (FActScore, RARR). Checking that a generated statement is supported by a cited source is an
   established task with established benchmarks. This repo's retrieval lane is a deliberately
   **weaker and fully deterministic** version of it — verbatim span containment, with no model and no
   entailment judgement anywhere in the verdict path. That trades semantic coverage for a check that
   cannot itself hallucinate, and the cost is named in the README: a faithful paraphrase reads as
   FAILED.

3. **Data provenance and information-flow / taint analysis** — Buneman, Khanna & Tan, *Why and
   Where: A Characterization of Data Provenance* (ICDT 2001); Green, Karvounarakis & Tannen,
   *Provenance Semirings* (PODS 2007); Denning, *A Lattice Model of Secure Information Flow*
   (CACM 19(5), 1976). These established value lineage and the discipline that a derived value is
   only as trustworthy as what it was derived from. The trajectory chain here is that discipline
   applied to values a language model produced.

**What this repo composes, stated so it can be attacked:** deterministic recomputation (1), verbatim
source grounding (2), and value lineage (3) — carried together in one signed certificate, re-derived
by a verifier with no model in its verdict path, and reported against a published coverage
denominator. Every ingredient is prior art. The claim is the composition, and specifically enforcing
lineage over model-generated values with a model-free checker.
