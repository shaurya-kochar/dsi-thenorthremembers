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
