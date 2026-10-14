"""Shared vocabulary for facts: attribute names and spreadsheet column mappings.

Every component that produces or compares facts (extractor, entity resolver,
conflict detector) uses these names, so a value from a spreadsheet column and
the same value mentioned in a WhatsApp message end up under one attribute.

For the PoC the table mappings are keyed by file name. In a real deployment
they would be configured once per sheet when a source is connected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# attribute name -> description (also given to the LLM extractor as its allowed list)
ATTRIBUTES: dict[str, str] = {
    # identity (strong keys for entity resolution)
    "phone": "phone number, normalised to the last 10 digits",
    "email": "email address, lower-case",
    "member_id": "Hyderabad Runners membership id, e.g. HR-0457",
    "volunteer_id": "volunteer id, e.g. V-114",
    # membership
    "membership_status": "Active / Lapsed",
    "membership_valid_until": "date the membership expires (YYYY-MM-DD)",
    "joined_on": "date the person joined (YYYY-MM-DD)",
    "medical_clearance_date": "date of the person's medical clearance (YYYY-MM-DD)",
    # programmes and registrations
    "programme": "training programme the person registered for, e.g. HMTP 2026B",
    "category": "programme category, e.g. Beginner / Intermediate",
    "registered_on": "date the registration was submitted (YYYY-MM-DD)",
    "payment_status": "Paid / Pending",
    "batch_start_date": "date a programme batch starts (YYYY-MM-DD); a fact about the programme",
    "registration_deadline": "last date to register for a programme (YYYY-MM-DD); a fact about the programme",
    # running record
    "event_result": "a race result, e.g. 'HR 10K Monsoon Run: 52:30'",
    "training_attendance": "training sessions attended, e.g. '6 of 7'",
    # volunteering
    "assigned_station": "aid station or post the volunteer is assigned to",
    "shift": "volunteer shift, e.g. 05:00-09:00",
    "role": "volunteer role, e.g. Station Lead",
    "first_aid_certified": "yes / no",
    "first_aid_certificate_id": "first-aid certificate id, e.g. FA-2026-031",
    # events
    "event_name": "name of the event",
    "event_date": "date of the event (YYYY-MM-DD)",
    "start_time": "start / flag-off time (HH:MM, 24h)",
    "meeting_point": "where participants gather",
    "distance_km": "distance in km",
    "lead_volunteer": "volunteer leading the event",
    "event_status": "Scheduled / Completed / Cancelled",
    "route": "route description",
    "water_stations": "water station locations",
    "briefing_time": "volunteer briefing time (HH:MM, 24h)",
    "event_id": "event id, e.g. EV-2026-043",
    "end_time": "time the event finished (HH:MM, 24h)",
    "volunteer_count": "number of volunteers confirmed for an event",
    "volunteers_present": "number of volunteers who turned up at an event",
    # people at an event
    "full_name": "the person's full name as written in a sheet or document",
    "signup_status": "Confirmed / Tentative / Withdrawn",
    "attended": "Present / Absent",
    "check_in_time": "time the volunteer checked in (HH:MM, 24h)",
    # aid stations
    "water_crates": "number of water crates at an aid station",
    "opening_time": "time an aid station opens (HH:MM, 24h)",
    # not a value: the entity is named in this chunk (used by entity resolution, ignored by conflicts)
    "mention": "the entity is mentioned in this chunk",
}

# Attributes that describe a programme or an event rather than a person; used to infer
# the entity type of a fact whose extractor did not set one.
PROGRAMME_ATTRIBUTES = {"batch_start_date", "registration_deadline"}
EVENT_ATTRIBUTES = {"event_name", "event_date", "start_time", "meeting_point", "distance_km", "lead_volunteer",
                    "event_status", "route", "water_stations", "briefing_time", "event_id", "end_time",
                    "volunteer_count", "volunteers_present"}
LOCATION_ATTRIBUTES = {"water_crates", "opening_time"}


def entity_type_of(attribute: str) -> str:
    if attribute in PROGRAMME_ATTRIBUTES:
        return "programme"
    if attribute in EVENT_ATTRIBUTES:
        return "event"
    if attribute in LOCATION_ATTRIBUTES:
        return "location"
    return "person"


@dataclass(frozen=True)
class TableSchema:
    """How one spreadsheet's rows become facts."""

    entity_column: str  # column naming the entity each row is about
    entity_type: str  # "person" | "event" | ...
    columns: dict[str, str]  # column -> attribute
    # columns whose fact is about a *different* entity named in another column,
    # e.g. registrations.batch_start describes the programme, not the participant
    about_other_entity: dict[str, tuple[str, str]] = field(default_factory=dict)  # column -> (entity column, entity type)
    # columns whose value names another entity (a mention, not an attribute of the row's entity)
    mention_columns: dict[str, str] = field(default_factory=dict)  # column -> entity type


TABLE_SCHEMAS: dict[str, TableSchema] = {
    "members.csv": TableSchema(
        entity_column="name",
        entity_type="person",
        columns={
            "member_id": "member_id", "phone": "phone", "email": "email",
            "membership_status": "membership_status", "membership_valid_until": "membership_valid_until",
            "medical_clearance_date": "medical_clearance_date", "joined_on": "joined_on",
        },
    ),
    "registrations.csv": TableSchema(
        entity_column="participant_name",
        entity_type="person",
        columns={
            "phone": "phone", "programme": "programme", "category": "category",
            "registered_on": "registered_on", "payment_status": "payment_status",
            "batch_start": "batch_start_date",
        },
        about_other_entity={"batch_start": ("programme", "programme")},
        mention_columns={"programme": "programme"},
    ),
    "volunteer_roster.xlsx": TableSchema(
        entity_column="full_name",
        entity_type="person",
        columns={
            "vol_id": "volunteer_id", "phone": "phone", "assigned_station": "assigned_station",
            "shift": "shift", "role": "role",
        },
        mention_columns={"assigned_station": "location"},
    ),
    "events.csv": TableSchema(
        entity_column="event_name",
        entity_type="event",
        columns={
            "event_id": "event_id", "date": "event_date", "start_time": "start_time",
            "meeting_point": "meeting_point", "distance_km": "distance_km",
            "lead_volunteer": "lead_volunteer", "status": "event_status",
        },
        mention_columns={"lead_volunteer": "person", "meeting_point": "location"},
    ),
    "events_q4.csv": TableSchema(
        entity_column="event_name",
        entity_type="event",
        columns={
            "event_id": "event_id", "date": "event_date", "start_time": "start_time",
            "meeting_point": "meeting_point", "distance_km": "distance_km",
            "lead_volunteer": "lead_volunteer", "status": "event_status",
        },
        mention_columns={"lead_volunteer": "person", "meeting_point": "location"},
    ),
    "volunteer_signups.xlsx": TableSchema(
        entity_column="full_name",
        entity_type="person",
        columns={
            "vol_id": "volunteer_id", "full_name": "full_name", "phone": "phone", "email": "email",
            "role": "role", "signup_status": "signup_status", "shift": "shift",
        },
    ),
    "attendance_log.csv": TableSchema(
        entity_column="volunteer_name",
        entity_type="person",
        columns={
            "vol_id": "volunteer_id", "volunteer_name": "full_name", "phone": "phone",
            "station": "assigned_station", "status": "attended", "check_in_time": "check_in_time",
        },
    ),
}
