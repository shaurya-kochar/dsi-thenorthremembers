from pathlib import Path

from infobridge.ingestion import load_directory, load_document
from infobridge.models import SourceFormat

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def test_csv_rows_use_spreadsheet_numbering():
    doc, chunks = load_document(DATA / "case_03_conflict/sources/members.csv")
    assert doc.format == SourceFormat.CSV
    ravi = next(c for c in chunks if "Ravi Sharma" in c.text)
    assert ravi.locator == "row=5"  # header is row 1
    assert ravi.metadata["row"]["medical_clearance_date"] == "2026-03-15"


def test_whatsapp_joins_multiline_messages():
    doc, chunks = load_document(DATA / "case_03_conflict/sources/whatsapp_coach_group.txt")
    assert doc.format == SourceFormat.WHATSAPP
    assert len(chunks) == 10
    msg6 = next(c for c in chunks if c.locator == "msg=6")
    assert "tempo work in November" in msg6.text
    assert msg6.metadata["sender"] == "Coach Anil"


def test_pdf_paragraphs():
    _, chunks = load_document(DATA / "case_03_conflict/sources/programme_rules.pdf")
    para2 = next(c for c in chunks if c.locator == "page=1&para=2")
    assert "8 November 2026" in para2.text


def test_email_headers_become_metadata():
    doc, chunks = load_document(DATA / "case_01_simple/sources/email_long_run_route.txt")
    assert doc.metadata["from"].startswith("Priya Reddy")
    assert all(not c.text.split(": ", 1)[1].startswith("From:") for c in chunks)


def test_excel():
    doc, chunks = load_document(DATA / "case_02_medium/sources/volunteer_roster.xlsx")
    assert doc.format == SourceFormat.EXCEL
    assert next(c for c in chunks if c.locator == "row=3").metadata["row"]["full_name"] == "Srinivas Rao Kumar"


def test_chunk_ids_unique():
    for case in DATA.glob("case_*"):
        _, chunks = load_directory(case / "sources")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))
