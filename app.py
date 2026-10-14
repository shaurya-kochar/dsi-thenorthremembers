"""InfoBridge demo app (issue #9): four screens over the API.

    uvicorn infobridge.api:app      # optional; without it the app runs the pipeline itself
    streamlit run app.py

A demo harness, not a product frontend. Screens:
  1. Home             case, question, Baseline / Full pipeline toggle, answer engine, sources
  2. Query Result     verdict, summary, confidence note, claims with citation badges, conflict flags
  3. Evidence Trail   source -> chunk -> extracted facts -> resolved entity -> claim
  4. Conflict Review  both values side by side with their sources, accept one

The app talks to the API at INFOBRIDGE_API_URL (default http://127.0.0.1:8000). If the API is
not reachable it calls the same ``Service`` in-process, so the demo never depends on a server.
Text facts (and so the conflicts that live in chats and PDFs) need Gemini extraction:
set INFOBRIDGE_API_LLM_EXTRACTION=1 for the server, or for this app when it runs alone.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

from infobridge.config import settings
from infobridge.models import Answer

API_URL = os.getenv("INFOBRIDGE_API_URL", "http://127.0.0.1:8000")
SCREENS = ["Home", "Query Result", "Evidence Trail", "Conflict Review"]
DEMO_CASE = "case_03_conflict"
SEVERITY_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}
CONFIDENCE_BOX = {"high": st.success, "medium": st.warning, "low": st.error}

st.set_page_config(page_title="InfoBridge", page_icon="🔗", layout="wide")


# ------------------------------------------------------------------ clients


class ApiClient:
    def __init__(self, url: str):
        self.http = httpx.Client(base_url=url, timeout=600)

    def _json(self, response: httpx.Response):
        if response.status_code >= 400:
            raise RuntimeError(response.json().get("detail", response.text))
        return response.json()

    def cases(self):
        return self._json(self.http.get("/cases"))

    def sources(self, case):
        return self._json(self.http.get("/sources", params={"case": case}))

    def query(self, case, question, mode, backend):
        return self._json(self.http.post("/query", json={"case": case, "question": question, "mode": mode,
                                                         "backend": backend}))

    def evidence(self, case, chunk_id):
        return self._json(self.http.get("/evidence", params={"case": case, "chunk_id": chunk_id}))

    def conflicts(self, case):
        return self._json(self.http.get("/conflicts", params={"case": case}))

    def accept(self, case, conflict_id, value):
        return self._json(self.http.post(f"/conflicts/{conflict_id}/accept", json={"case": case, "value": value}))


class LocalClient:
    """Same methods as ApiClient, calling the API's Service directly."""

    def __init__(self):
        from infobridge.api import Service

        self.service = Service()

    def __getattr__(self, name):
        fn = getattr(self.service, name)

        def call(*args):
            try:
                return fn(*args)
            except (LookupError, ValueError) as e:
                raise RuntimeError(str(e)) from e
        return call


@st.cache_resource(show_spinner=False)
def connect() -> tuple[object, str, bool]:
    """(client, where it runs, whether Gemini is available)."""
    try:
        health = httpx.get(f"{API_URL}/health", timeout=0.5).json()
        return ApiClient(API_URL), f"API at {API_URL}", bool(health.get("gemini"))
    except Exception:  # no server: run the pipeline in this process
        return LocalClient(), "in-process (API not running)", bool(settings.gemini_api_key)


client, where, gemini = connect()
state = st.session_state
state.setdefault("screen", "Home")
for key in [k for k in state.keys() if k in ("case", "mode", "backend") or str(k).startswith("question_")]:
    state[key] = state[key]  # keep Home's choices while another screen is shown (Streamlit drops unrendered widgets)
state.setdefault("evidence", {})  # (case, chunk_id) -> evidence; chunks do not change


def evidence(case: str, chunk_id: str) -> dict:
    if (case, chunk_id) not in state.evidence:
        state.evidence[(case, chunk_id)] = client.evidence(case, chunk_id)
    return state.evidence[(case, chunk_id)]


