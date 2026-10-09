"""InfoBridge demo app: a one-page harness for demonstrating the core pipeline.

Not a product frontend (that is out of scope for the PoC); it exists so the
Hack 1 / final demo videos can show question → cited answer → conflicts →
evidence trail in one place.

    streamlit run app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from infobridge.config import settings
from infobridge.models import Answer
from infobridge.pipeline import InfoBridge
from infobridge.provenance import answer_trail

DATA = Path(__file__).resolve().parent / "data" / "synthetic"

st.set_page_config(page_title="InfoBridge", page_icon="🔗", layout="wide")


@st.cache_resource(show_spinner="Ingesting sources…")
def load_bridge(case: str, backend: str) -> InfoBridge:
    bridge = InfoBridge(backend=backend)
    bridge.ingest(DATA / case / "sources")
    return bridge


def case_question(case: str) -> str:
    gold = json.loads((DATA / case / "gold.json").read_text())
    return gold["queries"][0]["question"]


# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.title("🔗 InfoBridge")
    st.caption("Evidence-preserving synthesis across fragmented sources · DSI 9A · Hyderabad Runners")
    cases = sorted(p.name for p in DATA.glob("case_*"))
    case = st.selectbox("Scenario", cases, index=len(cases) - 1)
    backends = ["gemini", "extractive"] if settings.gemini_api_key else ["extractive"]
    backend = st.radio("Answer engine", backends,
                       help="gemini = LLM synthesis · extractive = retrieval only (no API key)")
    if not settings.gemini_api_key:
        st.info("No GEMINI_API_KEY found, so only retrieval-only mode is available.")
    st.radio("Pipeline", ["Baseline (v0.1)"], help="The full pipeline (entity resolution, conflict "
             "detection, knowledge graph) is added in Hack 1.")

    bridge = load_bridge(case, backend)
    st.divider()
    st.subheader("Sources")
    for doc in bridge.documents.values():
        n = sum(c.doc_id == doc.doc_id for c in bridge.chunks.values())
        st.markdown(f"**{doc.doc_id}**  \n{doc.format.value} · {n} chunks")


# --------------------------------------------------------------------- main

question = st.text_input("Ask a question", value=case_question(case))
if not st.button("Ask", type="primary") and "answer" not in st.session_state:
    st.stop()

if st.session_state.get("asked") != (case, backend, question):
    with st.spinner("Retrieving evidence and synthesising…"):
        st.session_state["answer"] = bridge.ask(question)
        st.session_state["asked"] = (case, backend, question)
answer: Answer = st.session_state["answer"]

# Verdict + summary
if answer.fallback:
    st.warning("**Not enough evidence.** " + answer.summary)
elif answer.verdict:
    show = {"YES": st.success, "NO": st.error}.get(answer.verdict, st.warning)
    show(f"### Verdict: {answer.verdict}")
if not answer.fallback:
    st.markdown(answer.summary)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Claims", len(answer.claims))
c2.metric("Sources cited", len(answer.citations))
c3.metric("Conflicts", len(answer.conflicts))
c4.metric("Latency", f"{answer.latency_s:.2f}s")

left, right = st.columns([3, 2])

with left:
    st.subheader("Claims")
    by_label = {c.label: c for c in answer.citations}
    for claim in answer.claims:
        badges = " ".join(f"`{l}`" for l in claim.citations)
        flag = "  ⚠️ *unsupported*" if claim.unsupported else ""
        st.markdown(f"- {claim.text} {badges}{flag}")
    if not answer.claims:
        st.caption("No claims.")

    st.subheader("Sources used")
    for cit in answer.citations:
        with st.expander(f"[{cit.label}] {cit.doc_id} · {cit.locator}"):
            st.code(cit.quote, language=None, wrap_lines=True)

with right:
    st.subheader("Conflicts")
    if answer.conflicts:
        for conflict in answer.conflicts:
            with st.container(border=True):
                st.markdown(f"⚠️ **{conflict.attribute.replace('_', ' ')}** · {conflict.severity}")
                cols = st.columns(len(conflict.values))
                for col, value in zip(cols, conflict.values):
                    col.markdown(f"**{value.raw_value}**  \n`{value.chunk_id}`")
                if conflict.suggestion:
                    st.caption("Suggestion: " + conflict.suggestion)
    else:
        st.info("No conflicts flagged. Automatic conflict detection is added in Hack 1.")

    st.subheader("Evidence trail")
    for item in answer_trail(answer, bridge.documents):
        with st.expander(item["claim"][:80]):
            st.json(item["evidence"], expanded=True)
