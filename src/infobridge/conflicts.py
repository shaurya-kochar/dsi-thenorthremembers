"""Component 5b — Conflict Detector (issue #6, task C).

Deterministic, not LLM-based, so precision and recall are measurable against the
planted conflicts in ``gold.json["conflicts"]``:
  1. Every fact is mapped to its resolved entity through the mention it was written with.
  2. Facts are grouped by (entity, attribute). A group with more than one distinct
     *normalised* value is a conflict, listing each value with the chunks that state it.
     Mentions are names, not values, and attributes that legitimately hold several
     values (a person's results, roles, shifts) are skipped.
  3. A person written with two different full spellings ("Bhargavi" / "Bhargvi Kulkarni")
     is a ``full_name`` conflict. Forms that differ only by initials, honorifics or a
     dropped middle name are ways of writing a name, not disagreements.

Severity is a fixed rule by attribute, since the detector does not know which rule a
question depends on: event logistics that send people to the wrong place or time are
high; other dates, counts and statuses are medium; contact details, spellings and
station assignments are low.

The suggestion says which value to prefer: the official document for programme facts,
otherwise the most recent dated message, and for spellings the form most sources use.
Only chats and e-mails carry the date they were written; a PDF or sheet row is tagged
with the date it talks about, so it never counts as "more recent".
"""

from __future__ import annotations

import re
from collections import defaultdict

from .aliases import HONORIFICS, NAME_PREFIXES
from .models import Chunk, Conflict, ConflictValue, Entity, Fact
from .resolution import is_full, name_tokens
from .schema import entity_type_of

# a person can have several of these at once, so two values are not a disagreement
MULTI_VALUED = {"mention", "event_result", "training_attendance", "programme", "role", "shift"}

HIGH = {"start_time", "meeting_point", "event_date", "opening_time", "water_crates"}
MEDIUM = {"volunteer_count", "volunteers_present", "distance_km", "signup_status", "attended", "lead_volunteer"}


def severity_of(attribute: str) -> str:
    if attribute in HIGH:
        return "high"
    if attribute in MEDIUM or attribute.endswith("_date"):
        return "medium"
    return "low"


def _chunk_order(chunk_id: str) -> tuple:
    """Document order: file, then the numbers in the locator (row=10 after row=9)."""
    doc, _, locator = chunk_id.partition("#")
    return doc, [int(n) for n in re.findall(r"\d+", locator)]


def _is_table(chunk_id: str) -> bool:
    return chunk_id.partition("#")[2].startswith("row=")


def _is_official(chunk_id: str) -> bool:
    return chunk_id.partition("#")[2].startswith("page=")  # a PDF: plans, rules


def _written_on(chunk_id: str, chunks: dict[str, Chunk] | None) -> str | None:
    """Date a chat message or e-mail was written. PDFs, sheet rows and plain text are tagged
    with a date they mention, which says nothing about how recent the source is."""
    chunk = (chunks or {}).get(chunk_id)
    if chunk is None or not (chunk.metadata.get("sender") or chunk.metadata.get("sent")):
        return None
    return chunk.metadata.get("date")


def _name_key(text: str) -> tuple[str, ...]:
    """Name words without honorifics and leading prefixes, case-folded."""
    words = [w for w in re.findall(r"[A-Za-z]+", text.lower()) if w not in HONORIFICS]
    return tuple(w for i, w in enumerate(words) if not (i == 0 and w in NAME_PREFIXES and len(words) > 2))


