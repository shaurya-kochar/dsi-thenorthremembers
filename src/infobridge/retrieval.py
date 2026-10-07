"""Component 5 — Vector store.

ChromaDB (in-memory) with all-MiniLM-L6-v2 embeddings. Chroma's default
embedding function is exactly that model, run via ONNX, so we avoid a PyTorch
dependency while keeping the model chosen in the Design Doc.

Hack 1: add graph-traversal retrieval alongside this (hybrid search), e.g.
expand the result set with every chunk that mentions a resolved entity found
in the top hits.
"""

from __future__ import annotations

import uuid

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .models import Chunk, RetrievedChunk


class VectorStore:
    def __init__(self) -> None:
        client = chromadb.EphemeralClient()
        self._collection = client.create_collection(
            name=f"infobridge-{uuid.uuid4().hex[:8]}",
            embedding_function=DefaultEmbeddingFunction(),
            configuration={"hnsw": {"space": "cosine"}},
        )
        self._chunks: dict[str, Chunk] = {}

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self._collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{"doc_id": c.doc_id, "locator": c.locator} for c in chunks],
        )
        self._chunks.update({c.chunk_id: c for c in chunks})

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        k = min(k, len(self._chunks))
        if k == 0:
            return []
        res = self._collection.query(query_texts=[query], n_results=k)
        return [
            RetrievedChunk(chunk=self._chunks[cid], score=round(1 - dist, 4), rank=rank)
            for rank, (cid, dist) in enumerate(zip(res["ids"][0], res["distances"][0]), start=1)
        ]

    def __len__(self) -> int:
        return len(self._chunks)
