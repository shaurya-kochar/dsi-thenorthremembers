"""Render binary synthetic sources (PDF, Excel) from their plain-text originals.

The text originals in ``pdf_src/`` and ``xlsx_src/`` are the editable source of
truth; the rendered files land in ``sources/`` and are what the pipeline ingests.

    python scripts/build_synthetic.py
"""

from pathlib import Path

import pandas as pd
import pymupdf

ROOT = Path(__file__).resolve().parents[1] / "data" / "synthetic"

PAGE_W, PAGE_H = 595, 842  # A4 points
MARGIN = 56
PARA_GAP = 14


def text_to_pdf(src: Path, dst: Path) -> None:
    """One text block per paragraph, so PyMuPDF reads them back as separate blocks."""
    paragraphs = [p.strip() for p in src.read_text().split("\n\n") if p.strip()]
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = MARGIN
    for i, para in enumerate(paragraphs):
        size, font = (13, "hebo") if i == 0 else (10.5, "helv")  # bold title, regular body
        height = 20
        while True:  # grow the box until the paragraph fits (dry-run on a scratch page)
            rect = pymupdf.Rect(MARGIN, y, PAGE_W - MARGIN, y + height)
            scratch = pymupdf.open().new_page(width=PAGE_W, height=PAGE_H)
            if scratch.insert_textbox(rect, para, fontsize=size, fontname=font) >= 0:
                break
            height += 12
        if y + height > PAGE_H - MARGIN:
            page = doc.new_page(width=PAGE_W, height=PAGE_H)
            y = MARGIN
            rect = pymupdf.Rect(MARGIN, y, PAGE_W - MARGIN, y + height)
        page.insert_textbox(rect, para, fontsize=size, fontname=font)
        y += height + PARA_GAP
    doc.save(dst)


def csv_to_xlsx(src: Path, dst: Path) -> None:
    pd.read_csv(src, dtype=str).to_excel(dst, index=False, sheet_name="Roster")


def main() -> None:
    for case in sorted(ROOT.glob("case_*")):
        out = case / "sources"
        for src in sorted((case / "pdf_src").glob("*.txt")):
            text_to_pdf(src, out / f"{src.stem}.pdf")
            print("pdf ", out / f"{src.stem}.pdf")
        for src in sorted((case / "xlsx_src").glob("*.csv")):
            csv_to_xlsx(src, out / f"{src.stem}.xlsx")
            print("xlsx", out / f"{src.stem}.xlsx")


if __name__ == "__main__":
    main()
