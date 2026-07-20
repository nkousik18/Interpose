# Session continuity: how an AI-paired project remembers where it left off

## The problem

A new Claude Code session (new context window — could be tomorrow, could be on a different
machine) starts with no memory of any prior conversation. Without something written down, every
session would have to re-explain "here's the project, here's where we stopped, here's what's
next" from scratch. That doesn't scale past a couple of sessions.

There's a same-machine-only shortcut — `claude --continue` or `claude --resume` reopens a prior
conversation with full history intact — but it's tool-specific and doesn't help if you're on a
different machine, or genuinely want a clean context. The durable fix has to live in the repo
itself, readable by any session, on any machine, using any tool (this generalizes past Claude
Code specifically — it's exactly the problem a new human teammate joining a project has too).

## The four documents, and which question each answers

This project splits "project state" across four files, each answering a different question,
each changing at a different rate:

| File | Question it answers | Changes... |
|---|---|---|
| `CLAUDE.md` | What is this project, how do we work together | rarely |
| `docs/ROADMAP.md` | Which phase are we in, what's the gate | phase-by-phase |
| `docs/project/SESSION_LOG.md` | What happened *last time*, what's the immediate next step | every session |
| `CHANGELOG.md` | What has shipped, in user-facing terms | every notable change |

The one that closes the actual gap described above is the session log — it's the only one
granular enough to capture "we corrected X, decided Y, and the very next thing to do is Z."
Without it, that texture only ever existed in a chat transcript that the next session can't
read.

## The ritual (encoded in `CLAUDE.md`)

- **Start of session**: read the latest entry (or few entries) in `SESSION_LOG.md` before doing
  anything, alongside `ROADMAP.md`'s phase checkboxes.
- **End of session** (or a natural stopping point mid-session): append a new dated entry —
  what happened, decisions made, current state, next steps. Never edit past entries to rewrite
  history; append-only, like the audit log this project itself is building
  (see `concepts/02-interpose-gateway-overview.md` — the parallel is not an accident, it's the
  same underlying idea: a trustworthy record is one you add to, not one you edit after the
  fact).

## The bigger pattern this is an instance of

This is a lightweight version of what teams call an **engineering journal** or **devlog** —
distinct from a changelog (which is about shipped *results*) and distinct from commit messages
(which document individual changes, not the arc of a work session). It's also a close cousin of
the standup/handoff notes a human team leaves for whoever picks up work next. None of this is
unique to AI-paired development — it's just newly necessary here because the "teammate" starts
every session with total amnesia by default.

A related, heavier-weight pattern worth knowing for later: **ADRs (Architecture Decision
Records)** — one file per significant, hard-to-reverse decision (e.g. "why Postgres over an
append-only ledger for the audit log"), capturing the context, the decision, and the
consequences, permanently. Session logs capture the *flow* of work; ADRs capture *specific
decisions* worth defending later. We'll introduce `docs/adr/` once Phase 1 starts producing
decisions of that weight — the scoping doc's Section 6.17 ("Open technical questions resolved")
is already effectively a set of pre-written ADRs for the MVP's biggest calls.

## Related

- `docs/project/SESSION_LOG.md`
- `concepts/00-claude-md-files.md`
