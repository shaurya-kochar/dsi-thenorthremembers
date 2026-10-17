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
Look and feel: .streamlit/config.toml (theme) and STYLE below (cards, chips, timeline).
"""

from __future__ import annotations

import html
import os
import re

import httpx
import streamlit as st

from infobridge.config import settings
from infobridge.models import Answer

API_URL = os.getenv("INFOBRIDGE_API_URL", "http://127.0.0.1:8000")
SCREENS = ["Home", "Query Result", "Evidence Trail", "Conflict Review"]
SCREEN_ICON = {"Home": "🏠", "Query Result": "💡", "Evidence Trail": "🧭", "Conflict Review": "⚖️"}
DEMO_CASE = "case_03_conflict"
SEVERITY_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}
CONFIDENCE_BOX = {"high": st.success, "medium": st.warning, "low": st.error}
FORMAT_ICON = {"csv": "📊", "xlsx": "📗", "xls": "📗", "pdf": "📄", "txt": "💬", "whatsapp": "💬", "chat": "💬",
               "eml": "✉️", "email": "✉️", "md": "📝", "docx": "📝"}

st.set_page_config(page_title="InfoBridge", page_icon="🔗", layout="wide")

STYLE = """
<style>
:root {
  --ib-accent: #4F46E5; --ib-accent-soft: #EEF0FF; --ib-ink: #1E2333; --ib-muted: #667085;
  --ib-card: #FFFFFF; --ib-line: #E2E5EF;
  --ib-yes: #067647; --ib-yes-soft: #ECFDF3; --ib-no: #B42318; --ib-no-soft: #FEF3F2;
  --ib-warn: #B54708; --ib-warn-soft: #FFFAEB;
}
.block-container { max-width: 1240px; padding-top: 2.2rem; padding-bottom: 4rem; }
h1, h2, h3 { letter-spacing: -0.02em; }
[data-testid="stHeaderActionElements"] { display: none; }

/* cards: every keyed container named card_* */
[class*="st-key-card_"] { background: var(--ib-card); border-color: var(--ib-line) !important;
  box-shadow: 0 1px 2px rgba(16, 24, 40, .04), 0 1px 3px rgba(16, 24, 40, .06); }

