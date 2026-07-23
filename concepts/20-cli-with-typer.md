# Building the `interpose` CLI with Typer

Phase 1 Day 5 (`docs/ROADMAP.md`); implements `interpose verify-audit`
(`docs/INTERPOSE_SCOPING.md` Section 6.7 / G3). `src/interpose/cli/`.

## What Typer is, and why it needed no new dependency

**Typer** is a CLI framework built on top of **Click** (the library underneath most
Python command-line tools) that derives a command's arguments and validation
straight from Python type hints, the same way FastAPI derives HTTP request validation
from type hints — `def verify_audit(since: str | None = None)` becomes a
`--since TEXT` option with no separate argument-parser boilerplate. It was already
installed as a transitive dependency of `mcp[cli]` (the MCP Python SDK's own CLI
tooling depends on it), so building `interpose verify-audit` needed zero new entries
in `pyproject.toml` beyond the `[project.scripts]` entry point that makes `interpose`
a real installed command (`interpose = "interpose.cli.main:app"`).

## A real gotcha, worth knowing before it surprises you elsewhere

With only one command registered, Typer silently *collapses* the CLI into a flat
form — `interpose --since ...` instead of `interpose verify-audit --since ...` —
on the theory that forcing `mytool mytool-only-command` is bad UX for a genuinely
single-purpose tool. That's a reasonable default, but it's the wrong shape here: the
scoping doc's own spec text is `interpose verify-audit --since=...`, and a second
command (`interpose review`, Phase 2's HITL work) is already planned, at which point
the CLI's shape would silently change again as soon as that command landed. Adding an
empty `@app.callback()` disables the collapsing — Typer treats the presence of *any*
top-level callback as evidence this is meant to be a multi-command group, even before
a second command actually exists. Small thing, but exactly the kind of "worked
locally, looked done, was actually one flag away from the wrong CLI shape" issue
that's cheap to catch by actually running the command rather than trusting it once
the code compiles.

## `--since` filters the report, not what gets verified

The temptation with a `--since` flag is to have it also narrow the database query —
"only fetch and check entries after this date." That's wrong for a hash chain
specifically ([[19-hash-chained-audit-log]]): the whole guarantee comes from walking
unbroken from the genesis hash, so checking an arbitrary later slice in isolation
can't actually detect tampering that happened *before* that slice starts — you'd need
to already know the correct expected `prev_hash` entering the slice, which requires
having verified everything before it anyway. So `verify_audit` always fetches and
verifies every row from genesis; `--since` only changes what gets *reported* (how
many of the already-verified entries fall in the requested window), never what gets
*checked*. Worth stating in the command's own `--help` text, not just in code
comments — a compliance officer reaching for `--since` to "just check recent stuff"
should know up front that it's not a shortcut past verifying everything before it.

## Related

- [[19-hash-chained-audit-log]]
