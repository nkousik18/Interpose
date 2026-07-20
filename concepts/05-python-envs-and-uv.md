# Python environments, and why `uv`

## The problem it solves

Your machine had **four different Python installs** floating around before we touched
anything: a pyenv-managed 3.9.6 as the system default, a Homebrew 3.12.12, a Miniconda 3.12.9,
and pyenv's own 3.12.9. That's normal for a machine with years of accumulated tooling — but it
means "just run `python3`" is ambiguous: which one, with which packages installed, answers that
command depends on `PATH` order at that exact moment.

Two classic ways people used to solve this:
- **A version manager** (pyenv, conda) — controls *which Python interpreter* `python` resolves
  to, globally or per-directory.
- **A virtual environment** (`venv`, `virtualenv`) — an isolated folder of installed packages so
  Project A's dependencies don't collide with Project B's.

Traditionally these were two separate tools you had to learn and wire together (pyenv +
venv + pip, or conda doing both its own way). `uv` does both jobs itself, and does them fast
(it's written in Rust) and reproducibly.

## What we actually did

1. `uv python install 3.12` — downloaded a self-contained Python 3.12.13, isolated from all
   four pre-existing installs, managed entirely by `uv` in its own directory.
2. `.python-version` file pinned to the exact `3.12.13` — this is what told `uv` which
   interpreter to use. (We first tried the looser `3.12`, and `uv` picked up Miniconda's 3.12.9
   instead, since that satisfied "any 3.12" and happened to be found. Pinning the exact patch
   version removed the ambiguity and the dependency on conda being present at all.)
3. `pyproject.toml` — the standard modern Python file declaring what this project is, what
   Python version it needs, and what packages it depends on (empty for now).
4. `uv sync` — created `.venv/`, a virtual environment scoped to *this project only*, using
   exactly the pinned interpreter, with exactly the dependencies in `pyproject.toml` installed.

## Why this matters beyond "it works"

- **Reproducibility**: anyone (including future-you, on a different machine) who clones this
  repo and runs `uv sync` gets the identical Python version and identical package versions —
  no "works on my machine" drift.
- **Isolation**: nothing we install for Interpose touches your system Python, conda, or pyenv
  setups, and vice versa.
- **It's simply what most modern Python projects use now.** Worth being able to say in an
  interview: "I used `uv` for dependency and environment management" is a current, expected
  answer, not a dated one (`pip` + manually-managed `venv` reads as older practice now).

## The other lesson from this step: Homebrew autoremove

Installing `uv` via `brew install uv` triggered Homebrew's automatic cleanup, which uninstalled
`node` and `mongosh` as "no longer needed" — packages that had nothing to do with `uv`, just
happened to be flagged as unused dependencies of something else. We reinstalled both. Lesson
carried forward: `export HOMEBREW_NO_AUTOREMOVE=1` before any further `brew install` in this
project, so a package install doesn't silently remove unrelated tools you rely on elsewhere.

## Related

- [[06-containers-and-docker]]
