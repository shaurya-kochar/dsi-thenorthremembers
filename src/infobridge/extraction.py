"""Component 2 — Information Extractor.

Turns chunks into ``Fact`` objects, each tagged with the chunk it came from.

Built in issue #2:
  * Spreadsheet rows: columns map to attributes through ``schema.TABLE_SCHEMAS``
    (no ML, confidence 1.0, ``extractor="csv_schema"``). Values are normalised.
  * Mentions: a rule-based name finder tags every person, event, programme and
    place named in chat, PDF and e-mail text (``attribute="mention"``), and every
    WhatsApp sender. Entity resolution works on these mentions.
Added in issue #4: LLM extraction of attribute values from chat / PDF / e-mail text
(``text_extractor``), which plugs in below without changing this interface.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

from .aliases import HONORIFICS, NAME_PREFIXES, NICKNAMES, ORG_NAMES, PROGRAMME_ACRONYMS, SPELLINGS
from .models import Chunk, Fact
from .normalise import normalise_value
from .schema import TABLE_SCHEMAS

MENTION = "mention"


def fact_id(chunk_id: str, mention: str, attribute: str, value: str) -> str:
    return "F-" + hashlib.sha1(f"{chunk_id}|{mention}|{attribute}|{value}".encode()).hexdigest()[:10]


def mention_fact(text: str, chunk_id: str, entity_type: str, extractor: str, confidence: float = 0.8) -> Fact:
    return Fact(fact_id=fact_id(chunk_id, text, MENTION, ""), entity_mention=text, attribute=MENTION, value="",
                raw_value=text, chunk_id=chunk_id, extractor=extractor, confidence=confidence,
                entity_type=entity_type)


# ------------------------------------------------------------------ tables


def table_facts(chunk: Chunk) -> list[Fact]:
    schema = TABLE_SCHEMAS.get(chunk.doc_id)
    row = chunk.metadata.get("row")
    if schema is None or not isinstance(row, dict):
        return []
    year = int(chunk.metadata["date"][:4]) if chunk.metadata.get("date") else None
    entity = row.get(schema.entity_column, "").strip()
    facts = []
    for column, attribute in schema.columns.items():
        raw = row.get(column, "").strip()
        if not raw:
            continue
        mention, etype = entity, schema.entity_type
        if column in schema.about_other_entity:
            other_column, etype = schema.about_other_entity[column]
            mention = row.get(other_column, "").strip()
        if not mention:
            continue
        value = normalise_value(attribute, raw, year)
        facts.append(Fact(fact_id=fact_id(chunk.chunk_id, mention, attribute, value), entity_mention=mention,
                          attribute=attribute, value=value, raw_value=raw, chunk_id=chunk.chunk_id,
                          extractor="csv_schema", confidence=1.0, entity_type=etype))
    for column, etype in schema.mention_columns.items():
        if value := row.get(column, "").strip():
            facts.append(mention_fact(value, chunk.chunk_id, etype, "csv_schema", 1.0))
    if entity:
        facts.append(mention_fact(entity, chunk.chunk_id, schema.entity_type, "csv_schema", 1.0))
    return facts


# ------------------------------------------------------------- name finder

INITIAL = r"[A-Z]\.?"
HONORIFIC_TAIL = r"(?:\s+(?:" + "|".join(sorted(HONORIFICS, key=len, reverse=True)) + r")\b)?"
EVENT = re.compile(r"\b(?:(?:[A-Z][\w'-]*|\d+K)\s+){1,4}(?:Run|Marathon|Walk|Ride|\d+K)\b"
                   r"(?:\s+\((?:\d{1,2}\s+[A-Z][a-z]{2}|[A-Z][a-z]{2}\s+\d{1,2})\))?")
STATION = re.compile(r"\bAid Station \d+(?: \([^)]+\))?|\b[Ss]tation \d+\b|\bAS\d+\b")
# a full name right after a cue word: "lead Manoj Tiwari", "led by Priyanka Sen"
NAME_CUE = re.compile(r"\b(?:lead|led by|co-lead|coordinator|by|thanks)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
BATCH = re.compile(r"\bbatch\s+(?:\d{4})?[A-Z]\b", re.IGNORECASE)


def _programme_patterns() -> list[re.Pattern]:
    patterns = []
    for acronym, long_form in PROGRAMME_ACRONYMS.items():
        patterns.append(re.compile(rf"\b{long_form}\s*\({acronym}\),?\s*batch\s+\d{{4}}[A-Z]\b", re.IGNORECASE))
        patterns.append(re.compile(rf"\b{acronym}\s+(?:batch\s+)?\d{{4}}[A-Z]\b", re.IGNORECASE))
    return patterns


def _alternatives(token: str) -> set[str]:
    """Spellings and nicknames of one name token (lower-case)."""
    alts = {token}
    alts |= {v for k, v in SPELLINGS.items() if k == token} | {k for k, v in SPELLINGS.items() if v == token}
    alts |= {k for k, v in NICKNAMES.items() if v == token}
    return alts


def _cap(word: str) -> str:
    return word[:1].upper() + word[1:]


def person_patterns(full_name: str) -> list[str]:
    """Regexes for the ways a person's name is written: full, initials, first name + initial,
    first name alone, nicknames and spelling variants."""
    tokens = full_name.split()
    calling = [t for t in tokens if t.lower() not in NAME_PREFIXES] or tokens
    first, last = calling[0], calling[-1] if len(calling) > 1 else None
    firsts = "|".join(sorted({_cap(a) for a in _alternatives(first.lower())} | {first}, key=len, reverse=True))
    out = [re.escape(full_name)]
    if last:
        middles = calling[1:-1]
        initials = r"\s?".join(f"{t[0]}\\." for t in [first] + middles)
        out += [rf"(?:{firsts})\s+{re.escape(last)}",  # Lakshmi Prasad / Laxmi Prasad
                rf"{initials}\s?{re.escape(last)}",  # S. R. Kumar, R. Sharma
                rf"{first[0]}\.\s{re.escape(last)}",  # A. Iyer
                rf"(?:{firsts})\s+{last[0]}\b\.?"]  # Ravi S., Sneha N
    out.append(rf"(?:{firsts})")  # first name alone
    return out


class NameFinder:
    """Finds mentions of known people / events / places / programmes in free text.

    The lexicon comes from the spreadsheets (names in entity columns and mention
    columns) plus generic patterns for events, aid stations and programme batches.
    """

    def __init__(self, chunks: list[Chunk]):
        people, places, events, surnames = set(), set(), set(), {}
        for chunk in chunks:
            schema = TABLE_SCHEMAS.get(chunk.doc_id)
            row = chunk.metadata.get("row")
            if schema is None or not isinstance(row, dict):
                continue
            named = {schema.entity_column: schema.entity_type, **schema.mention_columns}
            for column, etype in named.items():
                value = row.get(column, "").strip()
                if not value:
                    continue
                {"person": people, "location": places, "event": events}.get(etype, set()).add(value)
        for chunk in chunks:  # people who appear only in text: chat senders and names after a cue word
            sender = chunk.metadata.get("sender", "")
            words = [w for w in sender.split() if w.lower().strip(".") not in HONORIFICS]
            if len(words) >= 2 and all(w[:1].isupper() and len(w.strip(".")) > 1 for w in words):
                people.add(" ".join(words))
            if not isinstance(chunk.metadata.get("row"), dict):
                people.update(m[1] for m in NAME_CUE.finditer(chunk.text) if m[1].lower() not in ORG_NAMES)
        self.rules: list[tuple[re.Pattern, str]] = []
        for name in sorted(people):
            for pattern in person_patterns(name):
                self.rules.append((re.compile(rf"(?<![\w.]){pattern}(?![\w]){HONORIFIC_TAIL}"), "person"))
            parts = name.split()
            if len(parts) > 1:
                surnames.setdefault(parts[-1], set()).add(parts[0].lower())
        self.surnames = surnames
        for place in sorted(places):
            core = re.sub(r"\s*\([^)]*\)", "", place).strip()
            variants = {place, core}
            if m := re.fullmatch(r"(.*?)\s*(\d+)", core):
                words = m[1].split()
                variants.add("".join(w[0] for w in words).upper() + m[2])  # Aid Station 3 -> AS3
            for v in variants:
                self.rules.append((re.compile(rf"\b{re.escape(v)}(?!\w)", re.IGNORECASE), "location"))
        for event in sorted(events):
            self.rules.append((re.compile(rf"\b{re.escape(event)}\b"), "event"))
        self.rules += [(EVENT, "event"), (STATION, "location"), (BATCH, "programme")]
        self.rules += [(p, "programme") for p in _programme_patterns()]

    def _misspelled(self, text: str) -> list[tuple[int, int, str]]:
        """'Bhargvi Kulkarni': an unknown first name close to a known one, before a known surname."""
        from rapidfuzz.distance import JaroWinkler

        spans = []
        for surname, firsts in self.surnames.items():
            for m in re.finditer(rf"\b([A-Z][a-z]{{2,}})\s+{re.escape(surname)}\b", text):
                word = m[1].lower()
                if word not in firsts and any(JaroWinkler.similarity(word, f) >= 0.9 for f in firsts):
                    spans.append((m.start(), m.end(), "person"))
        return spans

    def find(self, text: str) -> list[tuple[str, str]]:
        """Non-overlapping (surface text, entity type) mentions; longer matches win."""
        spans = [(m.start(), m.end(), etype) for rule, etype in self.rules for m in rule.finditer(text)]
        spans += self._misspelled(text)
        spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
        taken, found = [], []
        for start, end, etype in spans:
            if any(start < e and s < end for s, e in taken):
                continue
            surface = _strip_org(text[start:end])
            if not surface:
                continue
            taken.append((start, end))
            found.append((start, surface, etype))
        return [(surface, etype) for _, surface, etype in sorted(found)]


def _strip_org(surface: str) -> str:
    """'Hyderabad Runners Winter 10K' -> 'Winter 10K' (the organisation is not part of the event name)."""
    for org in ORG_NAMES:
        if surface.lower().startswith(org + " "):
            return surface[len(org) + 1:]
    return surface


# --------------------------------------------------------------- extractor


class InformationExtractor:
    """``extract(chunks)`` -> facts from tables, plus mentions found in text.

    ``text_extractor`` (issue #4) can add attribute facts for chat / PDF / e-mail
    chunks; it receives the chunks and returns facts.
    """

    def __init__(self, text_extractor: Callable[[list[Chunk]], list[Fact]] | None = None):
        self.text_extractor = text_extractor

    def extract(self, chunks: list[Chunk]) -> list[Fact]:
        finder = NameFinder(chunks)
        facts: list[Fact] = []
        text_chunks = []
        for chunk in chunks:
            if chunk.doc_id in TABLE_SCHEMAS and isinstance(chunk.metadata.get("row"), dict):
                facts += table_facts(chunk)
                continue
            if isinstance(chunk.metadata.get("row"), dict):
                continue  # a sheet without a schema (e.g. public data): no people in it
            text_chunks.append(chunk)
            if sender := chunk.metadata.get("sender"):
                facts.append(mention_fact(sender, chunk.chunk_id, "person", "chat_sender", 0.9))
            for surface, etype in finder.find(chunk.text):
                facts.append(mention_fact(surface, chunk.chunk_id, etype, "name_finder"))
        if self.text_extractor:
            facts += self.text_extractor(text_chunks)
        unique = {}
        for f in facts:
            unique.setdefault((f.entity_mention, f.attribute, f.value, f.chunk_id), f)
        return list(unique.values())
