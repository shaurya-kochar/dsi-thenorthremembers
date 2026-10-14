"""Component 6 — Synthesis Engine.

v0.1 baseline = "naive RAG": top-k chunks → LLM → JSON answer whose every claim
cites source labels [S1]..[Sk]. Citations are validated against what was
actually retrieved; claims citing nothing (or a label that doesn't exist) are
marked ``unsupported``.

The baseline deliberately has no resolved entities (it must guess that "Ravi S." ==
"Ravi Sharma") and no detected conflicts. The full pipeline (issue #7, task D3) adds
both to the prompt: a RESOLVED ENTITIES block with the names linked by the resolver,
and a KNOWN CONFLICTS block citing both sides of every relevant conflict with their
[S#] labels, which the model must mention, saying whether each changes the answer.

Confidence is computed here from the evidence, not asked of the model: low when the
system fell back, a claim is unsupported or the verdict is UNCERTAIN; medium when a
relevant conflict is open or the best evidence is weak; high otherwise.
"""

from __future__ import annotations

import json
import re

from .models import Answer, Chunk, Citation, Claim, Conflict, Entity, RetrievedChunk

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

FULL_SYSTEM_PROMPT = """You are InfoBridge, an assistant for the coordinator of Hyderabad Runners, a volunteer-run running NGO.
You answer the coordinator's question using ONLY the numbered sources provided.

Rules:
- Every claim must cite at least one source label, e.g. [S2] or [S1][S4]. Never cite a label that is not listed.
- Do not use outside knowledge. If the sources do not contain the answer, say so.
- RESOLVED ENTITIES lists names that InfoBridge has linked to the same person, event or programme across sources,
  with the evidence. Treat those names as the same entity; do not merge any other names.
- KNOWN CONFLICTS lists values on which the sources disagree. Mention every conflict relevant to the question in the
  summary and in a claim, cite both sides with their [S#] labels, and say whether it changes the answer.
- If sources disagree in a way that is not listed, say so explicitly and cite both sides.
- Only mention people who are relevant to the question.
- Be concise: one fact per claim.

Return JSON with exactly these keys:
{
  "verdict": "YES" | "NO" | "UNCERTAIN" | null,   // null when the question is not a yes/no question
  "summary": "2-4 sentence answer with inline [S#] citations",
  "claims": [{"text": "one factual claim", "citations": ["S1"]}]
}"""

LABEL = re.compile(r"\[?(S\d+)\]?")
WEAK_EVIDENCE = 0.4  # best retrieval score below this -> at most medium confidence


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


def _labels(chunk_ids: list[str], label_map: dict[str, RetrievedChunk]) -> str:
    label_of = {r.chunk.chunk_id: label for label, r in label_map.items()}
    cited = [f"[{label_of[c]}]" for c in dict.fromkeys(chunk_ids) if c in label_of]
    return "".join(cited) or f"({chunk_ids[0]}, not retrieved)"


def format_conflicts(conflicts: list[Conflict], label_map: dict[str, RetrievedChunk]) -> str:
    """K1 medical_clearance_date of Ravi Sharma: "2026-03-15" [S4] vs "22 June 2026" (= 2026-06-22) [S7]"""
    lines = []
    for i, c in enumerate(conflicts, start=1):
        sides = " vs ".join(
            f'"{v.raw_value}"' + (f" (= {v.value})" if v.value != v.raw_value else "")
            + " " + _labels(v.sources or [v.chunk_id], label_map) for v in c.values)
        hint = f"; suggestion: {c.suggestion}" if c.suggestion else ""
        lines.append(f"K{i} {c.attribute} of {c.entity_name or c.entity_id}: {sides}{hint}")
    return "KNOWN CONFLICTS (detected across sources; mention every relevant one):\n" + ("\n".join(lines) or "none")


def format_entities(entities: list[Entity], label_map: dict[str, RetrievedChunk]) -> str:
    """E1 Ravi Sharma (person): "Ravi Sharma" [S1]; "R. Sharma" [S3]; evidence: phone 9848022314 shared ..."""
    retrieved_ids = {r.chunk.chunk_id for r in label_map.values()}
    lines = []
    for i, e in enumerate(entities, start=1):
        forms: dict[str, list[str]] = {}
        for m in e.mentions:
            forms.setdefault(m.text, []).append(m.chunk_id)
        shown = [f'"{text}" {_labels(ids, label_map)}' for text, ids in forms.items() if set(ids) & retrieved_ids]
        evidence = "; ".join(e.match_evidence[:4])
        lines.append(f"E{i} {e.canonical_name} ({e.entity_type}): " + ", ".join(shown)
                     + (f"; evidence: {evidence}" if evidence else ""))
    return "RESOLVED ENTITIES (the question is about these):\n" + ("\n".join(lines) or "none")


