"""Generate the Hack 1 synthetic NGO cases and their answer keys (issue #1).

    python scripts/build_hack1_data.py

Writes four new cases next to the three from Sprint 2:

    case_04_sunday_long_run      demo scenario: signup sheet, event plan PDF, coordinators' chat,
                                 public data slice (WHO heat-and-health excerpt)       build set
    case_05_volunteer_attendance attendance log, volunteers' chat, coordinator's report email   build set
    case_06_event_schedule       Q4 events sheet, November newsletter email               held-out set
    case_07_race_day_logistics   aid station plan PDF, station leads' chat                held-out set

How the data is made: names come from Faker (en_IN, fixed seed) and are combined
with hand-written messages, so every inconsistency is deliberate. Each planted
conflict and every mention of every entity is recorded while the text is written,
then turned into exact chunk ids by ingesting the generated files. The answer key
(``gold.json``) therefore always matches the data.

Privacy: no real Hyderabad Runners member data is used. Names and phone numbers
are generated; e-mail addresses use the reserved ``example.org`` domain. Facts and
test questions (``facts`` / ``queries``) are added to the answer keys in issue #10.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pymupdf
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "data" / "synthetic"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_synthetic import csv_to_xlsx, text_to_pdf  # noqa: E402
from infobridge.ingestion import load_directory  # noqa: E402

SEED = 2026
SPLIT = {
    "build": ["case_01_simple", "case_02_medium", "case_03_conflict", "case_04_sunday_long_run",
              "case_05_volunteer_attendance"],
    "held_out": ["case_06_event_schedule", "case_07_race_day_logistics"],
}

# First names used by hand-written characters; Faker names must not reuse them,
# so a first name in a chat message points to one person unless a decoy is intended.
RESERVED_FIRST = {
    "vikram", "sneha", "kavya", "kavitha", "imran", "rohit", "rohith", "arun", "bhargavi", "sai",
    "meera", "laxmi", "lakshmi", "naveen", "farah", "pooja", "harish", "harsha", "swathi", "deepak",
    "anjali", "rahul", "divya", "karthik", "neha", "suresh", "priyanka", "manoj", "shalini", "abdul",
    "gayatri", "prakash", "rekha",
}


# --------------------------------------------------------------------------- people


class People:
    """Seeded pool of synthetic names, phones and e-mails."""

    def __init__(self, seed: int):
        self.fake = Faker("en_IN")
        Faker.seed(seed)
        self.rng = random.Random(seed)
        self.used_first: set[str] = set(RESERVED_FIRST)
        self.used_phones: set[str] = set()

    def name(self) -> str:
        while True:
            first, last = self.fake.first_name(), self.fake.last_name()
            if not (first.isalpha() and last.isalpha() and len(first) >= 4 and len(last) >= 4):
                continue
            if first.lower() in self.used_first:
                continue
            self.used_first.add(first.lower())
            return f"{first} {last}"

    def phone(self) -> str:
        while True:
            digits = self.rng.choice("6789") + "".join(self.rng.choice("0123456789") for _ in range(9))
            if digits not in self.used_phones:
                self.used_phones.add(digits)
                return digits

    @staticmethod
    def pretty(phone: str) -> str:
        return f"+91 {phone[:5]} {phone[5:]}"

    @staticmethod
    def email(name: str) -> str:
        return ".".join(name.lower().split()) + "@example.org"


# ----------------------------------------------------------------------- documents


@dataclass
class Ref:
    doc: str
    kind: str  # "row" | "msg" | "para"
    n: int


@dataclass
class Sheet:
    name: str  # file name in sources/
    columns: list[str]
    rows: list[dict] = field(default_factory=list)

    def add(self, **row) -> Ref:
        self.rows.append(row)
        return Ref(self.name, "row", len(self.rows) + 1)  # header is row 1


@dataclass
class Chat:
    name: str
    lines: list[str] = field(default_factory=list)

    def msg(self, when: str, sender: str, text: str) -> Ref:
        self.lines.append(f"{when} - {sender}: {text}")
        return Ref(self.name, "msg", len(self.lines))


@dataclass
class Paper:
    """A PDF (paragraphs rendered one block each) or an e-mail (headers + paragraphs)."""

    name: str
    headers: dict[str, str] = field(default_factory=dict)
    paras: list[str] = field(default_factory=list)

    def para(self, text: str) -> Ref:
        self.paras.append(text)
        return Ref(self.name, "para", len(self.paras))


class Case:
    def __init__(self, case_id: str, description: str):
        self.case_id = case_id
        self.description = description
        self.dir = SYN / case_id
        self.docs: list = []
        self.entities: dict[str, dict] = {}
        self.mentions: list[tuple[str, str, Ref]] = []
        self.conflicts: list[dict] = []
        self.extra_files: list[tuple[Path, str]] = []

    def add(self, doc):
        self.docs.append(doc)
        return doc

    def entity(self, canonical: str, etype: str) -> str:
        self.entities.setdefault(canonical, {"canonical": canonical, "type": etype, "mentions": []})
        return canonical

    def mention(self, canonical: str, text: str, ref: Ref) -> None:
        self.mentions.append((canonical, text, ref))

    def conflict(self, entity: str, attribute: str, values: list[tuple[str, list[str], list[Ref]]],
                 severity: str, note: str) -> None:
        self.conflicts.append({"entity": entity, "attribute": attribute, "values": values,
                               "severity": severity, "note": note})

    # ------------------------------------------------------------------ writing

    def write(self) -> None:
        if self.dir.exists():
            shutil.rmtree(self.dir)
        sources = self.dir / "sources"
        sources.mkdir(parents=True)
        for doc in self.docs:
            if isinstance(doc, Sheet):
                df = pd.DataFrame(doc.rows, columns=doc.columns)
                if doc.name.endswith(".xlsx"):
                    src = self.dir / "xlsx_src" / doc.name.replace(".xlsx", ".csv")
                    src.parent.mkdir(exist_ok=True)
                    df.to_csv(src, index=False)
                    csv_to_xlsx(src, sources / doc.name)
                else:
                    df.to_csv(sources / doc.name, index=False)
            elif isinstance(doc, Chat):
                (sources / doc.name).write_text("\n".join(doc.lines) + "\n")
            elif doc.name.endswith(".pdf"):
                src = self.dir / "pdf_src" / doc.name.replace(".pdf", ".txt")
                src.parent.mkdir(exist_ok=True)
                src.write_text("\n\n".join(doc.paras) + "\n")
                text_to_pdf(src, sources / doc.name)
            else:
                head = "\n".join(f"{k}: {v}" for k, v in doc.headers.items())
                (sources / doc.name).write_text(head + "\n\n" + "\n\n".join(doc.paras) + "\n")
        for src_path, name in self.extra_files:
            shutil.copy(src_path, sources / name)

        _, chunks = load_directory(sources)
        self.chunks = {c.chunk_id: c for c in chunks}
        self.gold = self._gold()
        (self.dir / "gold.json").write_text(json.dumps(self.gold, indent=2, ensure_ascii=False) + "\n")

    def chunk_id(self, ref: Ref) -> str:
        if ref.kind in ("row", "msg"):
            cid = f"{ref.doc}#{ref.kind}={ref.n}"
        elif ref.doc.endswith(".pdf"):
            paper = next(d for d in self.docs if getattr(d, "name", None) == ref.doc)
            start = re.sub(r"\s+", " ", paper.paras[ref.n - 1])[:40]
            hits = [c for c in self.chunks.values() if c.doc_id == ref.doc and c.text.startswith(start)]
            assert len(hits) == 1, (ref, start, len(hits))
            cid = hits[0].chunk_id
        else:
            cid = f"{ref.doc}#para={ref.n}"
        assert cid in self.chunks, cid
        return cid

    def _gold(self) -> dict:
        for canonical, text, ref in self.mentions:
            cid = self.chunk_id(ref)
            assert text.lower() in self.chunks[cid].text.lower(), (text, cid, self.chunks[cid].text)
            entry = {"text": text, "chunk_id": cid}
            if entry not in self.entities[canonical]["mentions"]:
                self.entities[canonical]["mentions"].append(entry)
        conflicts = []
        for i, c in enumerate(self.conflicts, start=1):
            values = []
            for value, surfaces, refs in c["values"]:
                sources = [self.chunk_id(r) for r in refs]
                for s in sources:
                    text = self.chunks[s].text.lower()
                    assert any(x.lower() in text for x in surfaces), (c["attribute"], value, s, text)
                values.append({"value": value, "surface_any": surfaces, "sources": sources})
            assert c["entity"] in self.entities, c["entity"]
            conflicts.append({"id": f"C{i}", "entity": c["entity"], "attribute": c["attribute"],
                              "values": values, "severity": c["severity"], "note": c["note"]})
        split = "held_out" if self.case_id in SPLIT["held_out"] else "build"
        return {"case_id": self.case_id, "description": self.description, "split": split,
                "queries": [], "facts": [],
                "entities": [{"canonical": e["canonical"], "type": e["type"], "mentions": e["mentions"]}
                             for e in self.entities.values()],
                "conflicts": conflicts}


# ---------------------------------------------------------------------------- cases


def case_04(people: People) -> Case:
    case = Case("case_04_sunday_long_run",
                "Demo scenario. Signup sheet, event plan PDF, coordinators' WhatsApp group and a public data "
                "slice (WHO heat-and-health excerpt) for the Sunday Long Run on 15 November 2026. The plan PDF "
                "says 14 volunteers confirmed, the chat says 12; the run lead is named three ways; start time, "
                "meeting point, distance, three signup statuses, a phone number and a name spelling disagree.")
    sheet = case.add(Sheet("volunteer_signups.xlsx",
                           ["vol_id", "full_name", "phone", "email", "role", "signup_status", "shift"]))
    plan = case.add(Paper("sunday_long_run_plan.pdf"))
    chat = case.add(Chat("whatsapp_run_coordinators.txt"))

    event = case.entity("Sunday Long Run (15 Nov 2026)", "event")

    # (name, role, status) for the hand-written characters; the rest are Faker volunteers
    cast = [
        ("Vikram Rao", "Run Lead", "Confirmed"), ("Sneha Naidu", "Co-lead", "Confirmed"),
        ("Kavya Reddy", "Course Marshal", "Confirmed"), ("Kavitha Reddy", "Course Marshal", "Tentative"),
        ("Imran Siddiqui", "Water Station", "Confirmed"), ("Rohit Varma", "Sweeper", "Tentative"),
        ("Rohith Verma", "Course Marshal", "Confirmed"), ("Arun Prakash", "First Aid", "Confirmed"),
        ("Bhargavi Kulkarni", "Water Station", "Confirmed"), ("Sai Kiran", "Water Station", "Confirmed"),
        ("Sai Krishna", "Photographer", "Tentative"),
    ]
    statuses = ["Confirmed"] * 6 + ["Tentative"] * 6 + ["Withdrawn"] * 5
    roles = ["Course Marshal", "Water Station", "Bag Drop", "Pacer", "Registration Desk"]
    for _ in statuses:
        cast.append((people.name(), people.rng.choice(roles), None))
    extra = iter(statuses)
    rows, phones = {}, {}
    for i, (name, role, status) in enumerate(cast):
        status = status or next(extra)
        phone = people.phone()
        phones[name] = phone
        shift = "04:30-09:00" if role in ("Run Lead", "Co-lead", "First Aid") else "05:00-09:00"
        rows[name] = sheet.add(vol_id=f"V-{201 + i}", full_name=name, phone=people.pretty(phone),
                               email=people.email(name), role=role, signup_status=status, shift=shift)
        case.entity(name, "person")
        case.mention(name, name, rows[name])
    confirmed = sum(r["signup_status"] == "Confirmed" for r in sheet.rows)
    assert confirmed == 14, confirmed

    p_title = plan.para("Hyderabad Runners - Sunday Long Run, 15 November 2026: Event Plan")
    p_lead = plan.para("Run lead: Vikram Rao (V-201). Co-lead: Sneha Naidu (V-202). The run lead takes the final "
                       "call on weather and route changes.")
    p_route = plan.para("Route: 18 km out-and-back along the Gandipet lake road, with water stations at km 6 "
                        "and km 12.")
    p_meet = plan.para("Meeting point: Gandipet Park Gate 2. Volunteer briefing at 4:45 AM, flag-off at 5:15 AM.")
    p_count = plan.para("Volunteers confirmed: 14, as per the signup sheet on 7 November 2026.")
    p_water = plan.para("Water station volunteers: Bhargvi Kulkarni, S. Kiran and I. Siddiqui at km 6; the "
                        "co-lead covers km 12.")
    plan.para("Questions about the run: runs@hyderabadrunners.example.org")
    case.mention(event, "Sunday Long Run", p_title)
    case.mention("Vikram Rao", "Vikram Rao", p_lead)
    case.mention("Sneha Naidu", "Sneha Naidu", p_lead)
    case.mention("Bhargavi Kulkarni", "Bhargvi Kulkarni", p_water)
    case.mention("Sai Kiran", "S. Kiran", p_water)
    case.mention("Imran Siddiqui", "I. Siddiqui", p_water)

    m1 = chat.msg("08/11/2026, 19:02", "Vikram Rao",
                  "Hi all, the Sunday Long Run on 15 Nov is on. Plan PDF and signup sheet are in the drive.")
    m2 = chat.msg("08/11/2026, 19:05", "Sneha N", "Vikram anna, how many have confirmed so far?")
    m3 = chat.msg("09/11/2026, 07:40", "Kavya", "Sorry all, I have to drop out this week, family function.")
    m4 = chat.msg("10/11/2026, 21:15", "Imran Siddiqui",
                  "Down with fever, I won't make it on Sunday. Please take me off the list.")
    m5 = chat.msg("11/11/2026, 18:30", "Vikram Rao",
                  "Update: we have 12 confirmed so far after Kavya and Imran dropped out.")
    m6 = chat.msg("11/11/2026, 18:33", "Rohit Varma", "Count me in, I'm confirmed for Sunday.")
    m7 = chat.msg("12/11/2026, 08:10", "Arun P", "Arun here, my number has changed. New number is 98712 34560.")
    m8 = chat.msg("12/11/2026, 20:45", "Vikram Rao",
                  "Flag-off at 5:30 sharp. Please be at Gandipet Park Gate 1 by 4:45 for the briefing.")
    m9 = chat.msg("13/11/2026, 07:20", "Sneha N", "Reminder, it is the 20K route this time, water at km 6 and km 12.")
    m10 = chat.msg("13/11/2026, 07:25", "Bhargavi Kulkarni", "I'll handle the km 6 water station with Sai Kiran.")
    m11 = chat.msg("14/11/2026, 21:00", "Vikram Rao", "Thanks everyone, see you tomorrow at the lake.")
    case.mention(event, "Sunday Long Run", m1)
    for ref in (m1, m5, m8, m11):
        case.mention("Vikram Rao", "Vikram Rao", ref)
    case.mention("Vikram Rao", "Vikram anna", m2)
    case.mention("Sneha Naidu", "Sneha N", m2)
    case.mention("Sneha Naidu", "Sneha N", m9)
    case.mention("Kavya Reddy", "Kavya", m3)
    case.mention("Kavya Reddy", "Kavya", m5)
    case.mention("Imran Siddiqui", "Imran Siddiqui", m4)
    case.mention("Imran Siddiqui", "Imran", m5)
    case.mention("Rohit Varma", "Rohit Varma", m6)
    case.mention("Arun Prakash", "Arun P", m7)
    case.mention("Bhargavi Kulkarni", "Bhargavi Kulkarni", m10)
    case.mention("Sai Kiran", "Sai Kiran", m10)

    case.conflict(event, "volunteer_count", [
        ("14", ["14"], [p_count]), ("12", ["12 confirmed"], [m5])],
        "medium", "The plan PDF copies the signup sheet of 7 Nov; the chat count is later and accounts for Kavya "
                  "and Imran dropping out.")
    case.conflict(event, "start_time", [
        ("05:15", ["5:15"], [p_meet]), ("05:30", ["5:30"], [m8])],
        "high", "Flag-off time decides when volunteers must be at their posts.")
    case.conflict(event, "meeting_point", [
        ("Gandipet Park Gate 2", ["gate 2"], [p_meet]), ("Gandipet Park Gate 1", ["gate 1"], [m8])],
        "high", "Participants could gather at the wrong gate.")
    case.conflict(event, "distance_km", [
        ("18", ["18 km"], [p_route]), ("20", ["20k"], [m9])],
        "medium", "The plan says 18 km; the chat reminder says 20K.")
    case.conflict("Kavya Reddy", "signup_status", [
        ("Confirmed", ["confirmed"], [rows["Kavya Reddy"]]), ("Withdrawn", ["drop out"], [m3])],
        "medium", "Kavya dropped out after the sheet was filled; the sheet was not updated.")
    case.conflict("Imran Siddiqui", "signup_status", [
        ("Confirmed", ["confirmed"], [rows["Imran Siddiqui"]]), ("Withdrawn", ["take me off the list"], [m4])],
        "medium", "Imran withdrew because of fever; the sheet still says Confirmed.")
    case.conflict("Rohit Varma", "signup_status", [
        ("Tentative", ["tentative"], [rows["Rohit Varma"]]), ("Confirmed", ["confirmed for sunday"], [m6])],
        "medium", "Rohit confirmed in the chat; the sheet still says Tentative.")
    new_phone = "9871234560"
    case.conflict("Arun Prakash", "phone", [
        (phones["Arun Prakash"], [People.pretty(phones["Arun Prakash"])], [rows["Arun Prakash"]]),
        (new_phone, ["98712 34560"], [m7])],
        "low", "Arun changed his number; the newer number is in the chat.")
    case.conflict("Bhargavi Kulkarni", "full_name", [
        ("Bhargavi Kulkarni", ["bhargavi kulkarni"], [rows["Bhargavi Kulkarni"]]),
        ("Bhargvi Kulkarni", ["bhargvi kulkarni"], [p_water])],
        "low", "Spelling mistake in the plan PDF; the sheet and the chat agree on 'Bhargavi'.")

    # public data slice: two text-rich pages of the WHO heat-and-health report
    who = ROOT / "data" / "public" / "who" / "who_heat_and_health_europe_2021.pdf"
    excerpt = case.dir.parent / ".who_excerpt_tmp.pdf"
    src = pymupdf.open(who)
    out = pymupdf.open()
    out.insert_pdf(src, from_page=0, to_page=1)
    out.save(excerpt)
    case.extra_files.append((excerpt, "public_who_heat_and_health_excerpt.pdf"))
    return case


def case_05(people: People) -> Case:
    case = Case("case_05_volunteer_attendance",
                "Attendance log, volunteers' WhatsApp group and the coordinator's report e-mail for the Saturday "
                "Night Run on 3 October 2026. Two volunteers marked Absent in the log were present, two station "
                "assignments disagree, the headcount (29 vs 31), finish time and one check-in time disagree, and "
                "one name is spelled two ways.")
    log = case.add(Sheet("attendance_log.csv",
                         ["vol_id", "volunteer_name", "phone", "station", "status", "check_in_time"]))
    chat = case.add(Chat("whatsapp_night_run_volunteers.txt"))
    mail = case.add(Paper("night_run_report.txt", headers={
        "From": "Meera Joshi <meera.joshi@example.org>",
        "To": "volunteers@hyderabadrunners.example.org",
        "Date": "Sun, 4 Oct 2026 10:15 +0530",
        "Subject": "Saturday Night Run (3 Oct) - thank you and report",
    }))
    event = case.entity("Saturday Night Run (3 Oct 2026)", "event")

    # (name, station, status, check-in)
    cast = [
        ("Meera Joshi", "Control Desk", "Present", "17:30"),
        ("Laxmi Prasad", "Bag Drop", "Present", "17:50"),
        ("Naveen Goud", "Station 3", "Absent", ""),
        ("Farah Ansari", "Finish Line", "Absent", ""),
        ("Pooja Nair", "Station 2", "Present", "18:10"),
        ("Pooja Rani", "Station 4", "Present", "18:00"),
        ("Harish Kumar", "Station 5", "Present", "18:15"),
        ("Harsha Kumar", "Station 1", "Present", "18:05"),
        ("Swathi Rao", "Station 1", "Present", "18:05"),
        ("Deepak Chauhan", "Station 2", "Absent", ""),
    ]
    stations = ["Station 1", "Station 2", "Station 3", "Station 4", "Station 5", "Finish Line"]
    for i in range(24):
        status = "Absent" if i in (3, 11) else "Present"
        check_in = "" if status == "Absent" else f"{17 + (i % 2)}:{['40', '45', '50', '55'][i % 4]}"
        cast.append((people.name(), stations[i % len(stations)], status, check_in))
    rows, phones = {}, {}
    for i, (name, station, status, check_in) in enumerate(cast):
        phones[name] = people.phone()
        rows[name] = log.add(vol_id=f"V-{301 + i}", volunteer_name=name, phone=phones[name], station=station,
                             status=status, check_in_time=check_in)
        case.entity(name, "person")
        case.mention(name, name, rows[name])
    present = sum(r["status"] == "Present" for r in log.rows)
    assert present == 29, present

    m1 = chat.msg("03/10/2026, 17:45", "Meera Joshi", "Volunteers, please check in at the control desk before "
                  "6 pm. Stations open at 6:30 pm for the Night Run.")
    m2 = chat.msg("03/10/2026, 18:31", "Swathi", "Reached at 6:30 pm, on my way to station 1.")
    m3 = chat.msg("03/10/2026, 18:40", "Naveen Goud", "At station 3 now, covering it for tonight.")
    m4 = chat.msg("03/10/2026, 22:55", "Meera Joshi",
                  "29 of us checked in tonight, thank you all! We wrapped up at 11 pm.")
    m5 = chat.msg("04/10/2026, 08:20", "Pooja N", "For the record, I was at station 4 the whole night, not station 2.")
    m6 = chat.msg("04/10/2026, 08:35", "Meera Joshi", "Thanks Naveen for covering station 3 at the last minute!")
    case.mention(event, "Night Run", m1)
    for ref in (m1, m4, m6):
        case.mention("Meera Joshi", "Meera Joshi", ref)
    case.mention("Swathi Rao", "Swathi", m2)
    case.mention("Naveen Goud", "Naveen Goud", m3)
    case.mention("Naveen Goud", "Naveen", m6)
    case.mention("Pooja Nair", "Pooja N", m5)

    e1 = mail.para("Thank you all for the Saturday Night Run on 3 October. 31 volunteers turned up and the run "
                   "wrapped up by 10:30 PM.")
    e2 = mail.para("Station highlights: Harish Kumar ran the water point at Station 1, Lakshmi Prasad managed the "
                   "bag drop, and Farah Ansari handled first aid at the finish line.")
    mail.para("Next month we need more volunteers at the finish. Please reply to this mail if you can help.")
    mail.para("Thanks,\nMeera")
    case.mention(event, "Saturday Night Run", e1)
    case.mention("Meera Joshi", "Meera Joshi", e1)
    case.mention("Harish Kumar", "Harish Kumar", e2)
    case.mention("Laxmi Prasad", "Lakshmi Prasad", e2)
    case.mention("Farah Ansari", "Farah Ansari", e2)

    case.conflict(event, "volunteers_present", [
        ("29", ["29 of us"], [m4]), ("31", ["31 volunteers"], [e1])],
        "medium", "The chat count matches the log's Present rows; the report also counts Naveen and Farah, who "
                  "were marked Absent but were there.")
    case.conflict(event, "end_time", [
        ("23:00", ["11 pm"], [m4]), ("22:30", ["10:30 pm"], [e1])],
        "low", "The run ended between 10:30 and 11 pm; the two messages round differently.")
    case.conflict("Naveen Goud", "attended", [
        ("Absent", ["absent"], [rows["Naveen Goud"]]), ("Present", ["at station 3 now"], [m3])],
        "medium", "Naveen covered station 3 but was never checked in at the desk.")
    case.conflict("Farah Ansari", "attended", [
        ("Absent", ["absent"], [rows["Farah Ansari"]]), ("Present", ["farah ansari handled first aid"], [e2])],
        "medium", "Farah handled first aid at the finish but is marked Absent.")
    case.conflict("Pooja Nair", "assigned_station", [
        ("Station 2", ["station 2"], [rows["Pooja Nair"]]), ("Station 4", ["station 4"], [m5])],
        "low", "Pooja says she was at station 4 all night.")
    case.conflict("Harish Kumar", "assigned_station", [
        ("Station 5", ["station 5"], [rows["Harish Kumar"]]), ("Station 1", ["station 1"], [e2])],
        "low", "The report places Harish at station 1; the log says station 5.")
    case.conflict("Laxmi Prasad", "full_name", [
        ("Laxmi Prasad", ["laxmi prasad"], [rows["Laxmi Prasad"]]),
        ("Lakshmi Prasad", ["lakshmi prasad"], [e2])],
        "low", "Two spellings of the same name (Laxmi / Lakshmi).")
    case.conflict("Swathi Rao", "check_in_time", [
        ("18:05", ["18:05"], [rows["Swathi Rao"]]), ("18:30", ["6:30 pm"], [m2])],
        "low", "Swathi's own message says she reached at 6:30 pm.")
    return case


def case_06(people: People) -> Case:
    case = Case("case_06_event_schedule",
                "Q4 events sheet and the November newsletter e-mail. The newsletter moves two events to a "
                "different date, changes one start time and names a different lead for one event.")
    sheet = case.add(Sheet("events_q4.csv", ["event_id", "event_name", "date", "start_time", "meeting_point",
                                             "distance_km", "lead_volunteer", "status"]))
    mail = case.add(Paper("newsletter_november.txt", headers={
        "From": "Anjali Desai <anjali.desai@example.org>",
        "To": "members@hyderabadrunners.example.org",
        "Date": "Sun, 1 Nov 2026 08:00 +0530",
        "Subject": "Hyderabad Runners newsletter - November and December runs",
    }))
    events = [
        ("EV-2026-061", "Lake Loop 15K", "2026-11-08", "05:30", "Durgam Cheruvu Park", "15", "Anjali Desai"),
        ("EV-2026-062", "Golconda Heritage Run", "2026-11-22", "06:00", "Golconda Fort Main Gate", "10", "Rahul Menon"),
        ("EV-2026-063", "Pink Run for Cancer Awareness", "2026-11-29", "05:45", "Necklace Road", "5", "Divya Shetty"),
        ("EV-2026-064", "Monsoon Trail Run", "2026-12-06", "06:00", "Gandipet Lake", "12", "Karthik Iyengar"),
        ("EV-2026-065", "Christmas Fun Run", "2026-12-20", "06:30", "KBR Park Gate 1", "5", "Neha Kapoor"),
        ("EV-2026-066", "Year-End Half Marathon", "2026-12-27", "05:00", "Gachibowli Stadium", "21", "Suresh Babu"),
    ]
    rows = {}
    for ev_id, name, date, start, meet, km, lead in events:
        rows[name] = sheet.add(event_id=ev_id, event_name=name, date=date, start_time=start, meeting_point=meet,
                               distance_km=km, lead_volunteer=lead, status="Scheduled")
        case.entity(name, "event")
        case.entity(lead, "person")
        case.mention(name, name, rows[name])
        case.mention(lead, lead, rows[name])

    mail.para("Hi everyone, here are the club runs for November and December. Please register on the website a "
              "week before each run.")
    n1 = mail.para("Lake Loop 15K on Sunday 8 November at 5:30 AM from Durgam Cheruvu Park, led by Anjali.")
    n2 = mail.para("Golconda Heritage Run on Sunday 29 November, 6:00 AM at Golconda Fort Main Gate, led by Rahul M.")
    n3 = mail.para("Pink Run for Cancer Awareness on Sunday 29 November at 6:15 AM from Necklace Road, led by Divya S.")
    n4 = mail.para("Monsoon Trail Run on Sunday 13 December from Gandipet Lake, 12 km, led by Karthik I.")
    n5 = mail.para("Christmas Fun Run on Sunday 20 December, 6:30 AM at KBR Park Gate 1, led by Priyanka Sen "
                   "(Neha is travelling).")
    n6 = mail.para("Year-End Half Marathon on Sunday 27 December, 5:00 AM at Gachibowli Stadium, led by Suresh Babu.")
    mail.para("See you on the road,\nAnjali")
    case.entity("Priyanka Sen", "person")
    for ref, ev, lead_text, lead in [(n1, "Lake Loop 15K", "Anjali", "Anjali Desai"),
                                     (n2, "Golconda Heritage Run", "Rahul M.", "Rahul Menon"),
                                     (n3, "Pink Run for Cancer Awareness", "Divya S.", "Divya Shetty"),
                                     (n4, "Monsoon Trail Run", "Karthik I.", "Karthik Iyengar"),
                                     (n5, "Christmas Fun Run", "Priyanka Sen", "Priyanka Sen"),
                                     (n6, "Year-End Half Marathon", "Suresh Babu", "Suresh Babu")]:
        case.mention(ev, ev, ref)
        case.mention(lead, lead_text, ref)
    case.mention("Neha Kapoor", "Neha", n5)

    case.conflict("Golconda Heritage Run", "event_date", [
        ("2026-11-22", ["2026-11-22"], [rows["Golconda Heritage Run"]]), ("2026-11-29", ["29 november"], [n2])],
        "high", "The newsletter moved the run a week later; one of the two is out of date.")
    case.conflict("Pink Run for Cancer Awareness", "start_time", [
        ("05:45", ["05:45"], [rows["Pink Run for Cancer Awareness"]]), ("06:15", ["6:15"], [n3])],
        "high", "Different start times in the sheet and the newsletter.")
    case.conflict("Monsoon Trail Run", "event_date", [
        ("2026-12-06", ["2026-12-06"], [rows["Monsoon Trail Run"]]), ("2026-12-13", ["13 december"], [n4])],
        "high", "The newsletter says 13 December; the sheet says 6 December.")
    case.conflict("Christmas Fun Run", "lead_volunteer", [
        ("Neha Kapoor", ["neha kapoor"], [rows["Christmas Fun Run"]]), ("Priyanka Sen", ["priyanka sen"], [n5])],
        "medium", "Neha is travelling, so Priyanka leads; the sheet was not updated.")
    return case


def case_07(people: People) -> Case:
    case = Case("case_07_race_day_logistics",
                "Aid station plan PDF and the station leads' WhatsApp group for the Winter 10K on 13 December "
                "2026. Two crate counts, one opening time and one lead's name spelling disagree.")
    plan = case.add(Paper("aid_station_plan.pdf"))
    chat = case.add(Chat("whatsapp_station_leads.txt"))
    event = case.entity("Winter 10K (13 Dec 2026)", "event")
    title = plan.para("Hyderabad Runners Winter 10K, 13 December 2026: Aid Station Plan")
    case.mention(event, "Winter 10K", title)
    stations = [
        (1, "Hitech City Junction", "Manoj Tiwari", 12, "05:00"),
        (2, "Cyber Towers", "Shalini Gupta", 10, "05:00"),
        (3, "Mindspace Circle", "Abdul Rahman", 14, "05:15"),
        (4, "Inorbit Mall Road", "Gayatri Menon", 10, "05:15"),
        (5, "Durgam Cheruvu Bridge", "Prakash Rao", 12, "05:30"),
        (6, "Shilparamam Finish Line", "Rekha Pillai", 16, "05:30"),
    ]
    paras = {}
    for n, place, lead, crates, opens in stations:
        station = case.entity(f"Aid Station {n} ({place})", "location")
        case.entity(lead, "person")
        hour, minute = opens.split(":")
        paras[n] = plan.para(f"Aid Station {n} ({place}): lead {lead}, {crates} water crates, opens at "
                             f"{int(hour)}:{minute} AM.")
        case.mention(station, f"Aid Station {n} ({place})", paras[n])
        case.mention(lead, lead, paras[n])
    plan.para("Station leads confirm crate counts in the WhatsApp group by 12 December, 8 PM.")

    m1 = chat.msg("12/12/2026, 18:05", "Manoj T", "AS1 is sorted, we have 12 crates at Hitech City Junction.")
    m2 = chat.msg("12/12/2026, 18:20", "Shalini Gupta", "Collected 8 crates for station 2, that's all the van had.")
    m3 = chat.msg("12/12/2026, 18:42", "Abdul R", "Station 3 will open at 5:30, our volunteers arrive late.")
    m4 = chat.msg("12/12/2026, 19:10", "Gayatri", "AS4 has 10 crates, all good.")
    m5 = chat.msg("12/12/2026, 19:35", "Prakash Rao", "Station 5 has 15 crates ready.")
    m6 = chat.msg("12/12/2026, 20:02", "Rekha Pilai", "Finish line station is ready with 16 crates.")
    case.mention("Manoj Tiwari", "Manoj T", m1)
    case.mention("Aid Station 1 (Hitech City Junction)", "AS1", m1)
    case.mention("Shalini Gupta", "Shalini Gupta", m2)
    case.mention("Aid Station 2 (Cyber Towers)", "station 2", m2)
    case.mention("Abdul Rahman", "Abdul R", m3)
    case.mention("Aid Station 3 (Mindspace Circle)", "Station 3", m3)
    case.mention("Gayatri Menon", "Gayatri", m4)
    case.mention("Aid Station 4 (Inorbit Mall Road)", "AS4", m4)
    case.mention("Prakash Rao", "Prakash Rao", m5)
    case.mention("Aid Station 5 (Durgam Cheruvu Bridge)", "Station 5", m5)
    case.mention("Rekha Pillai", "Rekha Pilai", m6)

    case.conflict("Aid Station 2 (Cyber Towers)", "water_crates", [
        ("10", ["10 water crates"], [paras[2]]), ("8", ["8 crates"], [m2])],
        "high", "Station 2 is two crates short of the plan.")
    case.conflict("Aid Station 3 (Mindspace Circle)", "opening_time", [
        ("05:15", ["5:15"], [paras[3]]), ("05:30", ["5:30"], [m3])],
        "high", "Station 3 opens 15 minutes later than planned.")
    case.conflict("Aid Station 5 (Durgam Cheruvu Bridge)", "water_crates", [
        ("12", ["12 water crates"], [paras[5]]), ("15", ["15 crates"], [m5])],
        "low", "Station 5 has more crates than planned.")
    case.conflict("Rekha Pillai", "full_name", [
        ("Rekha Pillai", ["rekha pillai"], [paras[6]]), ("Rekha Pilai", ["rekha pilai"], [m6])],
        "low", "Misspelled WhatsApp contact name.")
    return case


# ----------------------------------------------------------------------------- main


def main() -> None:
    people = People(SEED)
    cases = [case_04(people), case_05(people), case_06(people), case_07(people)]
    for case in cases:
        case.write()
        print(f"{case.case_id}: {len(case.docs) + len(case.extra_files)} files, "
              f"{len(case.gold['entities'])} entities, {len(case.gold['conflicts'])} conflicts")
    tmp = SYN / ".who_excerpt_tmp.pdf"
    tmp.unlink(missing_ok=True)

    # mark the Sprint 2 cases as build data
    for case_id in SPLIT["build"][:3]:
        path = SYN / case_id / "gold.json"
        gold = json.loads(path.read_text())
        if gold.get("split") != "build":
            gold = {"case_id": gold["case_id"], "description": gold["description"], "split": "build",
                    **{k: v for k, v in gold.items() if k not in ("case_id", "description", "split")}}
            path.write_text(json.dumps(gold, indent=2, ensure_ascii=False) + "\n")
    (SYN.parent / "split.json").write_text(json.dumps(SPLIT, indent=2) + "\n")


if __name__ == "__main__":
    main()