# ---------------------------------------------------------------- callbacks


def ask(case: str, question: str, mode: str, backend: str) -> None:
    try:
        state.answer = Answer.model_validate(client.query(case, question, mode, backend))
        state.answer_case, state.error = case, None
        state.trail_chunk = None
        state.screen = "Query Result"
    except Exception as e:  # shown on the page instead of crashing the demo
        state.error = str(e)


def open_trail(chunk_id: str) -> None:
    state.trail_chunk = chunk_id
    state.screen = "Evidence Trail"


def go(screen: str) -> None:
    state.screen = screen


def accept(case: str, conflict_id: str, value: str) -> None:
    try:
        client.accept(case, conflict_id, value)
        state.accepted_msg = f"{conflict_id}: accepted {value!r}"
    except Exception as e:
        state.accepted_msg = f"Could not accept: {e}"


# ------------------------------------------------------------------ sidebar

cases = {c["case"]: c for c in client.cases()}

with st.sidebar:
    st.title("🔗 InfoBridge")
    st.caption("Cited, conflict-aware answers across fragmented sources · DSI 9A · Hyderabad Runners")
    st.radio("Screen", SCREENS, key="screen")
    st.divider()
    st.caption(f"Pipeline runs {where}.")
    if not gemini:
        st.caption("No GEMINI_API_KEY: answers are retrieval-only (extractive).")

answer: Answer | None = state.get("answer")
answer_case: str | None = state.get("answer_case")


# ------------------------------------------------------------------ 1. Home


def home() -> None:
    st.header("Ask a question")
    names = list(cases)
    case = st.selectbox("Case", names, index=names.index(DEMO_CASE) if DEMO_CASE in names else 0,
                        format_func=lambda c: f"{c}  ({cases[c]['split'].replace('_', '-')})", key="case")
    info = cases[case]
    st.caption(info["description"])
    question = st.text_input("Question", value=info["question"], key=f"question_{case}")
    left, right = st.columns(2)
    mode_label = left.radio("Pipeline", ["Full pipeline", "Baseline (v0.1)"], horizontal=True, key="mode",
                            help="Baseline = Sprint 2 naive RAG (dense top-k, no entities, no conflicts). "
                                 "Full = entity resolution, knowledge graph, hybrid retrieval, conflict detection.")
    backends = ["gemini", "extractive"] if gemini else ["extractive"]
    backend = right.radio("Answer engine", backends, horizontal=True, key="backend",
                          help="gemini = LLM synthesis · extractive = retrieval only (no API key)")
    mode = "baseline" if mode_label.startswith("Baseline") else "full"
    st.button("Ask", type="primary", on_click=ask, args=(case, question, mode, backend),
              disabled=not question.strip())
    if state.get("error"):
        st.error(state.error)

    st.subheader("Sources")
    st.dataframe([{"file": s["doc_id"], "format": s["format"], "chunks": s["chunks"], "title": s["title"]}
                  for s in client.sources(case)], hide_index=True, width="stretch")
    if len(info["questions"]) > 1:
        with st.expander(f"Test questions for this case ({len(info['questions'])})"):
            for q in info["questions"]:
                st.markdown(f"- {q}")


# ---------------------------------------------------------- 2. Query Result


def no_answer() -> bool:
    if answer is None:
        st.info("Ask a question on the Home screen first.")
        st.button("Go to Home", on_click=go, args=("Home",))
        return True
    return False


