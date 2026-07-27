"""OFAC SDN + alternate-identities loading, parsing, and fuzzy-match index (docs/
INTERPOSE_SCOPING.md Section 9.6, D-2). Fetches from the real Treasury API by
default; `parse_*`/`build_index` are pure functions so they're unit-testable against
small fixture text without any network access -- see data/README.md's "OFAC file
formats" section for the real-data quirks these functions handle (no header row, the
`-0-` null sentinel, bracket-joined multi-program fields).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from models import REFERENCE_URL_TEMPLATE, SanctionsMatch, SDNEntry
from rapidfuzz import fuzz, process, utils

# Case-sensitive lowercase path -- the uppercase form 400s (verified while scoping
# this server; see data/README.md).
SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
ALT_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/alt.csv"

NULL_SENTINEL = "-0-"
DEFAULT_MATCH_THRESHOLD = 70.0


async def fetch_text(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def load_source(source: str) -> str:
    """`source` (config.py's sdn_source/alt_source) is either an http(s) URL --
    fetched live, the real default -- or a local file path, read from disk. The
    path form is what tests and offline local dev point at instead of the live
    Treasury API."""
    if source.startswith("http://") or source.startswith("https://"):
        return await fetch_text(source)
    return Path(source).read_text(encoding="utf-8")


def _clean(raw: str) -> str | None:
    value = raw.strip()
    return None if not value or value == NULL_SENTINEL else value


def _programs(raw: str) -> list[str]:
    cleaned = _clean(raw)
    if cleaned is None:
        return []
    # Multiple programs are joined as "PROGRAM1] [PROGRAM2", not a normal delimiter --
    # no brackets at all around a single-program field.
    return [p.strip("[] ") for p in cleaned.split("] [")]


def parse_sdn_csv(text: str) -> dict[str, SDNEntry]:
    """`sdn.csv`: 12 columns, no header. ent_num, name, sdn_type, program, title,
    call_sign, vess_type, tonnage, grt, vess_flag, vess_owner, remarks -- only the
    first four and the last are used by any tool this server exposes."""
    entries: dict[str, SDNEntry] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 12:
            continue  # the real export has exactly one short/blank trailing line
        ent_num = row[0].strip()
        name = row[1].strip()
        # Blank sdn_type means "entity" (business/organization), not "unknown" -- of
        # the 4 real values, only individual/vessel/aircraft are ever spelled out.
        sdn_type = _clean(row[2]) or "entity"
        entries[ent_num] = SDNEntry(
            ent_num=ent_num,
            name=name,
            sdn_type=sdn_type,
            programs=_programs(row[3]),
            remarks=_clean(row[11]) or "",
        )
    return entries


def parse_alt_csv(text: str, entries: dict[str, SDNEntry]) -> None:
    """`alt.csv`: 5 columns, no header. ent_num, alt_num, alt_type ("aka"), alt_name,
    alt_remarks. Attaches each alias to the `entries` dict's matching SDNEntry
    in-place; rows whose ent_num isn't in `entries` are skipped (can happen when
    `entries` was built from a smaller/fixture sdn.csv, e.g. in tests)."""
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        ent_num = row[0].strip()
        alt_name = row[3].strip()
        entry = entries.get(ent_num)
        if entry is not None and alt_name:
            entry.aliases.append(alt_name)


@dataclass
class SanctionsIndex:
    entries: dict[str, SDNEntry]
    # sdn_type -> {name: [ent_num, ...]} -- a list because two entries can (rarely)
    # share an identical name; returning all of them beats silently dropping one.
    names_by_type: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # every primary name + every alias, any type -> [ent_num, ...]
    all_names: dict[str, list[str]] = field(default_factory=dict)


def build_index(sdn_text: str, alt_text: str) -> SanctionsIndex:
    entries = parse_sdn_csv(sdn_text)
    parse_alt_csv(alt_text, entries)

    names_by_type: dict[str, dict[str, list[str]]] = {}
    all_names: dict[str, list[str]] = {}
    for entry in entries.values():
        names_by_type.setdefault(entry.sdn_type, {}).setdefault(entry.name, []).append(
            entry.ent_num
        )
        all_names.setdefault(entry.name, []).append(entry.ent_num)
        for alias in entry.aliases:
            all_names.setdefault(alias, []).append(entry.ent_num)

    return SanctionsIndex(entries=entries, names_by_type=names_by_type, all_names=all_names)


def _to_match(
    index: SanctionsIndex, matched_name: str, ent_num: str, score: float, threshold: float
) -> SanctionsMatch:
    entry = index.entries[ent_num]
    return SanctionsMatch(
        matched_name=matched_name,
        entry_id=ent_num,
        score=score,
        is_match=score >= threshold,
        programs=entry.programs,
        reference_url=REFERENCE_URL_TEMPLATE.format(ent_num=ent_num),
    )


def best_match(
    names: dict[str, list[str]], index: SanctionsIndex, query: str, threshold: float
) -> SanctionsMatch | None:
    """Single best fuzzy match over `names`' keys, or None if `names` is empty."""
    if not names:
        return None
    # processor=utils.default_process (lowercases + strips punctuation/whitespace
    # noise) matters a lot here: the SDN list is all-caps by Treasury convention, but
    # a real query name won't be -- without it, plain fuzz.WRatio scores a perfect
    # "Aerocaribbean Airlines" vs. "AEROCARIBBEAN AIRLINES" match at ~14% (pure
    # character-case mismatch), below completely unrelated names. Found via this
    # module's own tests, not assumed.
    result = process.extractOne(
        query, names.keys(), scorer=fuzz.WRatio, processor=utils.default_process
    )
    if result is None:
        return None
    matched_name, score, _ = result
    return _to_match(index, matched_name, names[matched_name][0], score, threshold)


def top_matches(
    names: dict[str, list[str]], index: SanctionsIndex, query: str, threshold: float, limit: int = 5
) -> list[SanctionsMatch]:
    """Every SDN entry behind the top `limit` matching names over `names`' keys --
    one name can map to more than one entry (see SanctionsIndex.all_names)."""
    if not names:
        return []
    results = process.extract(
        query, names.keys(), scorer=fuzz.WRatio, processor=utils.default_process, limit=limit
    )
    matches = []
    for matched_name, score, _ in results:
        for ent_num in names[matched_name]:
            matches.append(_to_match(index, matched_name, ent_num, score, threshold))
    return matches
