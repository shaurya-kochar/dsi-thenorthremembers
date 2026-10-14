"""Component 3 — Entity Resolver.

Clusters mentions that refer to the same real-world entity:
    "Ravi Sharma" (members.csv) = "R. Sharma" (registrations.csv) = "Ravi S." (WhatsApp)
while keeping look-alikes apart:
    "Ravi Shankar" != "Ravi Sharma",   "Srinivas Reddy" != "Srinivas Rao Kumar"

People, in this order:
  1. Strong keys: the same normalised phone / email / member or volunteer id -> same person.
  2. Full names that are compatible: same tokens after the alias table (spellings, nicknames,
     honorifics), initials ("S. R. Kumar" ~ "Srinivas Rao Kumar"), close spellings
     (Jaro-Winkler); two different full surnames never merge.
  3. Short forms ("Ravi S.", "Srini", "Kavya") join the one compatible person. If several are
     compatible: drop candidates named in full in the same document (the writer would have used
     that form), then prefer the candidate that shares the most co-mentioned entities. If it is
     still a tie, the mention stays on its own.
Events, places and programmes: names compared after removing qualifiers, by rapidfuzz plus an
embedding similarity (all-MiniLM-L6-v2 via Chroma's ONNX runtime) for near-misses; programme
batches by their batch code ("HMTP 2026B" ~ "Batch 2026B" ~ "batch B").
Two rows of the same sheet are different records and never merge on their name alone.
Every merge records why in ``Entity.match_evidence``. Scored with pairwise F1
(``evaluation.entity_resolution_f1``).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from .aliases import HONORIFICS, NAME_PREFIXES, NICKNAMES, ORG_NAMES, PROGRAMME_ACRONYMS, SPELLINGS
from .models import Entity, Fact, Mention
from .schema import entity_type_of

STRONG_KEYS = ("phone", "email", "member_id", "volunteer_id")


# --------------------------------------------------------------- names


def name_tokens(name: str) -> list[str]:
    """'Farhan bhai' -> ['farhan'];  'S. R. Kumar' -> ['s', 'r', 'kumar'];  'Laxmi' -> ['lakshmi']."""
    words = re.findall(r"[A-Za-z]+", name.lower())
    words = [w for w in words if w not in HONORIFICS]
    return [NICKNAMES.get(w, SPELLINGS.get(w, w)) for w in words]


def _calling(tokens: list[str]) -> list[str]:
    """Tokens without leading name prefixes: ['mohammed', 'farhan'] -> ['farhan']."""
    return [t for t in tokens if t not in NAME_PREFIXES] or tokens


def _token_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]  # initial
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True  # prefix nickname
    return min(len(a), len(b)) >= 5 and Levenshtein.distance(a, b) <= 1  # one-letter typo


def is_full(tokens: list[str]) -> bool:
    """A full name: at least two tokens and a full (not initial) surname."""
    return len(tokens) >= 2 and len(tokens[-1]) > 1


def names_compatible(a: list[str], b: list[str]) -> bool:
    if not a or not b:
        return False
    if is_full(a) and is_full(b) and is_full(_calling(a)) == is_full(_calling(b)):
        if not _token_match(a[-1], b[-1]) or len(a[-1]) == 1 or len(b[-1]) == 1:
            return False  # different surnames never merge
        if not _token_match(a[0], b[0]):
            return False
        middle_a, middle_b = a[1:-1], b[1:-1]
        return all(_token_match(x, y) for x, y in zip(middle_a, middle_b))
    short, long_ = (a, b) if len(_calling(a)) <= len(_calling(b)) else (b, a)
    short, long_ = _calling(short), _calling(long_)
    if not _token_match(short[0], long_[0]):
        return False
    if len(short) == 1:
        return len(short[0]) > 1  # a first name alone
    return _token_match(short[-1], long_[-1])  # 'Ravi S.' ~ 'Ravi Sharma'


def _strip_qualifiers(name: str) -> str:
    name = re.sub(r"\s*\([^)]*\)", "", name).strip().lower()
    for org in ORG_NAMES:
        if name.startswith(org + " "):
            name = name[len(org) + 1:]
    return name


def _acronym(name: str) -> str:
    m = re.fullmatch(r"(.*?)\s*(\d+)", name)
    return ("".join(w[0] for w in m[1].split()) + m[2]).lower() if m else ""


def _batch_code(name: str) -> tuple[str | None, str | None, str | None]:
    """'HMTP 2026B' -> ('hmtp', '2026', 'b');  'batch B' -> (None, None, 'b')."""
    low = name.lower()
    acronym = next((a for a, long_form in PROGRAMME_ACRONYMS.items() if a in low or long_form in low), None)
    m = re.search(r"(?:^|\s)(\d{4})?([a-z])$", low.strip())
    return acronym, (m[1] if m else None), (m[2] if m else None)


class _Embedder:
    """Lazy MiniLM name embeddings (the model the vector store already uses)."""

    def __init__(self):
        self._fn, self._cache = None, {}

    def similarity(self, a: str, b: str) -> float:
        try:
            if self._fn is None:
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

                self._fn = DefaultEmbeddingFunction()
            missing = [t for t in (a, b) if t not in self._cache]
            if missing:
                for text, vec in zip(missing, self._fn(missing)):
                    self._cache[text] = vec
            va, vb = self._cache[a], self._cache[b]
            dot = sum(x * y for x, y in zip(va, vb))
            norm = (sum(x * x for x in va) ** 0.5) * (sum(y * y for y in vb) ** 0.5)
            return dot / norm if norm else 0.0
        except Exception:
            return 0.0


def other_names_compatible(a: str, b: str, etype: str, embedder: _Embedder) -> str | None:
    """Reason the two event / place / programme names match, or None."""
    if etype == "programme":
        (aa, ya, la), (ab, yb, lb) = _batch_code(a), _batch_code(b)
        if la and la == lb and (not ya or not yb or ya == yb) and (not aa or not ab or aa == ab):
            return f"same batch code ({la.upper()})"
        return None
    na, nb = _strip_qualifiers(a), _strip_qualifiers(b)
    if na == nb:
        return "same name"
    numbers_a, numbers_b = re.findall(r"\d+", na), re.findall(r"\d+", nb)
    if numbers_a and numbers_b and numbers_a != numbers_b:
        return None  # 'Aid Station 1' vs 'Aid Station 2'
    if etype == "location" and (na == _acronym(nb) or nb == _acronym(na)):
        return "abbreviation"
    if etype == "location" and numbers_a and numbers_a == numbers_b and (
            re.search(r"station", na) or re.fullmatch(r"as\d+", na)) and (
            re.search(r"station", nb) or re.fullmatch(r"as\d+", nb)):
        return "same station number"
    if etype == "event" and min(len(na.split()), len(nb.split())) >= 2 and fuzz.token_set_ratio(na, nb) == 100:
        return "one name contains the other"
    ratio = fuzz.token_sort_ratio(na, nb)
    if ratio >= 92:
        return f"fuzzy={ratio:.0f}"
    if ratio >= 70 and (score := embedder.similarity(na, nb)) >= 0.9:
        return f"embedding={score:.2f}"
    return None


# ------------------------------------------------------------- resolver


@dataclass
class _Node:
    text: str
    chunk_id: str
    etype: str
    keys: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @property
    def doc(self) -> str:
        return self.chunk_id.split("#", 1)[0]

    @property
    def is_row(self) -> bool:
        return self.chunk_id.split("#", 1)[1].startswith("row=")


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.evidence: dict[int, list[str]] = defaultdict(list)

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int, why: str) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[rj] = ri
            self.evidence[ri] += self.evidence.pop(rj, []) + [why]


class EntityResolver:
    def __init__(self, use_embeddings: bool = True):
        self.embedder = _Embedder() if use_embeddings else None

    def resolve(self, facts: list[Fact]) -> list[Entity]:
        nodes, index = [], {}
        for f in facts:
            etype = f.entity_type or entity_type_of(f.attribute)
            key = (f.entity_mention, f.chunk_id, etype)
            if key not in index:
                index[key] = len(nodes)
                nodes.append(_Node(f.entity_mention, f.chunk_id, etype))
            if f.attribute in STRONG_KEYS and f.value:
                nodes[index[key]].keys[f.attribute].add(f.value.lower())
        uf = _UnionFind(len(nodes))
        self._resolve_other(nodes, uf)
        self._resolve_people(nodes, uf)
        return self._entities(nodes, uf)

    # ------------------------------------------------ events, places, programmes

    def _resolve_other(self, nodes: list[_Node], uf: _UnionFind) -> None:
        embedder = self.embedder or _Embedder.__new__(_Embedder)
        if self.embedder is None:
            embedder.similarity = lambda a, b: 0.0
        by_type = defaultdict(list)
        for i, n in enumerate(nodes):
            if n.etype != "person":
                by_type[n.etype].append(i)
        for etype, ids in by_type.items():
            for x, i in enumerate(ids):
                for j in ids[x + 1:]:
                    a, b = nodes[i], nodes[j]
                    if a.doc == b.doc and a.is_row and b.is_row and a.chunk_id != b.chunk_id:
                        continue  # two rows of one sheet are two records
                    if reason := other_names_compatible(a.text, b.text, etype, embedder):
                        uf.union(i, j, f"{a.text!r} ~ {b.text!r}: {reason}")

    # ------------------------------------------------------------------ people

    def _resolve_people(self, nodes: list[_Node], uf: _UnionFind) -> None:
        people = [i for i, n in enumerate(nodes) if n.etype == "person"]
        tokens = {i: name_tokens(nodes[i].text) for i in people}
        full = [i for i in people if is_full(tokens[i]) and all(len(t) > 1 for t in tokens[i])]
        initialled = [i for i in people if is_full(tokens[i]) and i not in full]
        short = [i for i in people if i not in full and i not in initialled]

        def full_names(root: int) -> list[int]:
            return [k for k in full if uf.find(k) == root]

        def members(root: int) -> list[int]:
            return [k for k in people if uf.find(k) == root]

        def different_ids(a: _Node, b: _Node) -> bool:
            """Two sheet records whose phone / e-mail / ids differ are two people."""
            if not (a.is_row and b.is_row):
                return False
            return any(a.keys.get(k) and b.keys.get(k) and not a.keys[k] & b.keys[k] for k in STRONG_KEYS)

        def can_join(i: int, j: int) -> bool:
            """Joining must not put two incompatible full names, or two different records, in one entity."""
            ri, rj = uf.find(i), uf.find(j)
            if not all(names_compatible(tokens[a], tokens[b]) for a in full_names(ri) for b in full_names(rj)):
                return False
            return not any(different_ids(nodes[a], nodes[b]) for a in members(ri) for b in members(rj))

        # 1. strong keys
        owners = defaultdict(list)
        for i in people:
            for attr, values in nodes[i].keys.items():
                for v in values:
                    owners[(attr, v)].append(i)
        for (attr, value), ids in owners.items():
            for j in ids[1:]:
                if can_join(ids[0], j):
                    uf.union(ids[0], j, f"same {attr} {value}")

        # 2. compatible full names
        for x, i in enumerate(full):
            for j in full[x + 1:]:
                a, b = nodes[i], nodes[j]
                if a.doc == b.doc and a.is_row and b.is_row and a.chunk_id != b.chunk_id:
                    continue
                if uf.find(i) != uf.find(j) and names_compatible(tokens[i], tokens[j]) and can_join(i, j):
                    same = tokens[i] == tokens[j]
                    uf.union(i, j, f"{a.text!r} ~ {b.text!r}: {'same name' if same else 'compatible names'}")

        # 3. initials and short forms join one compatible person
        for i in initialled:  # 'R. Sharma', 'S. R. Kumar'
            self._attach(i, nodes, tokens, full, uf)
        for i in short:  # same short form in the same document = same person
            for j in short:
                if i < j and nodes[i].doc == nodes[j].doc and tokens[i] == tokens[j]:
                    uf.union(i, j, f"{nodes[i].text!r} repeated in {nodes[i].doc}")
        for i in short:
            self._attach(i, nodes, tokens, full, uf)

    def _attach(self, i: int, nodes: list[_Node], tokens: dict, full: list[int], uf: _UnionFind) -> None:
        if any(uf.find(i) == uf.find(k) for k in full):
            return
        candidates = {uf.find(k) for k in full if names_compatible(tokens[i], tokens[k])}
        if not candidates:
            return
        note = "only compatible person"
        if len(candidates) > 1:
            # a person named in full in this document would have been named that way here too
            in_doc = {uf.find(k) for k in full if nodes[k].doc == nodes[i].doc}
            narrowed = candidates - in_doc
            if narrowed and len(narrowed) < len(candidates):
                candidates, note = narrowed, "other candidates are named in full in the same document"
        if len(candidates) > 1:
            scores = {c: self._shared_context(i, c, nodes, uf) for c in candidates}
            best = max(scores.values())
            winners = [c for c, s in scores.items() if s == best]
            if best == 0 or len(winners) > 1:
                return  # still ambiguous: keep apart rather than merge wrongly
            candidates, note = {winners[0]}, f"shares {best} co-mentioned entities"
        target = candidates.pop()
        uf.union(target, i, f"{nodes[i].text!r} -> {nodes[target].text!r}: {note}")

    @staticmethod
    def _shared_context(i: int, root: int, nodes: list[_Node], uf: _UnionFind) -> int:
        """Entities mentioned in i's document that also appear next to the candidate."""
        around_i = {uf.find(k) for k, n in enumerate(nodes) if n.doc == nodes[i].doc and k != i}
        candidate_chunks = {n.chunk_id for k, n in enumerate(nodes) if uf.find(k) == root}
        around_c = {uf.find(k) for k, n in enumerate(nodes) if n.chunk_id in candidate_chunks and uf.find(k) != root}
        return len((around_i - {root}) & around_c)

    # ------------------------------------------------------------------ output

    @staticmethod
    def _entities(nodes: list[_Node], uf: _UnionFind) -> list[Entity]:
        clusters = defaultdict(list)
        for i in range(len(nodes)):
            clusters[uf.find(i)].append(i)
        entities, used_ids = [], set()
        for root, ids in clusters.items():
            members = [nodes[i] for i in ids]
            etype = members[0].etype

            def rank(n: _Node) -> tuple:
                return (n.is_row, is_full(name_tokens(n.text)) if etype == "person" else True, len(n.text))

            canonical = max(members, key=rank).text
            slug = re.sub(r"[^a-z0-9]+", "-", canonical.lower()).strip("-")
            entity_id, k = f"{etype}:{slug}", 2
            while entity_id in used_ids:
                entity_id, k = f"{etype}:{slug}-{k}", k + 1
            used_ids.add(entity_id)
            mentions, seen = [], set()
            for n in members:
                if (n.text, n.chunk_id) not in seen:
                    seen.add((n.text, n.chunk_id))
                    mentions.append(Mention(text=n.text, chunk_id=n.chunk_id))
            entities.append(Entity(entity_id=entity_id, canonical_name=canonical, entity_type=etype,
                                   mentions=mentions, match_evidence=uf.evidence.get(root, [])))
        return entities