def query_result() -> None:
    if no_answer():
        return
    pipeline = "Full pipeline" if answer.mode == "full" else "Baseline (v0.1)"
    st.header(answer.question)
    st.caption(f"{answer_case} · {pipeline} · {answer.backend}")

    if answer.fallback:
        st.warning("**Not enough evidence.** " + answer.summary)
    else:
        if answer.verdict:
            {"YES": st.success, "NO": st.error}.get(answer.verdict, st.warning)(f"### Verdict: {answer.verdict}")
        st.markdown(answer.summary)
    if answer.confidence:
        CONFIDENCE_BOX[answer.confidence](f"**Confidence: {answer.confidence}.** {answer.confidence_reason}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Claims", len(answer.claims))
    c2.metric("Sources cited", len(answer.citations))
    c3.metric("Conflicts", len(answer.conflicts))
    c4.metric("Latency", f"{answer.latency_s:.1f}s")

    left, right = st.columns([3, 2])
    by_label = {c.label: c for c in answer.citations}
    with left:
        st.subheader("Claims")
        if not answer.claims:
            st.caption("No claims.")
        for i, claim in enumerate(answer.claims):
            with st.container(border=True):
                st.markdown(claim.text + ("  ⚠️ *unsupported*" if claim.unsupported else ""))
                cols = st.columns(max(len(claim.citations), 1) + 2)
                for col, label in zip(cols, claim.citations):
                    cit = by_label.get(label)
                    if cit is None:
                        col.caption(f"[{label}] not retrieved")
                        continue
                    col.button(f"[{label}] {cit.doc_id} · {cit.locator}", key=f"cite_{i}_{label}",
                               on_click=open_trail, args=(cit.chunk_id,), help=cit.quote)
    with right:
        st.subheader("Conflict flags")
        if not answer.conflicts:
            st.info("No conflicts flagged." if answer.mode == "full"
                    else "The baseline does not detect conflicts.")
        for conflict in answer.conflicts:
            with st.container(border=True):
                st.markdown(f"{SEVERITY_ICON.get(conflict.severity, '⚪')} **{conflict.attribute.replace('_', ' ')}**"
                            f" of {conflict.entity_name or conflict.entity_id} · {conflict.severity}")
                for col, value in zip(st.columns(len(conflict.values)), conflict.values):
                    col.markdown(f"**{value.raw_value}**")
                    col.button(value.chunk_id, key=f"conf_{conflict.conflict_id}_{value.chunk_id}",
                               on_click=open_trail, args=(value.chunk_id,))
                if conflict.suggestion:
                    st.caption("Suggestion: " + conflict.suggestion)
        if answer.conflicts:
            st.button("Review conflicts →", on_click=go, args=("Conflict Review",))

    with st.expander(f"Retrieved evidence ({len(answer.retrieved)} chunks)"):
        st.dataframe([{"label": f"S{r.rank}", "chunk": r.chunk.chunk_id, "score": r.score,
                       "found by": ", ".join(r.channels) or "dense"} for r in answer.retrieved],
                     hide_index=True, width="stretch")


# --------------------------------------------------------- 3. Evidence Trail


def chain(chunk_id: str, claims: list[str]) -> None:
    """source -> chunk -> extracted facts -> resolved entities -> claim, for one cited chunk."""
    ev = evidence(answer_case, chunk_id)
    retrieved = next((r for r in answer.retrieved if r.chunk.chunk_id == chunk_id), None)
    where_in = ", ".join(x for x in [f"row {ev['row_number']}" if ev["row_number"] else "",
                                     f"page {ev['page']}" if ev["page"] else "", ev["locator"]] if x)
    st.markdown(f"**① Source** · `{ev['file']}` ({ev['format']})")
    st.markdown(f"**② Chunk** · {where_in}" + (f" · dated {ev['date']}" if ev["date"] else ""))
    st.code(ev["text"], language=None, wrap_lines=True)
    st.markdown("**③ Extracted facts** (field = value)")
    if ev["facts"]:
        st.dataframe([{"field": f["field"], "value": f["value"], "as written": f["raw_value"],
                       "about": f["canonical_name"] or f["entity_mention"], "extractor": f["extractor"],
                       "confidence": f["confidence"]} for f in ev["facts"]],
                     hide_index=True, width="stretch")
    else:
        st.caption("No values extracted from this chunk (it may only name people or events).")
    st.markdown("**④ Resolved entities**")
    for e in ev["entities"]:
        evidence_text = "; ".join(e["match_evidence"][:3]) or "single mention"
        st.markdown(f"- “{e['mention']}” → **{e['canonical_name']}** (`{e['entity_id']}`)  \n"
                    f"  <small>{evidence_text}</small>", unsafe_allow_html=True)
    if not ev["entities"]:
        st.caption("No entity named in this chunk.")
    if retrieved:
        st.markdown(f"**⑤ Retrieval** · rank {retrieved.rank}, score {retrieved.score:.2f}, "
                    f"found by {', '.join(retrieved.channels) or 'dense'}")
    st.markdown("**⑥ Claim**")
    for text in claims:
        st.markdown(f"> {text}")


