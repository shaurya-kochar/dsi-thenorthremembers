"""Smoke test: the demo app loads and answers without errors (retrieval-only mode)."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def test_demo_app_answers(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    assert not at.exception
    at.button[0].click().run()
    assert not at.exception
    assert {m.label for m in at.metric} >= {"Claims", "Conflicts"}
