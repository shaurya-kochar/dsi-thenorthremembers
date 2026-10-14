"""Issue #2: normalisation, chunk tags, table facts and the name finder."""

from pathlib import Path

from infobridge.extraction import InformationExtractor
from infobridge.ingestion import load_directory
from infobridge.normalise import (normalise_category, normalise_count, normalise_date, normalise_phone,
                                  normalise_time, normalise_value)

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def test_normalise_values():
    assert normalise_date("22 June 2026") == "2026-06-22"
    assert normalise_date("15/03/2026") == "2026-03-15"  # day first
    assert normalise_date("15 Sept", default_year=2026) == "2026-09-15"
    assert normalise_date("Tue, 20 Oct 2026 19:12 +0530") == "2026-10-20"
    assert normalise_time("5:30 AM") == "05:30" and normalise_time("6:30 pm") == "18:30"
    assert normalise_time("11 pm") == "23:00" and normalise_time("14") is None
    assert normalise_phone("+91 98480 22314") == "9848022314"
    assert normalise_count("20K") == "20" and normalise_count("fourteen") == "14"


def test_normalise_categorical_values():
    # the chat messages of case_04 / case_05 as an LLM would return them
    signup = {"Sorry all, I have to drop out this week": "Withdrawn",
              "I won't make it on Sunday. Please take me off the list.": "Withdrawn",
              "Count me in, I'm confirmed for Sunday.": "Confirmed",
              "maybe, not sure yet": "Tentative", "confirmed": "Confirmed", "Withdrawn": "Withdrawn"}
    for raw, option in signup.items():
        assert normalise_category("signup_status", raw) == option, raw
    attended = {"At station 3 now, covering it for tonight.": "Present", "Reached at 6:30 pm": "Present",
                "handled first aid at the finish line": "Present", "checked in": "Present",
                "missed the run": "Absent", "couldn't make it": "Absent", "Absent": "Absent"}
    for raw, option in attended.items():
        assert normalise_category("attended", raw) == option, raw
    assert normalise_category("payment_status", "unpaid") == "Pending"
    assert normalise_category("payment_status", "PAID") == "Paid"
    assert normalise_category("membership_status", "membership lapsed in June") == "Lapsed"
    assert normalise_category("first_aid_certified", "not certified") == "no"
    assert normalise_category("signup_status", "see you there") is None


def test_normalise_value_uses_categories():
    assert normalise_value("signup_status", "  dropped out ") == "Withdrawn"
    assert normalise_value("signup_status", "something else") == "something else"  # unknown: kept as written
    assert normalise_value("role", "Run Lead") == "Run Lead"  # not categorical


def test_every_chunk_has_file_and_date_tags():
    for case in DATA.glob("case_*/sources"):
        _, chunks = load_directory(case)
        for c in chunks:
            assert c.metadata["file"] == c.doc_id
            assert "date" in c.metadata
        chats = [c for c in chunks if "sender" in c.metadata]
        assert all(c.metadata["date"] for c in chats)
        for c in chunks:  # tags hold ISO dates, never raw header text
            assert c.metadata["date"] is None or len(c.metadata["date"]) == 10


def _mentions(case: str) -> set[tuple[str, str]]:
    _, chunks = load_directory(DATA / case / "sources")
    return {(f.entity_mention, f.chunk_id) for f in InformationExtractor().extract(chunks) if f.attribute == "mention"}


def test_name_finder_finds_name_variants():
    m = _mentions("case_02_medium")
    assert ("S. R. Kumar", "first_aid_training.pdf#page=1&para=4") in m  # initials
    assert ("Ananya", "whatsapp_as3_volunteers.txt#msg=3") in m  # first name alone
    assert ("Farhan bhai", "whatsapp_as3_volunteers.txt#msg=4") in m  # sender with honorific
    assert ("AS3", "whatsapp_as3_volunteers.txt#msg=1") in m  # station abbreviation
    m = _mentions("case_04_sunday_long_run")
    assert ("Vikram anna", "whatsapp_run_coordinators.txt#msg=2") in m
    assert ("Bhargvi Kulkarni", "sunday_long_run_plan.pdf#page=1&para=6") in m  # misspelled first name
    m = _mentions("case_03_conflict")
    assert ("Half Marathon Training Programme (HMTP), Batch 2026B", "programme_rules.pdf#page=1&para=1") in m
    assert ("batch B", "whatsapp_coach_group.txt#msg=7") in m


def test_table_facts_are_normalised():
    _, chunks = load_directory(DATA / "case_04_sunday_long_run" / "sources")
    facts = InformationExtractor().extract(chunks)
    phones = [f for f in facts if f.attribute == "phone"]
    assert phones and all(len(f.value) == 10 and f.value.isdigit() for f in phones)
    assert any(f.attribute == "signup_status" and f.entity_mention == "Kavya Reddy" for f in facts)