def evidence_trail() -> None:
    if no_answer():
        return
    st.header("Evidence trail")
    labels = {f"S{r.rank}": r.chunk.chunk_id for r in answer.retrieved}
    cited = {}  # chunk_id -> claims citing it
    for claim in answer.claims:
        for label in claim.citations:
            if label in labels:
                cited.setdefault(labels[label], []).append(claim.text)
    conflict_chunks = {v.chunk_id for c in answer.conflicts for v in c.values}
    options = list(dict.fromkeys(list(cited) + sorted(conflict_chunks)))
    if not options:
        st.info("This answer cites no sources.")
        return
    focus = state.get("trail_chunk")
    index = options.index(focus) if focus in options else 0
    chunk_id = st.selectbox("Cited source", options, index=index,
                            format_func=lambda c: f"{c}  ({len(cited.get(c, []))} claims)")
    with st.container(border=True):
        chain(chunk_id, cited.get(chunk_id) or ["(a side of a flagged conflict, not cited by a claim)"])
    st.subheader("Every claim")
    for claim in answer.claims:
        with st.expander(claim.text[:120]):
            for label in claim.citations:
                if label in labels:
                    st.button(f"Trace [{label}] {labels[label]}", key=f"trace_{claim.text[:40]}_{label}",
                              on_click=open_trail, args=(labels[label],))


# -------------------------------------------------------- 4. Conflict Review


def conflict_review() -> None:
    st.header("Conflict review")
    case = st.session_state.get("case", answer_case or DEMO_CASE)
    conflicts = client.conflicts(case)
    in_answer = {c.conflict_id for c in answer.conflicts} if answer and answer_case == case else set()
    st.caption(f"{case}: {len(conflicts)} conflicts detected"
               + (f", {len(in_answer)} relevant to the last question" if in_answer else ""))
    if in_answer and st.toggle("Only conflicts in the last answer", value=True):
        conflicts = [c for c in conflicts if c["conflict_id"] in in_answer]
    if msg := state.pop("accepted_msg", None):
        st.toast(msg)
    if not conflicts:
        st.info("No conflicts. Text facts (chat, PDF, e-mail) need Gemini extraction: "
                "INFOBRIDGE_API_LLM_EXTRACTION=1.")
    for c in conflicts:
        with st.container(border=True):
            status = f"✅ accepted: **{c['accepted_value']}**" if c["status"] == "accepted" else "open"
            st.markdown(f"{SEVERITY_ICON.get(c['severity'], '⚪')} **{c['conflict_id']} · "
                        f"{c['field'].replace('_', ' ')}** of {c['entity_name']} · severity {c['severity']} · {status}")
            for col, v in zip(st.columns(len(c["values"])), c["values"]):
                chosen = c["status"] == "accepted" and c["accepted_value"] == v["value"]
                col.markdown(f"### {'✅ ' if chosen else ''}{v['raw_value']}")
                if v["raw_value"] != v["value"]:
                    col.caption(f"normalised: {v['value']}")
                col.caption(f"{v['file']} · {v['locator']}")
                col.code(evidence(case, v["chunk_id"])["text"], language=None, wrap_lines=True)
                col.button("Accept this value", key=f"accept_{c['conflict_id']}_{v['value']}", disabled=chosen,
                           on_click=accept, args=(case, c["conflict_id"], v["value"]))
            if c["suggestion"]:
                st.caption("Suggestion: " + c["suggestion"])


{"Home": home, "Query Result": query_result, "Evidence Trail": evidence_trail,
 "Conflict Review": conflict_review}[state.screen]()
