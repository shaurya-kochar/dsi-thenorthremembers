"""Component 6 — Synthesis Engine.

v0.1 baseline = "naive RAG": top-k chunks → LLM → JSON answer whose every claim
cites source labels [S1]..[Sk]. Citations are validated against what was
actually retrieved; claims citing nothing (or a label that doesn't exist) are
marked ``unsupported``.

What the baseline deliberately does NOT have (added in Hack 1):
  * resolved entities  → it must guess that "Ravi S." == "Ravi Sharma"
  * detected conflicts → it may or may not notice contradictions on its own;
                         ``Answer.conflicts`` is always empty
"""

from __future__ import annotations

import json
import re

from .models import Answer, Citation, Claim, RetrievedChunk

SYSTEM_PROMPT = """You are InfoBridge, an assistant for the coordinator of Hyderabad Runners, a volunteer-run running NGO.
You answer the coordinator's question using ONLY the numbered sources provided.

Rules:
- Every claim must cite at least one source label, e.g. [S2] or [S1][S4]. Never cite a label that is not listed.
- Do not use outside knowledge. If the sources do not contain the answer, say so.
- Different sources may refer to the same person or event with different names; only treat them as the same if the sources make that clear.
- If sources disagree with each other, say so explicitly and cite both sides.
- Be concise: one fact per claim.

Return JSON with exactly these keys:
{
  "verdict": "YES" | "NO" | "UNCERTAIN" | null,   // null when the question is not a yes/no question
  "summary": "2-4 sentence answer with inline [S#] citations",
  "claims": [{"text": "one factual claim", "citations": ["S1"]}]
}"""

LABEL = re.compile(r"\[?(S\d+)\]?")


def format_sources(retrieved: list[RetrievedChunk]) -> tuple[str, dict[str, RetrievedChunk]]:
    label_map = {f"S{r.rank}": r for r in retrieved}
    lines = [f"[{label}] ({r.chunk.doc_id}, {r.chunk.locator}) {r.chunk.text}" for label, r in label_map.items()]
    return "\n".join(lines), label_map


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        return json.loads(match.group(0)) if match else {}


def _build_answer(question: str, data: dict, label_map: dict[str, RetrievedChunk], backend: str) -> Answer:
    claims, used = [], set()
    for c in data.get("claims") or []:
        if not isinstance(c, dict) or not c.get("text"):
            continue
        labels = [m.group(1) for raw in c.get("citations") or [] for m in [LABEL.fullmatch(str(raw).strip())] if m]
        valid = [l for l in labels if l in label_map]
        used.update(valid)
        claims.append(Claim(text=c["text"], citations=labels, unsupported=not valid or len(valid) != len(labels)))

    summary = str(data.get("summary") or "")
    used.update(l for l in LABEL.findall(summary) if l in label_map)

    verdict = data.get("verdict")
    verdict = str(verdict).upper() if verdict not in (None, "", "null") else None

    citations = [
        Citation(label=l, chunk_id=label_map[l].chunk.chunk_id, doc_id=label_map[l].chunk.doc_id,
                 locator=label_map[l].chunk.locator, quote=label_map[l].chunk.text)
        for l in sorted(used, key=lambda x: int(x[1:]))
    ]
    return Answer(question=question, verdict=verdict, summary=summary, claims=claims, citations=citations,
                  retrieved=list(label_map.values()), backend=backend)


class LLMSynthesizer:
    """Naive RAG baseline."""

    def __init__(self, llm) -> None:
        self.llm = llm
        self.name = f"rag-baseline/{llm.name}"

    def synthesize(self, question: str, retrieved: list[RetrievedChunk]) -> Answer:
        sources, label_map = format_sources(retrieved)
        prompt = f"SOURCES:\n{sources}\n\nQUESTION: {question}"
        data = _parse_json(self.llm.generate_json(SYSTEM_PROMPT, prompt))
        return _build_answer(question, data, label_map, self.name)


class ExtractiveSynthesizer:
    """Retrieval-only lower bound: returns the top chunks verbatim as claims.

    Needs no API key, so the whole pipeline + evaluation can run offline.
    """

    name = "extractive"

    def __init__(self, n_claims: int = 5) -> None:
        self.n_claims = n_claims

    def synthesize(self, question: str, retrieved: list[RetrievedChunk]) -> Answer:
        _, label_map = format_sources(retrieved)
        top = list(label_map.items())[: self.n_claims]
        data = {
            "verdict": None,
            "summary": "Most relevant evidence: " + " ".join(f"[{l}]" for l, _ in top),
            "claims": [{"text": r.chunk.text, "citations": [l]} for l, r in top],
        }
        return _build_answer(question, data, label_map, self.name)


def fallback_answer(question: str, retrieved: list[RetrievedChunk], backend: str) -> Answer:
    """Assisted-search mode (Design Doc §3.5): don't guess, point to where to look."""
    _, label_map = format_sources(retrieved[:3])
    answer = _build_answer(question, {"verdict": None, "summary": ""}, label_map, backend)
    docs = ", ".join(dict.fromkeys(r.chunk.doc_id for r in retrieved[:3])) or "none"
    answer.summary = f"Not enough reliable evidence to answer this. Closest sources to check: {docs}."
    answer.fallback = True
    return answer
