# ofac-sanctions

The OFAC sanctions MCP server (`docs/INTERPOSE_SCOPING.md` Section 9.6, Phase 3 Day 11).
Exposes fuzzy-matched OFAC SDN (Specially Designated Nationals) list lookups over
streamable-HTTP -- see `concepts/28-fuzzy-matching-and-sanctions-screening.md` for the
fuzzy-matching concepts and the real bugs/quirks found building this.

Deliberately its own small, standalone service (own `Dockerfile`, no dependency on
`src/interpose/`) -- this stands in for what a real production sanctions-screening API
would be: an external system Interpose's gateway proxies to, not something the gateway
owns. Phase 3's `transaction-graph` server will follow the same pattern.

## Tools

- `check_entity(name, entity_type="individual")` -- fuzzy-matches `name` against SDN
  **primary names only**, restricted to one entity type (`individual` | `entity` |
  `vessel` | `aircraft`). Always returns the best candidate found (or `None` if that
  type has zero entries); `is_match` says whether the score cleared the configured
  threshold.
- `check_alias(name)` -- fuzzy-matches `name` against SDN primary names **and every
  alternate identity** (`alt.csv`), across all entity types. Returns the top several
  candidates, since an alias search is explicitly broader than `check_entity`.
- `get_entity_detail(sdn_entry_id)` -- full record (including aliases) for a matched
  entry ID.

## Data

Fetches two files fresh from Treasury's public API on every startup (a read-mostly
reference list, loaded once, not per-call):

- `sdn.csv` -- the SDN list itself.
- `alt.csv` -- alternate identities (aliases), without which `check_alias` would just be
  `check_entity` under a different name -- see `data/README.md`'s "OFAC file formats"
  section for both files' real shape (no header row, the `-0-` null sentinel, etc.).

Override `OFAC_SDN_SOURCE`/`OFAC_ALT_SOURCE` (env vars) to point at a local file instead
of the live URL -- what tests and offline dev use, so nothing here depends on Treasury's
service being reachable. `mcp-servers/ofac-sanctions/tests/fixtures/` holds a small
sample (4 real, public-domain SDN entries + 1 real alias) for exactly that purpose.

## Running it

Bare, against the real live Treasury data:

```sh
uv run python mcp-servers/ofac-sanctions/src/server.py
```

Listens on `http://127.0.0.1:9002/mcp`. Standalone unit tests (no network):

```sh
uv run pytest tests/unit/mcp_servers/
```

Integration test through the real gateway (`tests/integration/test_gateway_ofac.py`,
uses the local fixture CSVs above, not live Treasury):

```sh
uv run pytest tests/integration/test_gateway_ofac.py
```

Containerized:

```sh
docker build -t ofac-sanctions:dev mcp-servers/ofac-sanctions
docker run --rm -p 9002:9002 ofac-sanctions:dev
```
