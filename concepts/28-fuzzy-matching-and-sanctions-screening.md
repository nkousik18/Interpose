# Fuzzy string matching, and what it takes to search a real sanctions list

Phase 3, Day 11 (`docs/ROADMAP.md`); implements `docs/INTERPOSE_SCOPING.md` Section 9.6's
`ofac-sanctions` MCP server. First non-toy MCP server in the repo — the first one backed
by a real external data source and a real domain problem, not an echo tool.

## Why exact string matching isn't enough

"Sanctions screening" means checking whether a name a customer/agent gives you matches
someone on a list of prohibited parties (see [[04-aml-ofac-glossary]] for what OFAC/SDN
mean). If the check were `name == entry.name`, it would miss almost every real hit: people
and companies get typed with different capitalization, punctuation, abbreviations
("Co." vs "Company"), transliteration variants, and plain typos. A screening tool that
only catches exact matches is worse than useless — it creates false confidence. Real
sanctions screening is a **fuzzy matching** problem: given a query name, find the closest
name(s) on the list and say *how* close, not just whether it's identical.

## rapidfuzz, in brief

**rapidfuzz** is a fast (C++-backed) Python library for string similarity. The building
blocks used here:

- `fuzz.WRatio(a, b) -> float` (0-100): a composite similarity score — under the hood it
  tries several comparison strategies (whole-string, partial, token-reordered) and
  returns the best-justified one, which is why it's a sturdier default than a single
  edit-distance ratio for names that might have extra words or reordered tokens
  ("John Doe" vs "Doe, John").
- `process.extractOne(query, choices, scorer=...) -> (match, score, index)`: the single
  best match over a collection of candidate strings.
- `process.extract(query, choices, scorer=..., limit=N)`: the top-N matches — what
  `check_alias` uses, since an alias search is explicitly meant to surface more than one
  candidate.

## A real bug this project's own tests caught: case sensitivity

First implementation used `fuzz.WRatio` with no preprocessing. The OFAC SDN list is
ALL-CAPS by Treasury convention (`"AEROCARIBBEAN AIRLINES"`), but a realistic query comes
in mixed case (`"Aerocaribbean Airlines"`). Plain `WRatio` compares characters literally —
case counts as a mismatch — so the *correct* match scored a dismal ~14%, actually **losing**
to several unrelated candidates in the same list. This is exactly the kind of gap a live
test surfaces and a design review might not: the code "worked" (returned a score, no
crash), it was just silently wrong.

Fix: `rapidfuzz.utils.default_process` (lowercases, strips punctuation noise, collapses
whitespace) passed as the `processor=` argument to every `extractOne`/`extract` call. With
it, the same query scores a perfect 100. One line, but the kind of one line that's invisible
until you test with realistically-cased input instead of the dataset's own casing.

## Two tools, not one, and why

Section 9.6 specifies both `check_entity` (fuzzy-match against the SDN list) and
`check_alias` ("alias-aware search — SDN entries often list multiple names"). This
project's `sdn.csv` download only had one name per entry — the alias data lives in a
second Treasury file, `alt.csv` ("Alternate Identities"), fetched separately once this
became clear (see `data/README.md`'s "OFAC file formats" section for both files' real,
undocumented-by-the-scoping-doc shapes: no header row, a `-0-` null sentinel, bracket-joined
multi-program fields). Without `alt.csv`, `check_alias` would just be `check_entity` under
a different name — with it, the two tools search genuinely different corpora:
`check_entity` only ever searches primary SDN names (and only within one `entity_type` —
individual/entity/vessel/aircraft), while `check_alias` searches primary names *and* every
alias, across all types. `mcp-servers/ofac-sanctions/src/loader.py`'s `SanctionsIndex`
keeps both a `names_by_type` map (for `check_entity`) and a combined `all_names` map (for
`check_alias`) rather than one general-purpose structure, precisely so the two tools stay
meaningfully different.

## A FastMCP quirk worth knowing: `structuredContent`'s envelope

MCP tool results carry both a `content` (text) and, when the tool has a real return-type
annotation, a `structuredContent` (typed JSON) field. Calling `check_entity`  (return type
`SanctionsMatch | None`, a Union) produces `structuredContent = {"result": {...}}` — wrapped
under a `"result"` key. Calling `get_entity_detail` (return type `SDNEntry`, a single
concrete model, no Union) produces `structuredContent` as the object's fields *directly*,
no wrapper. FastMCP can build one clean JSON Schema object for a single concrete type; a
Union needs an envelope to represent "could be any of these shapes" — worth knowing before
writing an integration test against `structuredContent`, since the un-wrapped and
wrapped shapes look almost identical until you index into the wrong key.

## Related

- [[04-aml-ofac-glossary]]
- [[01-what-is-mcp]]
- [[09-mcp-handshake-and-transports]]
