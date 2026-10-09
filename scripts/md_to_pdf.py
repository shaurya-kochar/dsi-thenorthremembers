"""Render a Markdown doc in docs/ to a print-styled A4 PDF via headless Chrome.

    python scripts/md_to_pdf.py docs/technical_design_doc.md     # -> docs/technical_design_doc.pdf

Needs Google Chrome (or Chromium) and the markdown package (pip install -e ".[dev]").
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
]

css = """
@page { size: A4; margin: 18mm 17mm 18mm 17mm;
        @bottom-center { content: counter(page); } }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: Charter, "Iowan Old Style", Georgia, serif; font-size: 10.3pt;
       line-height: 1.42; color: #1a1a1a; max-width: 100%; }
h1 { font-size: 19pt; text-align: center; margin: 0 0 4pt; line-height: 1.2; }
h1 + p { text-align: center; color: #444; font-size: 9.6pt; margin-top: 2pt; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; padding-bottom: 3pt; border-bottom: 1.2px solid #1f3a5f;
     color: #1f3a5f; break-after: avoid; }
h3 { font-size: 11.3pt; margin: 13pt 0 4pt; color: #1f3a5f; break-after: avoid; }
p, li { margin: 3pt 0; }
ul, ol { padding-left: 18pt; margin: 3pt 0; }
hr { border: none; border-top: 0.8px solid #bbb; margin: 12pt 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 9pt; font-size: 8.7pt;
        line-height: 1.32; break-inside: auto; }
tr { break-inside: avoid; }
th { background: #1f3a5f; color: #fff; text-align: left; font-weight: 600; padding: 4pt 5pt; }
td { padding: 3.5pt 5pt; border-bottom: 0.6px solid #d5dbe3; vertical-align: top; }
tbody tr:nth-child(even) td { background: #f4f6f9; }
code { font-family: Menlo, "SF Mono", monospace; font-size: 8.2pt; background: #eef1f5;
       padding: 0.5pt 2.5pt; border-radius: 2pt; }
pre { background: #f4f6f9; border: 0.6px solid #d5dbe3; border-left: 3px solid #1f3a5f;
      padding: 6pt 8pt; font-size: 8pt; line-height: 1.35; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8pt; }
blockquote { margin: 7pt 0; padding: 5pt 9pt; background: #fff8e6; border-left: 3px solid #e0a100;
             font-size: 9.5pt; }
blockquote p { margin: 0; }
.badge { display: inline-block; font-size: 7.6pt; font-weight: 700; padding: 0.5pt 5pt;
         border-radius: 7pt; white-space: nowrap; }
.badge.ok { background: #dcf3e3; color: #17663a; }
.badge.stub { background: #fdecd2; color: #8a4b00; }
.badge.part { background: #fff3bf; color: #7a5d00; }
strong { color: #111; }
li.task { list-style: none; margin-left: -13pt; }
"""


def to_html(src: Path) -> str:
    md = src.read_text()
    # Task lists -> checkbox glyphs; in-doc anchor links -> plain text.
    md = re.sub(r"^(\s*)- \[ \] ", r"\1- ☐ ", md, flags=re.M)
    md = re.sub(r"^(\s*)- \[x\] ", r"\1- ☑ ", md, flags=re.M)
    md = re.sub(r"\[([^\]]+)\]\(#[^)]+\)", r"\1", md)
    # Python-Markdown nests list content only at 4-space indents; our docs use 3.
    md = re.sub(r"^   (?=\S)", "    ", md, flags=re.M)
    # GitHub starts a list right after a paragraph line; Python-Markdown needs a blank line first.
    md = re.sub(r"^(?![ |#>\-]|\d+\. )(\S.*)\n(?=(?:- |\d+\. ))", r"\1\n\n", md, flags=re.M)

    # Status emoji -> text badges (formal document).
    badges = {"✅": ("ok", "Done"), "⏳": ("stub", "Stub"), "🟡": ("part", "Partial")}
    for emoji, (cls, _) in badges.items():
        md = re.sub(emoji + r" ?(\w[\w ]*)", lambda m, c=cls: f'<span class="badge {c}">{m.group(1)}</span>', md)

    title = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), src.stem).replace("&", "&amp;")
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    body = body.replace("<li>☐", '<li class="task">☐').replace("<li>☑", '<li class="task">☑')
    return (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{title}</title>"
            f"<style>{css}</style></head><body>{body}</body></html>")


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists() or shutil.which(c):
            return c
    sys.exit("Chrome/Chromium not found; open the .md in a browser and print to PDF instead.")


def md_to_pdf(src: Path, dst: Path | None = None) -> Path:
    dst = dst or src.with_suffix(".pdf")
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "doc.html"
        html.write_text(to_html(src))
        subprocess.run([find_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={dst.resolve()}", html.resolve().as_uri()],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dst


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print("wrote", md_to_pdf(Path(arg)))
