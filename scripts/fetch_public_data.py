"""Fetch the public data slice into data/public/ (issue #1).

    python scripts/fetch_public_data.py                 # OpenAlex + WHO
    DATA_GOV_IN_API_KEY=... python scripts/fetch_public_data.py --ogd   # also OGD India

What is kept, and why:
  * OpenAlex: ~200 paper records about recreational running, marathon health,
    community physical activity, heat illness and event volunteering. Author
    names and affiliations are dropped (personal identifiers); only the work's
    title, year, venue, type, topic, citations, open-access flag and DOI stay.
  * WHO: five open-access reports. Only their text-heavy pages are kept (a
    "slice"), so the repo stays small; the full report is linked in the manifest.
  * OGD India: two small health/education tables from data.gov.in. The API needs
    a personal key (free at https://data.gov.in); the public sample key is rate
    limited, so this step is skipped without DATA_GOV_IN_API_KEY.

Every file is listed in data/public/manifest.json with its source URL and licence.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "public"
UA = {"User-Agent": "InfoBridge-DSI-student-project/0.1 (research use)"}

OPENALEX_QUERIES = [
    "recreational running injuries",
    "marathon runners health",
    "community running group physical activity",
    "heat illness endurance event",
    "volunteer management sport events",
]

# (search query, slug, text the item title must contain) — the first matching IRIS hit with a PDF is used
WHO_REPORTS = [
    ("WHO guidelines on physical activity and sedentary behaviour", "who_physical_activity_guidelines_2020", "physical activity and sedentary"),
    ("Global action plan on physical activity 2018-2030 more active people for a healthier world", "who_gappa_2018_2030", "global action plan on physical activity"),
    ("Global status report on physical activity 2022", "who_physical_activity_status_report_2022", "global status report on physical activity"),
    ("Heat and health in the WHO European Region updated evidence for effective prevention", "who_heat_and_health_europe_2021", "heat and health"),
    ("Public health for mass gatherings key considerations", "who_mass_gatherings_2015", "mass gatherings"),
]
WHO_PAGES = 6  # text-heavy pages kept per report

# (data.gov.in resource id, file name)
OGD_DATASETS = [
    ("1fc6d761-49a7-4e2e-8621-d211debf3fc4", "ogd_covid_dedicated_hospital_beds_by_state_2020.csv"),
    ("3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69", "ogd_realtime_air_quality_telangana.csv"),
]


def get(url: str, timeout: int = 90) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


# ------------------------------------------------------------------ OpenAlex


def fetch_openalex(limit: int = 200) -> dict:
    rows, seen = [], set()
    for q in OPENALEX_QUERIES:
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode({
            "search": q, "per-page": 45, "sort": "relevance_score:desc",
            "filter": "from_publication_date:2015-01-01,type:article|review",
            "select": "id,doi,title,publication_year,type,cited_by_count,open_access,primary_location,primary_topic",
        })
        for w in json.loads(get(url))["results"]:
            if w["id"] in seen or not w.get("title"):
                continue
            seen.add(w["id"])
            source = ((w.get("primary_location") or {}).get("source") or {})
            rows.append({
                "openalex_id": w["id"].rsplit("/", 1)[-1],
                "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
                "title": " ".join(w["title"].split()),
                "publication_year": w.get("publication_year"),
                "type": w.get("type"),
                "venue": source.get("display_name") or "",
                "primary_topic": (w.get("primary_topic") or {}).get("display_name", ""),
                "cited_by_count": w.get("cited_by_count"),
                "is_open_access": (w.get("open_access") or {}).get("is_oa"),
                "search_query": q,
            })
    rows = rows[:limit]
    out = PUBLIC / "openalex" / "openalex_running_papers.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"openalex: {len(rows)} records -> {out.relative_to(ROOT)}")
    return {"file": str(out.relative_to(ROOT)), "source": "https://api.openalex.org/works",
            "queries": OPENALEX_QUERIES, "records": len(rows), "licence": "CC0 (OpenAlex metadata)",
            "privacy": "author names and affiliations dropped"}


# ----------------------------------------------------------------------- WHO


def _iris_pdf(query: str, must_contain: str) -> tuple[str, str, str]:
    """First IRIS item for the query whose title matches and that has a PDF: (title, handle URL, PDF URL)."""
    search = "https://iris.who.int/server/api/discover/search/objects?" + urllib.parse.urlencode(
        {"query": query, "dsoType": "ITEM", "size": 5})
    hits = json.loads(get(search))["_embedded"]["searchResult"]["_embedded"]["objects"]
    for hit in hits:
        item = hit["_embedded"]["indexableObject"]
        if must_contain not in item["name"].lower():
            continue
        bundles = json.loads(get(item["_links"]["bundles"]["href"]))["_embedded"]["bundles"]
        for bundle in bundles:
            if bundle["name"] != "ORIGINAL":
                continue
            streams = json.loads(get(bundle["_links"]["bitstreams"]["href"]))["_embedded"]["bitstreams"]
            pdfs = [s for s in streams if s["name"].lower().endswith(".pdf")]
            pdfs.sort(key=lambda s: "eng" not in s["name"].lower())  # English edition first
            if pdfs:
                handle = f"https://iris.who.int/handle/{item['handle']}"
                return item["name"], handle, pdfs[0]["_links"]["content"]["href"]
    raise RuntimeError(f"no PDF found for {query!r}")


def _slice_pdf(pdf_bytes: bytes, dst: Path, pages: int) -> list[int]:
    """Keep the `pages` text-richest pages among the first 40, in reading order."""
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    scored = [(len(src[i].get_text("text")), i) for i in range(min(40, len(src)))]
    keep = sorted(i for _, i in sorted(scored, reverse=True)[:pages])
    out = pymupdf.open()
    for i in keep:
        out.insert_pdf(src, from_page=i, to_page=i)
    out.save(dst, garbage=4, deflate=True)
    return [i + 1 for i in keep]


def fetch_who() -> list[dict]:
    entries = []
    (PUBLIC / "who").mkdir(parents=True, exist_ok=True)
    for query, slug, must_contain in WHO_REPORTS:
        title, handle, pdf_url = _iris_pdf(query, must_contain)
        dst = PUBLIC / "who" / f"{slug}.pdf"
        kept = _slice_pdf(get(pdf_url, timeout=180), dst, WHO_PAGES)
        print(f"who: {slug} ({len(kept)} pages) <- {handle}")
        entries.append({"file": str(dst.relative_to(ROOT)), "title": title, "source": handle,
                        "pages_kept": kept, "licence": "CC BY-NC-SA 3.0 IGO (WHO open access)"})
    return entries


# ----------------------------------------------------------------------- OGD


def fetch_ogd(api_key: str) -> list[dict]:
    entries = []
    (PUBLIC / "ogd").mkdir(parents=True, exist_ok=True)
    for resource, name in OGD_DATASETS:
        params = {"api-key": api_key, "format": "csv", "limit": 500}
        if "air_quality" in name:
            params["filters[state]"] = "Telangana"
        url = f"https://api.data.gov.in/resource/{resource}?" + urllib.parse.urlencode(params)
        text = get(url).decode("utf-8")
        if text.lstrip().startswith("{"):
            raise RuntimeError(f"data.gov.in refused {resource}: {text[:200]}")
        dst = PUBLIC / "ogd" / name
        dst.write_text(text)
        rows = sum(1 for _ in csv.reader(io.StringIO(text))) - 1
        print(f"ogd: {name} ({rows} rows)")
        entries.append({"file": str(dst.relative_to(ROOT)), "source": f"https://data.gov.in/resource/{resource}",
                        "rows": rows, "licence": "Government Open Data License - India (GODL)"})
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ogd", action="store_true", help="also fetch OGD India (needs DATA_GOV_IN_API_KEY)")
    parser.add_argument("--skip-who", action="store_true")
    parser.add_argument("--skip-openalex", action="store_true")
    args = parser.parse_args()

    manifest_path = PUBLIC / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if not args.skip_openalex:
        manifest["openalex"] = fetch_openalex()
    if not args.skip_who:
        manifest["who"] = fetch_who()
    if args.ogd:
        key = os.getenv("DATA_GOV_IN_API_KEY")
        if not key:
            raise SystemExit("set DATA_GOV_IN_API_KEY (free key from https://data.gov.in) to fetch OGD data")
        manifest["ogd"] = fetch_ogd(key)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("manifest ->", manifest_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