/* hero */
.ib-hero { padding: 1.6rem 1.8rem; border-radius: 1rem; margin-bottom: 1.2rem; color: #fff;
  background: linear-gradient(120deg, #312E81 0%, #4F46E5 55%, #7C3AED 100%); }
.ib-hero .eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: .72rem; opacity: .8; font-weight: 600; }
.ib-hero h1 { color: #fff; font-size: 2rem; margin: .25rem 0 .35rem 0; padding: 0; }
.ib-hero p { margin: 0; opacity: .9; max-width: 46rem; }

/* chips and badges */
.ib-chip { display: inline-flex; align-items: center; gap: .3rem; padding: .12rem .55rem; margin: 0 .3rem .3rem 0;
  border-radius: 999px; font-size: .78rem; font-weight: 500; background: var(--ib-accent-soft); color: var(--ib-accent);
  border: 1px solid #DCDFFF; white-space: nowrap; }
.ib-chip.grey { background: #F2F4F7; color: #475467; border-color: #E4E7EC; }
.ib-chip.ok { background: var(--ib-yes-soft); color: var(--ib-yes); border-color: #ABEFC6; }
.ib-chip.bad { background: var(--ib-no-soft); color: var(--ib-no); border-color: #FECDCA; }
.ib-chip.warn { background: var(--ib-warn-soft); color: var(--ib-warn); border-color: #FEDF89; }
.ib-verdict { display: inline-block; font-weight: 700; font-size: 1.05rem; letter-spacing: .04em;
  padding: .35rem .9rem; border-radius: .6rem; margin-bottom: .6rem; }
.ib-verdict.YES { background: var(--ib-yes-soft); color: var(--ib-yes); border: 1px solid #ABEFC6; }
.ib-verdict.NO { background: var(--ib-no-soft); color: var(--ib-no); border: 1px solid #FECDCA; }
.ib-verdict.UNCERTAIN { background: var(--ib-warn-soft); color: var(--ib-warn); border: 1px solid #FEDF89; }
.ib-label { text-transform: uppercase; letter-spacing: .08em; font-size: .7rem; font-weight: 600; color: var(--ib-muted); }
.ib-num { display: inline-flex; justify-content: center; align-items: center; min-width: 1.6rem; height: 1.6rem;
  border-radius: .45rem; background: var(--ib-accent-soft); color: var(--ib-accent); font-weight: 600; font-size: .8rem;
  margin-right: .55rem; }
.ib-claim { display: flex; align-items: flex-start; line-height: 1.55; }
.ib-value { font-size: 1.35rem; font-weight: 700; color: var(--ib-ink); line-height: 1.25; }
.ib-vs { text-align: center; color: var(--ib-muted); font-weight: 700; font-size: .8rem; padding-top: 1.6rem; }

/* source grid on Home */
.ib-sources { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: .75rem; }
.ib-source { background: var(--ib-card); border: 1px solid var(--ib-line); border-radius: .8rem; padding: .85rem 1rem; }
.ib-source .icon { font-size: 1.3rem; }
.ib-source .file { font-weight: 600; margin-top: .25rem; word-break: break-all; }
.ib-source .title { color: var(--ib-muted); font-size: .85rem; margin: .15rem 0 .45rem 0; }

/* sidebar */
.ib-brand { display: flex; align-items: center; gap: .6rem; margin-bottom: .2rem; }
.ib-brand .mark { width: 2.2rem; height: 2.2rem; border-radius: .6rem; display: flex; align-items: center;
  justify-content: center; background: linear-gradient(135deg, #4F46E5, #7C3AED); color: #fff; font-size: 1.1rem; }
.ib-brand .name { font-weight: 700; font-size: 1.25rem; letter-spacing: -0.02em; }
.ib-side-note { color: var(--ib-muted); font-size: .82rem; line-height: 1.45; }

/* citation badges and source buttons rendered as chips */
[class*="st-key-cite_"] button, [class*="st-key-conf_"] button, [class*="st-key-trace_"] button {
  border-radius: 999px; min-height: 0; padding: .15rem .7rem; background: var(--ib-accent-soft);
  border: 1px solid #DCDFFF; color: var(--ib-accent); }
[class*="st-key-cite_"] button p, [class*="st-key-conf_"] button p, [class*="st-key-trace_"] button p {
  font-size: .78rem; font-weight: 500; }
[class*="st-key-cite_"] button:hover, [class*="st-key-conf_"] button:hover, [class*="st-key-trace_"] button:hover {
  background: var(--ib-accent); color: #fff; border-color: var(--ib-accent); }

/* evidence trail timeline: keyed containers named step_* */
[class*="st-key-step_"] { border-left: 2px solid #DCDFFF; padding-left: 1.1rem; margin-left: .4rem; position: relative; }
[class*="st-key-step_"]::before { content: ""; position: absolute; left: -7px; top: .35rem; width: 12px; height: 12px;
  border-radius: 50%; background: var(--ib-accent); box-shadow: 0 0 0 3px var(--ib-accent-soft); }

/* the chosen side of an accepted conflict */
[class*="st-key-side_"][class*="_chosen"] { background: var(--ib-yes-soft); border-color: #ABEFC6 !important; }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text))


def chip(text, kind: str = "") -> str:
    return f'<span class="ib-chip {kind}">{esc(text)}</span>'


def slug(text: str) -> str:
    """A widget/container key fragment that is also a valid CSS class name."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", text)


def card(name: str):
    return st.container(border=True, key=f"card_{slug(name)}")


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


def pick_question(case: str) -> None:
    if picked := state.get(f"pick_{case}"):
        state[f"question_{case}"] = picked


# ------------------------------------------------------------------ sidebar

cases = {c["case"]: c for c in client.cases()}
answer: Answer | None = state.get("answer")
answer_case: str | None = state.get("answer_case")

with st.sidebar:
    st.markdown('<div class="ib-brand"><div class="mark">🔗</div><div class="name">InfoBridge</div></div>'
                '<div class="ib-side-note">Cited, conflict-aware answers across fragmented sources · '
                'DSI 9A · Hyderabad Runners</div>', unsafe_allow_html=True)
    st.write("")
    st.radio("Screen", SCREENS, key="screen", format_func=lambda s: f"{SCREEN_ICON[s]}  {s}")
    st.divider()
    st.markdown('<div class="ib-label">Status</div>', unsafe_allow_html=True)
    st.markdown(chip("● API" if where.startswith("API") else "● In-process", "ok" if where.startswith("API") else "grey")
                + chip("Gemini on" if gemini else "Gemini off", "ok" if gemini else "warn"), unsafe_allow_html=True)
    st.caption(f"Pipeline runs {where}.")
    if not gemini:
        st.caption("No GEMINI_API_KEY: answers are retrieval-only (extractive).")
    if answer is not None:
        st.divider()
        st.markdown('<div class="ib-label">Last question</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ib-side-note" style="color:inherit">{esc(answer.question)}</div>'
                    f'<div style="margin-top:.4rem">{chip(answer_case, "grey")}'
                    + (chip(answer.verdict, {"YES": "ok", "NO": "bad"}.get(answer.verdict, "warn"))
                       if answer.verdict else "") + "</div>", unsafe_allow_html=True)


# ------------------------------------------------------------------ 1. Home


def home() -> None:
    st.markdown('<div class="ib-hero"><div class="eyebrow">Evidence-preserving synthesis</div>'
                '<h1>Ask across every source</h1>'
                '<p>Spreadsheets, chats, PDFs and e-mails are resolved into one picture of who is who. '
                'Every claim is cited, and disagreements between sources are flagged instead of hidden.</p></div>',
                unsafe_allow_html=True)
    names = list(cases)
    with card("ask"):
        case = st.selectbox("Case", names, index=names.index(DEMO_CASE) if DEMO_CASE in names else 0,
                            format_func=lambda c: f"{c}  ({cases[c]['split'].replace('_', '-')})", key="case")
        info = cases[case]
        st.caption(info["description"])
        state.setdefault(f"question_{case}", info["question"])
        question = st.text_input("Question", key=f"question_{case}")
        if len(info["questions"]) > 1:
            st.pills(f"Test questions for this case ({len(info['questions'])})", info["questions"],
                     key=f"pick_{case}", on_change=pick_question, args=(case,))
        left, right, go_col = st.columns([5, 4, 2], vertical_alignment="bottom")
        mode_label = left.radio("Pipeline", ["Full pipeline", "Baseline (v0.1)"], horizontal=True, key="mode",
                                help="Baseline = Sprint 2 naive RAG (dense top-k, no entities, no conflicts). "
                                     "Full = entity resolution, knowledge graph, hybrid retrieval, conflict detection.")
        backends = ["gemini", "extractive"] if gemini else ["extractive"]
        backend = right.radio("Answer engine", backends, horizontal=True, key="backend",
                              help="gemini = LLM synthesis · extractive = retrieval only (no API key)")
        mode = "baseline" if mode_label.startswith("Baseline") else "full"
        go_col.button("Ask", type="primary", on_click=ask, args=(case, question, mode, backend),
                      disabled=not question.strip(), icon=":material/arrow_forward:", width="stretch")
    if state.get("error"):
        st.error(state.error)

    sources = client.sources(case)
    st.subheader(f"Sources · {len(sources)}")
    tiles = "".join(
        f'<div class="ib-source"><div class="icon">{FORMAT_ICON.get(s["format"].lower(), "📁")}</div>'
        f'<div class="file">{esc(s["doc_id"])}</div><div class="title">{esc(s["title"] if s["title"] != s["doc_id"] else "")}</div>'
        f'{chip(s["format"], "grey")}{chip(str(s["chunks"]) + " chunks")}</div>' for s in sources)
    st.markdown(f'<div class="ib-sources">{tiles}</div>', unsafe_allow_html=True)


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
    st.markdown(chip(answer_case, "grey") + chip(pipeline) + chip(answer.backend, "grey"), unsafe_allow_html=True)
    st.header(answer.question)

    with card("answer"):
        st.markdown('<div class="ib-label">Answer</div>', unsafe_allow_html=True)
        if answer.fallback:
            st.warning("**Not enough evidence.** " + answer.summary)
        else:
            if answer.verdict:
                st.markdown(f'<span class="ib-verdict {esc(answer.verdict)}">{esc(answer.verdict)}</span>',
                            unsafe_allow_html=True)
            st.markdown(answer.summary)
        if answer.confidence:
            CONFIDENCE_BOX[answer.confidence](f"**Confidence: {answer.confidence}.** {answer.confidence_reason}")

    c1, c2, c3, c4 = st.columns(4)
    for col, (label, value) in zip((c1, c2, c3, c4), [("Claims", len(answer.claims)),
                                                      ("Sources cited", len(answer.citations)),
                                                      ("Conflicts", len(answer.conflicts)),
                                                      ("Latency", f"{answer.latency_s:.1f}s")]):
        with col, card(f"metric_{label}"):
            st.metric(label, value)

    left, right = st.columns([3, 2], gap="large")
    by_label = {c.label: c for c in answer.citations}
    with left:
        st.subheader("Claims")
        if not answer.claims:
            st.caption("No claims.")
        for i, claim in enumerate(answer.claims):
            with card(f"claim_{i}"):
                flag = chip("unsupported", "bad") if claim.unsupported else ""
                st.markdown(f'<div class="ib-claim"><span class="ib-num">{i + 1}</span>'
                            f'<span>{esc(claim.text)} {flag}</span></div>', unsafe_allow_html=True)
                with st.container(horizontal=True, gap="small"):
                    for label in claim.citations:
                        cit = by_label.get(label)
                        if cit is None:
                            st.caption(f"[{label}] not retrieved")
                            continue
                        st.button(f"[{label}] {cit.doc_id} · {cit.locator}", key=f"cite_{i}_{label}",
                                  on_click=open_trail, args=(cit.chunk_id,), help=cit.quote,
                                  icon=":material/link:")
    with right:
        st.subheader("Conflict flags")
        if not answer.conflicts:
            st.info("No conflicts flagged." if answer.mode == "full"
                    else "The baseline does not detect conflicts.")
        for conflict in answer.conflicts:
            with card(f"flag_{conflict.conflict_id}"):
                st.markdown(f"{SEVERITY_ICON.get(conflict.severity, '⚪')} **{conflict.attribute.replace('_', ' ')}**"
                            f" of {conflict.entity_name or conflict.entity_id} · {conflict.severity}")
                for col, value in zip(st.columns(len(conflict.values)), conflict.values):
                    col.markdown(f'<div class="ib-value">{esc(value.raw_value)}</div>', unsafe_allow_html=True)
                    col.button(value.chunk_id, key=f"conf_{conflict.conflict_id}_{value.chunk_id}",
                               on_click=open_trail, args=(value.chunk_id,))
                if conflict.suggestion:
                    st.caption("💡 Suggestion: " + conflict.suggestion)
        if answer.conflicts:
            st.button("Review conflicts", on_click=go, args=("Conflict Review",), type="primary",
                      icon=":material/balance:", width="stretch")

    with st.expander(f"Retrieved evidence ({len(answer.retrieved)} chunks)"):
        st.dataframe([{"label": f"S{r.rank}", "chunk": r.chunk.chunk_id, "score": r.score,
                       "found by": ", ".join(r.channels) or "dense"} for r in answer.retrieved],
                     hide_index=True, width="stretch",
                     column_config={"score": st.column_config.ProgressColumn("score", min_value=0, max_value=1,
                                                                             format="%.2f")})


# --------------------------------------------------------- 3. Evidence Trail


def chain(chunk_id: str, claims: list[str]) -> None:
    """source -> chunk -> extracted facts -> resolved entities -> claim, for one cited chunk."""
    ev = evidence(answer_case, chunk_id)
    retrieved = next((r for r in answer.retrieved if r.chunk.chunk_id == chunk_id), None)
    where_in = ", ".join(x for x in [f"row {ev['row_number']}" if ev["row_number"] else "",
                                     f"page {ev['page']}" if ev["page"] else "", ev["locator"]] if x)
    with st.container(key="step_source"):
        st.markdown(f"**① Source** · {FORMAT_ICON.get(ev['format'].lower(), '📁')} `{ev['file']}` ({ev['format']})")
    with st.container(key="step_chunk"):
        st.markdown(f"**② Chunk** · {where_in}" + (f" · dated {ev['date']}" if ev["date"] else ""))
        st.code(ev["text"], language=None, wrap_lines=True)
    with st.container(key="step_facts"):
        st.markdown("**③ Extracted facts** (field = value)")
        if ev["facts"]:
            st.dataframe([{"field": f["field"], "value": f["value"], "as written": f["raw_value"],
                           "about": f["canonical_name"] or f["entity_mention"], "extractor": f["extractor"],
                           "confidence": f["confidence"]} for f in ev["facts"]],
                         hide_index=True, width="stretch")
        else:
            st.caption("No values extracted from this chunk (it may only name people or events).")
    with st.container(key="step_entities"):
        st.markdown("**④ Resolved entities**")
        for e in ev["entities"]:
            evidence_text = "; ".join(dict.fromkeys(e["match_evidence"][:3])) or "single mention"
            st.markdown(f"- “{e['mention']}” → **{e['canonical_name']}** (`{e['entity_id']}`)  \n"
                        f"  <small>{esc(evidence_text)}</small>", unsafe_allow_html=True)
        if not ev["entities"]:
            st.caption("No entity named in this chunk.")
    if retrieved:
        with st.container(key="step_retrieval"):
            st.markdown(f"**⑤ Retrieval** · rank {retrieved.rank}, score {retrieved.score:.2f}")
            st.markdown("".join(chip(c) for c in (retrieved.channels or ["dense"])), unsafe_allow_html=True)
    with st.container(key="step_claim"):
        st.markdown("**⑥ Claim**")
        for text in claims:
            st.markdown(f"> {text}")


def evidence_trail() -> None:
    if no_answer():
        return
    st.header("Evidence trail")
    st.caption("How one cited source became a claim: source → chunk → facts → entities → retrieval → claim.")
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
    with card("trail"):
        chain(chunk_id, cited.get(chunk_id) or ["(a side of a flagged conflict, not cited by a claim)"])
    st.subheader("Every claim")
    for n, claim in enumerate(answer.claims, 1):
        with st.expander(f"{n}. {claim.text[:120]}"):
            with st.container(horizontal=True, gap="small"):
                for label in claim.citations:
                    if label in labels:
                        st.button(f"Trace [{label}] {labels[label]}", key=f"trace_{claim.text[:40]}_{label}",
                                  on_click=open_trail, args=(labels[label],), icon=":material/route:")


# -------------------------------------------------------- 4. Conflict Review


def conflict_review() -> None:
    st.header("Conflict review")
    case = st.session_state.get("case", answer_case or DEMO_CASE)
    conflicts = client.conflicts(case)
    in_answer = {c.conflict_id for c in answer.conflicts} if answer and answer_case == case else set()
    accepted = sum(c["status"] == "accepted" for c in conflicts)
    st.markdown(chip(case, "grey") + chip(f"{len(conflicts)} detected")
                + (chip(f"{len(in_answer)} in the last answer", "warn") if in_answer else "")
                + chip(f"{accepted} resolved", "ok"), unsafe_allow_html=True)
    if in_answer and st.toggle("Only conflicts in the last answer", value=True):
        conflicts = [c for c in conflicts if c["conflict_id"] in in_answer]
    if msg := state.pop("accepted_msg", None):
        st.toast(msg, icon="✅")
    if not conflicts:
        st.info("No conflicts. Text facts (chat, PDF, e-mail) need Gemini extraction: "
                "INFOBRIDGE_API_LLM_EXTRACTION=1.")
    for c in conflicts:
        with card(f"conflict_{c['conflict_id']}"):
            status = f"✅ accepted: **{c['accepted_value']}**" if c["status"] == "accepted" else "open"
            st.markdown(f"{SEVERITY_ICON.get(c['severity'], '⚪')} **{c['conflict_id']} · "
                        f"{c['field'].replace('_', ' ')}** of {c['entity_name']} · severity {c['severity']} · {status}")
            n = len(c["values"])
            cols = st.columns([10, 1] * (n - 1) + [10]) if n > 1 else st.columns(1)
            for i, v in enumerate(c["values"]):
                if i:
                    cols[2 * i - 1].markdown('<div class="ib-vs">VS</div>', unsafe_allow_html=True)
                chosen = c["status"] == "accepted" and c["accepted_value"] == v["value"]
                side = f"side_{slug(c['conflict_id'])}_{i}" + ("_chosen" if chosen else "")
                with cols[2 * i], st.container(border=True, key=side):
                    st.markdown(f'<div class="ib-value">{"✅ " if chosen else ""}{esc(v["raw_value"])}</div>',
                                unsafe_allow_html=True)
                    if v["raw_value"] != v["value"]:
                        st.caption(f"normalised: {v['value']}")
                    st.markdown(chip(f"{FORMAT_ICON.get(v['file'].rsplit('.', 1)[-1].lower(), '📁')} {v['file']}",
                                     "grey") + chip(v["locator"], "grey"), unsafe_allow_html=True)
                    st.code(evidence(case, v["chunk_id"])["text"], language=None, wrap_lines=True)
                    st.button("Accepted" if chosen else "Accept this value",
                              key=f"accept_{c['conflict_id']}_{v['value']}", disabled=chosen,
                              on_click=accept, args=(case, c["conflict_id"], v["value"]),
                              type="secondary" if chosen else "primary", icon=":material/check:", width="stretch")
            if c["suggestion"]:
                st.caption("💡 Suggestion: " + c["suggestion"])


{"Home": home, "Query Result": query_result, "Evidence Trail": evidence_trail,
 "Conflict Review": conflict_review}[state.screen]()
