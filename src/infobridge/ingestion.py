"""Component 1 — Document Ingestion.

Parses heterogeneous source files into fact-sized, citable ``Chunk`` objects:

    CSV / Excel   one chunk per row        locator "row=N" (spreadsheet row, header = row 1)
    WhatsApp      one chunk per message    locator "msg=N" (1-based, multi-line messages joined)
    PDF           one chunk per paragraph  locator "page=P&para=N"
    Text / email  one chunk per paragraph  locator "para=N" (email headers kept as metadata)
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pymupdf

from .models import Chunk, Document, SourceFormat

WHATSAPP_LINE = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}), (?P<time>\d{1,2}:\d{2}(?:\s?[APap][Mm])?) - (?P<sender>[^:]+): (?P<text>.*)$"
)
EMAIL_HEADER = re.compile(r"^(From|To|Cc|Date|Subject):\s*(.*)$")


def detect_format(path: Path) -> SourceFormat:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return SourceFormat.CSV
    if suffix in {".xlsx", ".xls"}:
        return SourceFormat.EXCEL
    if suffix == ".pdf":
        return SourceFormat.PDF
    if suffix == ".txt":
        first = path.read_text(errors="ignore").lstrip().splitlines()[:1]
        if first and WHATSAPP_LINE.match(first[0]):
            return SourceFormat.WHATSAPP
        return SourceFormat.TEXT
    raise ValueError(f"Unsupported source format: {path.name}")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------- loaders


def _load_table(doc: Document, df: pd.DataFrame) -> list[Chunk]:
    chunks = []
    for i, row in enumerate(df.fillna("").to_dict(orient="records")):
        locator = f"row={i + 2}"  # +1 for 1-based, +1 for header row
        fields = "; ".join(f"{k}={v}" for k, v in row.items() if str(v).strip())
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{locator}",
                doc_id=doc.doc_id,
                locator=locator,
                text=f"{doc.title}, row {i + 2}: {fields}",
                metadata={"row": {k: str(v) for k, v in row.items()}},
            )
        )
    return chunks


def _load_whatsapp(doc: Document, raw: str) -> list[Chunk]:
    messages: list[dict] = []
    for line in raw.splitlines():
        m = WHATSAPP_LINE.match(line)
        if m:
            messages.append(m.groupdict())
        elif messages and line.strip():  # continuation of a multi-line message
            messages[-1]["text"] += " " + line.strip()
    chunks = []
    for i, msg in enumerate(messages, start=1):
        locator = f"msg={i}"
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{locator}",
                doc_id=doc.doc_id,
                locator=locator,
                text=f"[{msg['date']} {msg['time']}] {msg['sender'].strip()}: {_clean(msg['text'])}",
                metadata={"date": msg["date"], "time": msg["time"], "sender": msg["sender"].strip()},
            )
        )
    return chunks


def _load_pdf(doc: Document, path: Path) -> list[Chunk]:
    chunks = []
    with pymupdf.open(path) as pdf:
        for page_no, page in enumerate(pdf, start=1):
            blocks = [b for b in page.get_text("blocks") if b[6] == 0]  # text blocks only
            blocks.sort(key=lambda b: (round(b[1]), b[0]))  # reading order
            for para_no, block in enumerate(blocks, start=1):
                text = _clean(block[4])
                if not text:
                    continue
                locator = f"page={page_no}&para={para_no}"
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc.doc_id}#{locator}",
                        doc_id=doc.doc_id,
                        locator=locator,
                        text=text,
                        metadata={"page": page_no, "para": para_no},
                    )
                )
    return chunks


def _load_text(doc: Document, raw: str) -> list[Chunk]:
    lines = raw.strip().splitlines()
    headers: dict[str, str] = {}
    while lines and (m := EMAIL_HEADER.match(lines[0])):
        headers[m.group(1).lower()] = m.group(2).strip()
        lines.pop(0)
    doc.metadata.update(headers)
    prefix = f"Email from {headers.get('from', '?')} ({headers.get('date', '?')}), subject '{headers.get('subject', '')}': " if headers else ""

    paragraphs = [_clean(p) for p in "\n".join(lines).split("\n\n") if _clean(p)]
    chunks = []
    for i, para in enumerate(paragraphs, start=1):
        locator = f"para={i}"
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{locator}",
                doc_id=doc.doc_id,
                locator=locator,
                text=prefix + para,
                metadata={"para": i, **headers},
            )
        )
    return chunks


# ------------------------------------------------------------------ public


def load_document(path: str | Path) -> tuple[Document, list[Chunk]]:
    path = Path(path)
    fmt = detect_format(path)
    doc = Document(doc_id=path.name, path=str(path), format=fmt, title=path.name)

    if fmt == SourceFormat.CSV:
        chunks = _load_table(doc, pd.read_csv(path, dtype=str))
    elif fmt == SourceFormat.EXCEL:
        chunks = _load_table(doc, pd.read_excel(path, dtype=str))
    elif fmt == SourceFormat.WHATSAPP:
        chunks = _load_whatsapp(doc, path.read_text())
    elif fmt == SourceFormat.PDF:
        chunks = _load_pdf(doc, path)
    else:
        chunks = _load_text(doc, path.read_text())
    return doc, chunks


def load_directory(directory: str | Path) -> tuple[list[Document], list[Chunk]]:
    docs, chunks = [], []
    for path in sorted(Path(directory).iterdir()):
        if path.name.startswith(".") or path.is_dir():
            continue
        doc, doc_chunks = load_document(path)
        docs.append(doc)
        chunks.extend(doc_chunks)
    return docs, chunks
