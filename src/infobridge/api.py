"""API layer (issue #8): FastAPI endpoints over the pipeline, for the demo UI.

    uvicorn infobridge.api:app --reload

One ``InfoBridge`` per case, built on first use and kept in memory. Ingestion takes seconds;
LLM fact extraction takes minutes and spends quota, so it only runs when
``INFOBRIDGE_API_LLM_EXTRACTION=1``. The bridge of a case is shared by both answer engines
(the backend only picks the synthesizer), so a conflict value accepted in Conflict Review
stays accepted whichever engine answers next.

The logic lives in ``Service`` (plain Python), so the app can call it directly when the API
server is not running; the FastAPI routes are thin wrappers that map errors to HTTP codes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .config import settings
from .pipeline import MODES, InfoBridge, make_synthesizer

DATA = Path(__file__).resolve().parents[2] / "data" / "synthetic"
BACKENDS = ("gemini", "extractive")


class NotFound(LookupError):
    pass


class BadRequest(ValueError):
    pass


class Service:
    def __init__(self, data_dir: str | Path = DATA, llm_extraction: bool | None = None):
        self.data = Path(data_dir)
        self.llm_extraction = (os.getenv("INFOBRIDGE_API_LLM_EXTRACTION") == "1"
                               if llm_extraction is None else llm_extraction)
        self._bridges: dict[str, InfoBridge] = {}
        self._synthesizers: dict[str, object] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- helpers

    def gold(self, case: str) -> dict:
        path = self.data / case / "gold.json"
        if not path.exists():
            raise NotFound(f"unknown case {case!r}")
        return json.loads(path.read_text())

    def bridge(self, case: str) -> InfoBridge:
        self.gold(case)  # 404 for unknown cases
        with self._lock:
            if case not in self._bridges:
                bridge = InfoBridge(backend="extractive", llm_extraction=self.llm_extraction)
                bridge.ingest(self.data / case / "sources")
                self._bridges[case] = bridge
            return self._bridges[case]

    def _synthesizer(self, backend: str):
        if backend not in BACKENDS:
            raise BadRequest(f"unknown backend {backend!r} (expected one of {BACKENDS})")
        if backend == "gemini" and not settings.gemini_api_key:
            raise BadRequest("GEMINI_API_KEY is not set; use backend 'extractive'")
        if backend not in self._synthesizers:
            self._synthesizers[backend] = make_synthesizer(backend)
        return self._synthesizers[backend]

    # -------------------------------------------------------------- endpoints

    def cases(self) -> list[dict]:
        out = []
        for path in sorted(self.data.glob("case_*/gold.json")):
            gold = json.loads(path.read_text())
            out.append({"case": gold["case_id"], "split": gold.get("split", "build"),
                        "description": gold.get("description", ""),
                        "question": gold["queries"][0]["question"] if gold["queries"] else "",
                        "questions": [q["question"] for q in gold["queries"]]})
        return out

    def sources(self, case: str) -> list[dict]:
        bridge = self.bridge(case)
        counts: dict[str, int] = {}
        for c in bridge.chunks.values():
            counts[c.doc_id] = counts.get(c.doc_id, 0) + 1
        return [{"doc_id": d.doc_id, "title": d.title, "format": d.format.value, "chunks": counts.get(d.doc_id, 0)}
                for d in bridge.documents.values()]

    def query(self, case: str, question: str, mode: str = "full", backend: str = "extractive") -> dict:
        if mode not in MODES:
            raise BadRequest(f"unknown mode {mode!r} (expected one of {MODES})")
        if not question.strip():
            raise BadRequest("empty question")
        bridge = self.bridge(case)
        synthesizer = self._synthesizer(backend)
        with self._lock:  # the synthesizer is swapped on the shared bridge for this one call
            bridge.synthesizer = synthesizer
            answer = bridge.ask(question, mode=mode)
        return answer.model_dump(mode="json")

    def evidence(self, case: str, chunk_id: str) -> dict:
        bridge = self.bridge(case)
        chunk = bridge.chunks.get(chunk_id)
        if chunk is None:
            raise NotFound(f"unknown chunk {chunk_id!r} in {case}")
        doc = bridge.documents.get(chunk.doc_id)
        meta = chunk.metadata
        return {"chunk_id": chunk.chunk_id, "file": chunk.doc_id, "format": doc.format.value if doc else None,
                "locator": chunk.locator, "row_number": meta.get("row_number"), "page": meta.get("page"),
                "date": meta.get("date"), "sender": meta.get("sender"), "text": chunk.text,
                "row": meta.get("row"),
                "facts": bridge.store.sql.facts_in_chunk(chunk_id),
                "entities": bridge.store.sql.entities_in_chunk(chunk_id)}

    def conflicts(self, case: str, status: str | None = None) -> list[dict]:
        if status not in (None, "open", "accepted"):
            raise BadRequest(f"unknown status {status!r} (expected open or accepted)")
        bridge = self.bridge(case)
        names = {e.entity_id: e.canonical_name for e in bridge.entities}
        rows = bridge.store.sql.conflicts(status)
        for r in rows:
            r["entity_name"] = names.get(r["entity_id"], r["entity_id"])
        return sorted(rows, key=lambda r: int(r["conflict_id"][1:]) if r["conflict_id"][1:].isdigit() else 0)

    def accept(self, case: str, conflict_id: str, value: str) -> dict:
        bridge = self.bridge(case)
        if not any(r["conflict_id"] == conflict_id for r in bridge.store.sql.conflicts()):
            raise NotFound(f"unknown conflict {conflict_id!r} in {case}")
        try:
            bridge.store.sql.accept_conflict_value(conflict_id, value)
        except ValueError as e:
            raise BadRequest(str(e)) from e
        return next(r for r in self.conflicts(case) if r["conflict_id"] == conflict_id)


# ------------------------------------------------------------------ FastAPI


class QueryRequest(BaseModel):
    case: str
    question: str
    mode: str = "full"
    backend: str = "extractive"


class AcceptRequest(BaseModel):
    case: str
    value: str


service = Service()
app = FastAPI(title="InfoBridge", version="0.1.0",
              description="Cited, conflict-aware answers over messy NGO sources (DSI 9A, Hyderabad Runners)")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BadRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "gemini": bool(settings.gemini_api_key)}


@app.get("/cases")
def get_cases() -> list[dict]:
    return service.cases()


@app.get("/sources")
def get_sources(case: str) -> list[dict]:
    return _call(service.sources, case)


@app.post("/query")
def post_query(req: QueryRequest) -> dict:
    return _call(service.query, req.case, req.question, req.mode, req.backend)


@app.get("/evidence")
def get_evidence_by_query(case: str, chunk_id: str) -> dict:
    return _call(service.evidence, case, chunk_id)


@app.get("/evidence/{chunk_id:path}")
def get_evidence(chunk_id: str, case: str) -> dict:
    """Chunk ids contain '#', '=' and '&': URL-encode them, or use /evidence?case=&chunk_id=."""
    return _call(service.evidence, case, chunk_id)


@app.get("/conflicts")
def get_conflicts(case: str, status: str | None = Query(None)) -> list[dict]:
    return _call(service.conflicts, case, status)


@app.post("/conflicts/{conflict_id}/accept")
def post_accept(conflict_id: str, req: AcceptRequest) -> dict:
    return _call(service.accept, req.case, conflict_id, req.value)
