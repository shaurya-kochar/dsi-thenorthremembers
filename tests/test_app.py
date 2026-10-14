"""Smoke test: the demo app loads and answers without errors (retrieval-only mode)."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def test_demo_app_answers(monkeypatch):
    from dataclasses import replace

    import infobridge.config as config

    # Settings are read from .env at import time, so patch the object itself: tests must not call Gemini.
    monkeypatch.setattr(config, "settings", replace(config.settings, gemini_api_key=None))
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    assert not at.exception
    at.button[0].click().run()
    assert not at.exception
    assert {m.label for m in at.metric} >= {"Claims", "Conflicts"}


def test_demo_app_walks_the_four_screens(monkeypatch):
    from dataclasses import replace

    import infobridge.config as config

    monkeypatch.setattr(config, "settings", replace(config.settings, gemini_api_key=None))
    monkeypatch.setenv("INFOBRIDGE_API_URL", "http://127.0.0.1:9")  # no server: the app runs the pipeline itself
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    assert {r.label for r in at.radio} == {"Screen", "Pipeline", "Answer engine"}  # incl. the baseline/full toggle
    at.button[0].click().run()  # Ask -> Query Result
    assert at.session_state["screen"] == "Query Result" and not at.exception
    notes = [e.value for e in list(at.success) + list(at.warning) + list(at.error)]
    assert any(n.startswith("**Confidence:") for n in notes)  # the confidence note
    badge = next(b for b in at.button if b.key and b.key.startswith("cite_"))
    badge.click().run()  # a citation badge opens its evidence trail
    assert at.session_state["screen"] == "Evidence Trail" and not at.exception
    assert any("Source" in m.value for m in at.markdown) and any("Resolved entities" in m.value for m in at.markdown)

    at.radio(key="screen").set_value("Home").run()
    at.selectbox(key="case").set_value("case_05_volunteer_attendance").run()
    at.radio(key="screen").set_value("Conflict Review").run()
    assert not at.exception
    accept = next(b for b in at.button if b.key and b.key.startswith("accept_") and b.key.endswith("_Lakshmi Prasad"))
    accept.click().run()
    assert any("accepted: **Lakshmi Prasad**" in m.value for m in at.markdown)
