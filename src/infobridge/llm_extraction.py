"""Fact extraction from chat, PDF and e-mail text with an LLM (issue #4, task A second half).

One call per document (all of its chunks together) keeps the number of calls low on the
free tier, and responses are cached by ``GeminiLLM``. The model may only use the attribute
names from ``schema.ATTRIBUTES``; anything else is dropped. Each fact must name an entity
written in its document (in the cited chunk, or elsewhere in the same chat / PDF when a message
refers to it implicitly, e.g. "we have 12 confirmed" about the run named earlier).
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .extraction import fact_id
from .models import Chunk, Fact
from .normalise import normalise_value
from .schema import ATTRIBUTES

SYSTEM = """You extract facts from the records of Hyderabad Runners, a volunteer-run running NGO.
Read the numbered chunks and return every fact they state as (entity, attribute, value).

Rules:
- attribute must be one of the allowed attributes listed below. Skip anything else.
- entity is the person, event, programme or place the fact is about, written exactly as it appears in that chunk
  (or, if the chunk only refers to it implicitly, as it is named elsewhere in this document)
  (e.g. "Ravi S.", "Batch B", "Sunday Long Run", "station 2"). A programme's start date or deadline is about the
  programme; a run's time, distance or meeting point is about the event; crates and opening times are about the station.
- value is the value as written in the text (e.g. "22 June 2026", "5:30", "12 confirmed").
- chunk is the label of the chunk the fact comes from.
- Only facts the text states. Do not guess. Return {"facts": []} if there are none.

Return JSON: {"facts": [{"chunk": "C1", "entity": "...", "entity_type": "person|event|programme|location",
"attribute": "...", "value": "..."}]}"""

log = logging.getLogger(__name__)

ALLOWED = {k: v for k, v in ATTRIBUTES.items() if k not in ("mention", "full_name")}


def _parse(raw: str) -> list[dict]:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        data = json.loads(match.group(0)) if match else {}
    facts = data.get("facts", []) if isinstance(data, dict) else data
    return [f for f in facts if isinstance(f, dict)]


class LLMFactExtractor:
    """Callable for ``InformationExtractor(text_extractor=...)``."""

    def __init__(self, llm, skip_prefixes: tuple[str, ...] = ("public_",), workers: int = 2):
        self.llm = llm
        self.failed: list[str] = []  # documents whose extraction failed (reported, not fatal)
        self.skip_prefixes = skip_prefixes
        self.workers = workers

    def prompt(self, chunks: list[Chunk]) -> str:
        attributes = "\n".join(f"- {k}: {v}" for k, v in ALLOWED.items())
        body = "\n".join(f"[C{i}] {c.text}" for i, c in enumerate(chunks, start=1))
        return f"Allowed attributes:\n{attributes}\n\nChunks from {chunks[0].doc_id}:\n{body}"

    def __call__(self, chunks: list[Chunk]) -> list[Fact]:
        by_doc: dict[str, list[Chunk]] = defaultdict(list)
        for c in chunks:
            if not c.doc_id.startswith(self.skip_prefixes):
                by_doc[c.doc_id].append(c)
        # documents are independent, so up to `workers` calls run at once (one call per document)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(self.extract_document, by_doc.values()))
        return [f for doc_facts in results for f in doc_facts]

    def extract_document(self, chunks: list[Chunk]) -> list[Fact]:
        labels = {f"C{i}": c for i, c in enumerate(chunks, start=1)}
        try:
            raw = self.llm.generate_json(SYSTEM, self.prompt(chunks), retries=6)
        except Exception as e:  # model overloaded / quota: keep the table facts and mentions, skip this document
            log.warning("LLM extraction skipped for %s: %s", chunks[0].doc_id, str(e)[:120])
            self.failed.append(chunks[0].doc_id)
            return []
        facts = []
        for item in _parse(raw):
            chunk = labels.get(str(item.get("chunk", "")).strip("[]"))
            entity = str(item.get("entity", "")).strip()
            attribute = str(item.get("attribute", "")).strip()
            raw = str(item.get("value", "")).strip()
            if not (chunk and entity and raw) or attribute not in ALLOWED:
                continue
            if entity.lower() not in chunk.text.lower() and not any(entity.lower() in c.text.lower() for c in chunks):
                continue  # the entity must be named in the cited chunk or elsewhere in the same document
            etype = item.get("entity_type") if item.get("entity_type") in ("person", "event", "programme", "location") else None
            year = int(chunk.metadata["date"][:4]) if chunk.metadata.get("date") else None
            value = normalise_value(attribute, raw, year)
            facts.append(Fact(fact_id=fact_id(chunk.chunk_id, entity, attribute, value), entity_mention=entity,
                              attribute=attribute, value=value, raw_value=raw, chunk_id=chunk.chunk_id,
                              extractor="llm", confidence=0.8, entity_type=etype))
        return facts
