"""Local LLM step — the ONLY place a model is involved.

The model PROPOSES claims; the checker (pcai.checker) DISPOSES. It emits two
kinds of claim, both line-delimited (small local models handle "print these
lines" far better than JSON):

  CLAIM: <what the number means> ||| <arithmetic expression> ||| <result>
  FACT:  <the fact stated>        ||| <source id, e.g. S1>     ||| <verbatim quote>

Neither is trusted. A malformed line is dropped (an honest loss of coverage,
never a fabricated verified claim).
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

OLLAMA_HOST = "http://localhost:11434"

# The claim delimiter. Three pipes is vanishingly unlikely to appear inside a
# claim's own text, so splitting on it is safe.
SEP = "|||"

ARITHMETIC_PROMPT = """You answer questions that involve arithmetic, and you show your work so it can be checked.

Given FACTS and a QUESTION, respond in EXACTLY this format and nothing else:

ANSWER: <one or two sentences>
CLAIM: <what the number means> {sep} <arithmetic expression> {sep} <the resulting number>
CLAIM: <what the number means> {sep} <arithmetic expression> {sep} <the resulting number>

Rules:
- Each CLAIM line has exactly two "{sep}" separators.
- The middle field is an arithmetic expression using ONLY numbers and + - * / ( ).
  Do not put words, units, or currency symbols in the expression.
- Use the numbers given in FACTS.
- Write one CLAIM line for every number you state in the ANSWER.

FACTS:
{facts}

QUESTION:
{question}
"""

SOURCED_PROMPT = """You answer a question using ONLY the SOURCES, and you back every fact with an exact quote.

Respond in EXACTLY this format and nothing else:

ANSWER: <one or two sentences>
FACT: <the fact you are stating> {sep} <the source id, e.g. S1> {sep} <a quote copied EXACTLY from that source>
FACT: <the fact you are stating> {sep} <the source id, e.g. S1> {sep} <a quote copied EXACTLY from that source>

Rules:
- Each FACT line has exactly two "{sep}" separators.
- The third field must be copied VERBATIM from the cited source — word for word.
  Do NOT paraphrase, summarize, or reword. Keep each quote short.
- Only cite source ids that appear in SOURCES.
- Write one FACT line for every fact you state in the ANSWER.

SOURCES:
{sources}

QUESTION:
{question}
"""


@dataclass
class RawClaim:
    kind: str = "arithmetic"          # 'arithmetic' | 'retrieval'
    text: str = ""
    computation: str = ""             # arithmetic
    asserted_text: str = ""           # arithmetic
    source_id: str = ""               # retrieval
    quote: str = ""                   # retrieval


@dataclass
class ModelOutput:
    answer: str
    claims: list  # list[RawClaim]
    raw: str      # the full, unmodified model response (kept for the certificate)


def _generate_raw(prompt: str, model: str, host: str, timeout: int) -> str:
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["response"]


def generate(question: str, facts: str, model: str = "llama3.2:3b",
             host: str = OLLAMA_HOST, timeout: int = 180) -> str:
    """Arithmetic answer. temperature=0 for reproducible receipts."""
    return _generate_raw(ARITHMETIC_PROMPT.format(sep=SEP, facts=facts, question=question),
                         model, host, timeout)


def format_sources(sources) -> str:
    return "\n".join(f"[{s['id']}] {s['text']}" for s in sources)


def generate_facts(question: str, sources, model: str = "llama3.2:3b",
                   host: str = OLLAMA_HOST, timeout: int = 180) -> str:
    """Retrieval answer: facts backed by verbatim quotes from the sources."""
    return _generate_raw(
        SOURCED_PROMPT.format(sep=SEP, sources=format_sources(sources), question=question),
        model, host, timeout)


_QUOTE_CHARS = "\"'“”‘’"


def _unquote(s: str) -> str:
    """Strip a single pair of surrounding quote marks (small models add them)."""
    s = s.strip()
    if len(s) >= 2 and s[0] in _QUOTE_CHARS and s[-1] in _QUOTE_CHARS:
        return s[1:-1].strip()
    return s


def parse_output(raw: str, default_kind: str = "arithmetic") -> ModelOutput:
    """Extract the ANSWER line plus CLAIM (arithmetic) and FACT (retrieval) lines.

    Tolerant by design: scans every line for known prefixes; a small model often
    drops the CLAIM:/FACT: prefix but still emits the three ||| fields, so an
    unprefixed three-field line is parsed as `default_kind`. Surrounding quote
    marks are stripped. Malformed lines are dropped, not guessed at.
    """
    answer_parts: list[str] = []
    claims: list[RawClaim] = []
    for line in raw.splitlines():
        stripped = line.strip().lstrip("*# ").strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith("ANSWER:"):
            answer_parts.append(stripped[len("ANSWER:"):].strip())
            continue

        if upper.startswith("CLAIM:"):
            kind, body = "arithmetic", stripped[len("CLAIM:"):]
        elif upper.startswith("FACT:"):
            kind, body = "retrieval", stripped[len("FACT:"):]
        elif stripped.count(SEP) == 2:
            kind, body = default_kind, stripped
        else:
            continue

        fields = [_unquote(f) for f in body.split(SEP)]
        if len(fields) != 3:
            continue
        if kind == "retrieval":
            claims.append(RawClaim(kind="retrieval", text=fields[0],
                                   source_id=fields[1], quote=fields[2]))
        else:
            claims.append(RawClaim(kind="arithmetic", text=fields[0],
                                   computation=fields[1], asserted_text=fields[2]))

    answer = " ".join(p for p in answer_parts if p).strip()
    if not answer and claims:
        answer = "; ".join(cl.text for cl in claims)
    return ModelOutput(answer=answer, claims=claims, raw=raw)
