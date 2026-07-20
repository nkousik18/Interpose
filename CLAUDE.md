# Interpose — project instructions for Claude Code

## What this project is

Interpose is an MCP (Model Context Protocol) audit/policy gateway with a demo AML policy pack.
Full spec: `docs/INTERPOSE_SCOPING.md`. Execution plan: `docs/ROADMAP.md`.

**Start every session by reading `docs/project/SESSION_LOG.md` (latest entries) and
`docs/ROADMAP.md` (phase checkboxes)** before doing anything else — that's where things
actually stopped last time and what's next, not just which phase we're in. At the end of a
session, or at a natural stopping point mid-session, **append** a new dated entry to
`SESSION_LOG.md` (what happened, decisions made, current state, next steps). Append-only —
never edit past entries. See `concepts/13-session-continuity-and-progress-logs.md` for why.

## How the owner wants to work

The owner (Kousik) is new to this domain (MCP, Kubernetes, LangGraph, Spark, AML/compliance)
and is building Interpose specifically to learn it well enough to talk about it in interviews —
this is a learning project first, a shipped artifact second. Timeline is flexible (~30 days,
+/- a week); do not rush ahead of understanding to hit a date.

**Every non-trivial step should teach, not just execute:**
- Before or alongside doing something new (a new tool, a new architectural piece, a new
  domain term), explain *what* it is and *why* we're using it here, in plain language.
- After introducing a genuinely new concept, add or update one file in `concepts/` (see
  below). Don't explain the same concept at length in chat *and* in a file — write it once,
  in the file, and reference it from chat.
- The owner does not need to read or review the code itself in detail — focus explanations on
  concepts, reasoning, and tradeoffs, not syntax.
- We are also deliberately learning Claude Code mechanics alongside the project: CLAUDE.md
  files, skills, subagents, and MCP servers. Introduce each one when it becomes naturally
  relevant to what we're building (not all at once), and explain it as a concept too.

## The `concepts/` folder

One Markdown file per concept, in `concepts/`. Rules:
- One concept per file. If a file grows past a comfortable read (roughly 150-200 lines), split
  it into two focused files rather than letting it sprawl.
- Filenames: `NN-topic-name.md`, numbered in rough order of introduction.
- Every file gets a one-line entry in `concepts/INDEX.md` when created.
- Written for someone new to the domain — define jargon on first use, prefer plain language,
  use the *why* before the *what* where possible.

## Standing quality bar for the final deliverable

Even though this is paced for learning, code that gets written should end up production-grade
by the end: real error handling (no bare `except:`, no silently swallowed failures), structured
logging at the key decision points (not print statements), and test coverage per the targets in
`docs/INTERPOSE_SCOPING.md` Section 4.6. It's fine for early scaffolding to be minimal; it should
not stay that way.

## Repo conventions

- Python 3.12, managed with `uv`.
- Module layout under `src/interpose/` follows `docs/INTERPOSE_SCOPING.md` Section 6.16 — don't
  restructure it without updating that section too.
- Commit discipline: one meaningful commit per work session minimum (see roadmap Section
  14.11 in the scoping doc for the reasoning).
