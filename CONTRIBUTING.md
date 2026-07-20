# Contributing

This is currently a solo learning/portfolio project (see `README.md` and `docs/ROADMAP.md`),
but it's built in the open and structured the way a real open-source project would be, so
external contributions are welcome once there's enough surface area to contribute to.

## Workflow

This repo follows **GitHub Flow**:

1. `main` is always the deployable branch. Nothing gets pushed to it directly.
2. Create a branch off `main`, named `<type>/<short-description>`:
   - `feat/` — new functionality
   - `fix/` — bug fix
   - `docs/` — documentation only
   - `chore/` — tooling, CI, dependency bumps
   - `refactor/` — internal restructuring, no behavior change
3. Open a pull request against `main` once it's ready. CI (lint + tests) must pass.
4. Squash-merge into `main` once approved.

## Local setup

```
uv sync --all-extras --dev
uv run pytest
uv run ruff check .
```

Requires Python 3.12 (managed automatically by `uv`, see `concepts/05-python-envs-and-uv.md`).

## Commit messages

Prefer [Conventional Commits](https://www.conventionalcommits.org/) style (`feat:`, `fix:`,
`docs:`, `chore:`, ...) — makes history and future changelog generation easier to skim.

## A convention specific to this repo

If a change introduces a new tool, architectural piece, or domain concept, add or update a
file in `concepts/` alongside it (see `CLAUDE.md`) — one concept per file, plain language. This
repo is a learning project as much as a shipped one; the concepts folder is how that gets
captured for anyone reading along later.