class ConflictDetector:
    def detect(self, entities: list[Entity], facts: list[Fact],
               chunks: dict[str, Chunk] | None = None) -> list[Conflict]:
        """``chunks`` (chunk_id -> Chunk) is optional; it gives message dates for the suggestion."""
        index: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)  # (mention, chunk) -> {type: entity}
        types, names = {}, {}
        for e in entities:
            types[e.entity_id], names[e.entity_id] = e.entity_type, e.canonical_name
            for m in e.mentions:
                index[(m.text, m.chunk_id)][e.entity_type] = e.entity_id

        def entity_of(f: Fact) -> str | None:
            candidates = index.get((f.entity_mention, f.chunk_id), {})
            etype = f.entity_type or entity_type_of(f.attribute)
            if etype in candidates:
                return candidates[etype]
            return next(iter(candidates.values())) if len(candidates) == 1 else None

        groups: dict[tuple[str, str], dict[str, list[Fact]]] = defaultdict(lambda: defaultdict(list))
        for f in facts:
            if f.attribute in MULTI_VALUED or f.attribute == "full_name" or not f.value:
                continue
            if (entity_id := entity_of(f)) is not None:
                groups[(entity_id, f.attribute)][f.value].append(f)

        found = []
        for (entity_id, attribute), by_value in groups.items():
            if len(by_value) > 1:
                values = [self._value(value, fs) for value, fs in by_value.items()]
                found.append((entity_id, attribute, values))
        for e in entities:
            if e.entity_type == "person" and (values := self._spellings(e)):
                found.append((e.entity_id, "full_name", values))

        conflicts = []
        for n, (entity_id, attribute, values) in enumerate(sorted(found, key=lambda x: (x[0], x[1])), start=1):
            values.sort(key=lambda v: _chunk_order(v.chunk_id))
            conflicts.append(Conflict(
                conflict_id=f"C{n}", entity_id=entity_id, entity_name=names.get(entity_id, ""), attribute=attribute,
                values=values,
                severity=severity_of(attribute),
                suggestion=self._suggest(attribute, types.get(entity_id), values, chunks)))
        return conflicts

    @staticmethod
    def _value(value: str, facts: list[Fact]) -> ConflictValue:
        """One entry per distinct value; the sheet row (the record) represents it when there is one."""
        facts = sorted(facts, key=lambda f: (not _is_table(f.chunk_id), _chunk_order(f.chunk_id)))
        sources = list(dict.fromkeys(f.chunk_id for f in facts))
        return ConflictValue(value=value, raw_value=facts[0].raw_value, chunk_id=sources[0], sources=sources)

    @staticmethod
    def _spellings(entity: Entity) -> list[ConflictValue]:
        """Different full spellings of one person's name (same number of words, no initials)."""
        by_key: dict[tuple[str, ...], list] = defaultdict(list)
        for m in entity.mentions:
            key = _name_key(m.text)
            if is_full(name_tokens(m.text)) and all(len(w) > 1 for w in key) and len(key) >= 2:
                by_key[key].append(m)
        lengths = {len(k) for k in by_key}
        if len(by_key) < 2 or len(lengths) != 1:
            return []  # one spelling, or a short and a long form of the same name
        values = []
        for mentions in by_key.values():
            mentions.sort(key=lambda m: (not _is_table(m.chunk_id), _chunk_order(m.chunk_id)))
            text = re.sub(r"\s+", " ", mentions[0].text).strip()
            sources = list(dict.fromkeys(m.chunk_id for m in mentions))
            values.append(ConflictValue(value=text, raw_value=text, chunk_id=sources[0], sources=sources))
        return values

    @staticmethod
    def _suggest(attribute: str, entity_type: str | None, values: list[ConflictValue],
                 chunks: dict[str, Chunk] | None) -> str:
        if attribute == "full_name":
            best = max(values, key=lambda v: (len({s.split("#")[0] for s in v.sources}),
                                              any(_is_table(s) or _is_official(s) for s in v.sources)))
            docs = ", ".join(dict.fromkeys(s.split("#")[0] for s in best.sources))
            return f"prefer the spelling most sources use ('{best.value}' in {docs})"
        if entity_type == "programme":
            official = [v for v in values if any(_is_official(s) for s in v.sources)]
            if len(official) == 1:
                doc = next(s for s in official[0].sources if _is_official(s)).split("#")[0]
                return f"prefer the official document ({doc}: {official[0].raw_value})"
        dated = [(d, s, v) for v in values for s in v.sources if (d := _written_on(s, chunks))]
        if dated:
            date, source, value = max(dated, key=lambda x: x[0])
            return f"prefer the most recent source ({source.split('#')[0]}, {date}: {value.raw_value})"
        official = [v for v in values if any(_is_official(s) for s in v.sources)]
        if len(official) == 1:
            doc = next(s for s in official[0].sources if _is_official(s)).split("#")[0]
            return f"prefer the official document ({doc}: {official[0].raw_value})"
        return "no source is clearly newer or more official; check with the coordinator"