def cite_conflicts(retrieved: list[RetrievedChunk], conflicts: list[Conflict],
                   chunks: dict[str, Chunk]) -> tuple[list[RetrievedChunk], list[Conflict]]:
    """Make both sides of every conflict citable: point each value at the best-ranked retrieved chunk
    that states it (for a person, their own row), or append its chunk to the evidence with the next rank."""
    retrieved = list(retrieved)
    by_id = {r.chunk.chunk_id: r for r in retrieved}
    out = []
    for c in conflicts:
        values = []
        for v in c.values:
            sources = v.sources or [v.chunk_id]
            chunk_id = min((s for s in sources if s in by_id), key=lambda s: by_id[s].rank, default=None)
            if chunk_id is None and v.chunk_id in chunks:
                chunk_id = v.chunk_id
                by_id[chunk_id] = RetrievedChunk(chunk=chunks[chunk_id], score=0.0, rank=len(retrieved) + 1,
                                                 channels=[f"conflict:{c.conflict_id}"])
                retrieved.append(by_id[chunk_id])
            values.append(v.model_copy(update={"chunk_id": chunk_id or v.chunk_id}))
        out.append(c.model_copy(update={"values": values}))
    return retrieved, out


def _field(conflict: Conflict) -> str:
    name = f" of {conflict.entity_name}" if conflict.entity_name else ""
    return f"the {conflict.attribute.replace('_', ' ')}{name}"


def assess_confidence(answer: Answer, retrieved: list[RetrievedChunk]) -> tuple[str, str]:
    """(confidence, one-sentence reason) from the evidence; conflicts are taken in order of relevance."""
    unsupported = sum(c.unsupported for c in answer.claims)
    best = max((r.score for r in retrieved), default=0.0)
    if answer.fallback:
        return "low", "Not enough reliable evidence was found to answer the question."
    if unsupported:
        return "low", f"{unsupported} of {len(answer.claims)} claims do not cite a retrieved source."
    if answer.verdict == "UNCERTAIN":
        return "low", "The sources do not settle the question."
    if answer.conflicts:
        first = answer.conflicts[0]
        values = " vs ".join(v.value for v in first.values)
        who = "Two sources disagree" if len(first.values) == 2 else f"{len(first.values)} sources disagree"
        more = len(answer.conflicts) - 1
        rest = f", and {more} more conflict{'s' if more > 1 else ''} {'are' if more > 1 else 'is'} open" if more else ""
        return "medium", f"{who} on {_field(first)} ({values}){rest}."
    if best < WEAK_EVIDENCE:
        return "medium", f"The best matching evidence is weak (score {best:.2f})."
    return "high", "Every claim cites a source and no source disagrees."


def _finish(answer: Answer, retrieved: list[RetrievedChunk], conflicts: list[Conflict] | None) -> Answer:
    answer.conflicts = list(conflicts or [])
    answer.confidence, answer.confidence_reason = assess_confidence(answer, retrieved)
    return answer


class LLMSynthesizer:
    """Naive RAG (baseline), or conflict-aware RAG when conflicts / entities are given."""

    def __init__(self, llm) -> None:
        self.llm = llm
        self.name = f"rag-baseline/{llm.name}"

    def synthesize(self, question: str, retrieved: list[RetrievedChunk], conflicts: list[Conflict] | None = None,
                   entities: list[Entity] | None = None) -> Answer:
        sources, label_map = format_sources(retrieved)
        if conflicts is None and entities is None:  # the v0.1 prompt, unchanged (and its cache entries reused)
            system, prompt = SYSTEM_PROMPT, f"SOURCES:\n{sources}\n\nQUESTION: {question}"
        else:
            system = FULL_SYSTEM_PROMPT
            prompt = (f"SOURCES:\n{sources}\n\n{format_entities(entities or [], label_map)}\n\n"
                      f"{format_conflicts(conflicts or [], label_map)}\n\nQUESTION: {question}")
        data = _parse_json(self.llm.generate_json(system, prompt))
        name = self.name if conflicts is None and entities is None else f"rag/{self.llm.name}"
        return _finish(_build_answer(question, data, label_map, name), retrieved, conflicts)


class ExtractiveSynthesizer:
    """Retrieval-only lower bound: returns the top chunks verbatim as claims.

    Needs no API key, so the whole pipeline + evaluation can run offline.
    """

    name = "extractive"

    def __init__(self, n_claims: int = 5) -> None:
        self.n_claims = n_claims

    def synthesize(self, question: str, retrieved: list[RetrievedChunk], conflicts: list[Conflict] | None = None,
                   entities: list[Entity] | None = None) -> Answer:
        _, label_map = format_sources(retrieved)
        top = list(label_map.items())[: self.n_claims]
        data = {
            "verdict": None,
            "summary": "Most relevant evidence: " + " ".join(f"[{l}]" for l, _ in top),
            "claims": [{"text": r.chunk.text, "citations": [l]} for l, r in top],
        }
        return _finish(_build_answer(question, data, label_map, self.name), retrieved, conflicts)


def fallback_answer(question: str, retrieved: list[RetrievedChunk], backend: str) -> Answer:
    """Assisted-search mode (Design Doc §3.5): don't guess, point to where to look."""
    _, label_map = format_sources(retrieved[:3])
    answer = _build_answer(question, {"verdict": None, "summary": ""}, label_map, backend)
    docs = ", ".join(dict.fromkeys(r.chunk.doc_id for r in retrieved[:3])) or "none"
    answer.summary = f"Not enough reliable evidence to answer this. Closest sources to check: {docs}."
    answer.fallback = True
    return _finish(answer, retrieved, None)
