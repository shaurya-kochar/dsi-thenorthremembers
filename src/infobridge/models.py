"""Data contracts shared by every pipeline component.

These are the component APIs from the Design Doc expressed as types. Every
component consumes and produces these objects, so components can be built
and tested independently.

Provenance rule: anything derived from a source must carry the ``chunk_id``
it came from. A chunk carries ``doc_id`` + ``locator``, so any output fact can
be walked back to an exact row / message / paragraph.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceFormat(str, Enum):
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"
    WHATSAPP = "whatsapp"
    TEXT = "text"


# ---------------------------------------------------------------- 1. Ingestion


class Document(BaseModel):
    """One source file, as registered with the system."""

    doc_id: str  # stable id, e.g. "members.csv"
    path: str
    format: SourceFormat
    title: str
    ingested_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = {}


class Chunk(BaseModel):
    """Smallest citable unit: one spreadsheet row, chat message or paragraph.

    Chunks are deliberately fact-sized so that a citation to a chunk is a
    citation to a specific fact, not to a whole document.
    """

    chunk_id: str  # f"{doc_id}#{locator}"
    doc_id: str
    locator: str  # "row=5" | "msg=12" | "page=1&para=3" | "para=2"
    text: str  # normalised text used for embedding + prompting
    metadata: dict[str, Any] = {}  # row fields, sender, timestamp, ...


# ------------------------------------------------- 2-5. Extraction → conflicts
# Contracts are fixed now; implementations land in Hack 1.


class Fact(BaseModel):
    """An (entity, attribute, value) claim extracted from one chunk."""

    fact_id: str
    entity_mention: str  # surface form as written in the source ("Ravi S.")
    attribute: str  # normalised attribute name ("medical_clearance_date")
    value: str  # normalised value ("2026-06-22")
    raw_value: str  # as written ("22 June")
    chunk_id: str
    extractor: str  # "csv_schema" | "llm" | "spacy" ...
    confidence: float = 1.0


class Mention(BaseModel):
    """A surface form of an entity inside one chunk ("Ravi S." in whatsapp#msg=3)."""

    text: str
    chunk_id: str


class Entity(BaseModel):
    """A resolved real-world entity with all of its cross-source mentions."""

    entity_id: str
    canonical_name: str
    entity_type: str  # "person" | "event" | "programme" | "location" ...
    mentions: list[Mention] = []
    match_evidence: list[str] = []  # e.g. "phone match", "fuzzy=92"


class ConflictValue(BaseModel):
    value: str
    raw_value: str
    chunk_id: str


class Conflict(BaseModel):
    conflict_id: str
    entity_id: str
    attribute: str
    values: list[ConflictValue]
    severity: str = "medium"  # "low" | "medium" | "high"
    suggestion: str | None = None  # e.g. "prefer most recent source"


# ------------------------------------------------------ 6-7. Synthesis output


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float  # similarity in [0, 1], higher is better
    rank: int


class Citation(BaseModel):
    label: str  # label shown to the user / LLM, e.g. "S3"
    chunk_id: str
    doc_id: str
    locator: str
    quote: str  # the chunk text, so the user can verify without opening the file


class Claim(BaseModel):
    """One sentence of the answer and the sources it rests on."""

    text: str
    citations: list[str]  # citation labels
    unsupported: bool = False  # True if it cites nothing or a non-existent label


class Answer(BaseModel):
    question: str
    verdict: str | None = None  # "YES" | "NO" | "UNCERTAIN" | None (non yes/no question)
    summary: str
    claims: list[Claim] = []
    citations: list[Citation] = []
    conflicts: list[Conflict] = []  # always empty for the v0.1 baseline
    retrieved: list[RetrievedChunk] = []
    fallback: bool = False  # True when the system declined to synthesise
    backend: str = ""
    latency_s: float = 0.0
