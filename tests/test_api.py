"""Issue #8: the API, offline (extractive backend, no LLM extraction)."""

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import infobridge.api as api

RAVI = "Is Ravi Sharma eligible for the Half Marathon Training Programme Batch 2026B?"
CASE3 = "case_03_conflict"


@pytest.fixture(scope="module")
def client():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(api, "service", api.Service(llm_extraction=False))
        yield TestClient(api.app)


def test_cases_list_every_case_with_its_split(client):
    cases = {c["case"]: c for c in client.get("/cases").json()}
    assert len(cases) == 7
    assert cases[CASE3]["split"] == "build" and cases[CASE3]["question"] == RAVI
    assert cases["case_06_event_schedule"]["split"] == "held_out"


def test_sources_have_format_and_chunk_count(client):
    sources = {s["doc_id"]: s for s in client.get("/sources", params={"case": CASE3}).json()}
    assert set(sources) == {"members.csv", "registrations.csv", "whatsapp_coach_group.txt", "programme_rules.pdf"}
    assert sources["members.csv"]["format"] == "csv" and sources["members.csv"]["chunks"] == 7
    assert client.get("/sources", params={"case": "case_99"}).status_code == 404


def test_query_full_and_baseline(client):
    full = client.post("/query", json={"case": CASE3, "question": RAVI, "mode": "full", "backend": "extractive"})
    assert full.status_code == 200
    answer = full.json()
    assert answer["mode"] == "full" and answer["entities"] == ["person:ravi-sharma", "programme:hmtp-2026b"]
    assert answer["confidence"] in ("high", "medium", "low") and answer["confidence_reason"]
    ids = {r["chunk"]["chunk_id"] for r in answer["retrieved"]}
    assert {"members.csv#row=5", "registrations.csv#row=3"} <= ids
    baseline = client.post("/query", json={"case": CASE3, "question": RAVI, "mode": "baseline"}).json()
    assert baseline["mode"] == "baseline" and baseline["conflicts"] == []
    assert client.post("/query", json={"case": CASE3, "question": RAVI, "mode": "other"}).status_code == 400
    assert client.post("/query", json={"case": CASE3, "question": RAVI, "backend": "gpt"}).status_code == 400


def test_evidence_by_path_and_by_query(client):
    by_path = client.get(f"/evidence/{quote('members.csv#row=5', safe='')}", params={"case": CASE3}).json()
    by_query = client.get("/evidence", params={"case": CASE3, "chunk_id": "members.csv#row=5"}).json()
    assert by_path == by_query
    assert (by_path["file"], by_path["locator"], by_path["row_number"]) == ("members.csv", "row=5", 5)
    assert ("medical_clearance_date", "2026-03-15") in {(f["field"], f["value"]) for f in by_path["facts"]}
    assert "person:ravi-sharma" in {e["entity_id"] for e in by_path["entities"]}
    pdf = client.get("/evidence", params={"case": CASE3, "chunk_id": "programme_rules.pdf#page=1&para=2"}).json()
    assert pdf["page"] == 1 and "8 November 2026" in pdf["text"]
    assert client.get("/evidence", params={"case": CASE3, "chunk_id": "members.csv#row=99"}).status_code == 404


def test_conflict_review_accepts_one_value(client):
    conflicts = client.get("/conflicts", params={"case": "case_05_volunteer_attendance"}).json()
    laxmi = next(c for c in conflicts if c["field"] == "full_name")
    assert laxmi["status"] == "open" and laxmi["entity_name"] and laxmi["severity"] == "low"
    assert {v["file"] for v in laxmi["values"]} == {"attendance_log.csv", "night_run_report.txt"}
    url = f"/conflicts/{laxmi['conflict_id']}/accept"
    assert client.post(url, json={"case": "case_05_volunteer_attendance", "value": "Nobody"}).status_code == 400
    assert client.post("/conflicts/C999/accept", json={"case": "case_05_volunteer_attendance",
                                                      "value": "x"}).status_code == 404
    accepted = client.post(url, json={"case": "case_05_volunteer_attendance", "value": "Lakshmi Prasad"}).json()
    assert (accepted["status"], accepted["accepted_value"]) == ("accepted", "Lakshmi Prasad")
    still = client.get("/conflicts", params={"case": "case_05_volunteer_attendance", "status": "accepted"}).json()
    assert [c["conflict_id"] for c in still] == [laxmi["conflict_id"]]
    assert client.get("/conflicts", params={"case": CASE3, "status": "maybe"}).status_code == 400
