# CLAUDE.md files

## What it is

A `CLAUDE.md` file is a plain Markdown file that Claude Code automatically reads at the start
of a session in that directory (and its subdirectories). It's not magic — it's just text that
gets silently added to the model's context before it does anything else. Think of it as a
standing memo left on the desk of whoever picks up this project next, except the "whoever" is
usually a fresh instance of Claude with zero memory of past conversations.

## Why it exists

Without it, every new session starts from nothing: no idea what the project is, what
conventions to follow, or how you like to work. You'd have to re-explain "this is an MCP
gateway, I'm new to the domain, teach concepts as we go, use `concepts/`..." every single time.
`CLAUDE.md` makes that context durable instead of something you retype.

It's the project-level equivalent of onboarding docs for a new hire — except the new hire
starts fresh every session, so the memo has to actually be read every time, not just once.

## Why we're using it here specifically

Two reasons, matching the two things this project is for:

1. **Practical** — it encodes *how* we've agreed to work (teach concepts, keep `concepts/`
   updated, hold code to a real quality bar) so that carries forward automatically instead of
   depending on you repeating instructions each session.
2. **Learning goal** — you explicitly wanted to learn CLAUDE.md as a mechanism while building
   the project, so the root `CLAUDE.md` in this repo doubles as a live example to point at.

## Things worth knowing

- **It's scoped by directory.** A `CLAUDE.md` in the repo root applies everywhere in the repo.
  You can also put more specific `CLAUDE.md` files in subdirectories (e.g. one inside
  `terraform/` with Terraform-specific conventions) — Claude Code picks up the ones relevant to
  where it's working. We're not doing that yet; the root file is enough until the project has
  enough distinct sub-areas to justify it. We'll add scoped ones when that becomes true (likely
  once `terraform/`, `charts/`, and `src/sentinel/control_plane/` each have their own real
  conventions worth stating).
- **It's not enforcement.** Nothing *forces* Claude to obey it — it's a strong instruction, not
  a hard constraint, the same way an onboarding doc doesn't stop a new hire from cutting a
  corner. It works because it's read and followed in good faith, and because you can always
  say "check CLAUDE.md" if something drifts.
- **Keep it short.** It gets loaded into every session's context whether it's needed or not. A
  bloated `CLAUDE.md` costs context budget for the rest of the conversation. Detailed,
  occasionally-needed information belongs in `docs/` or `concepts/`, with just a pointer from
  `CLAUDE.md`.

## Related

- [[01-what-is-mcp]] — the protocol this whole project is about.
