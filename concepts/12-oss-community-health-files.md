# OSS "community health" files, and CI

## What these files are

GitHub recognizes a specific set of files by name and gives them special treatment (surfacing
them in the UI, prompting contributors with them) — collectively called "community health
files." We just added the standard set:

- **`CONTRIBUTING.md`** — how to actually contribute: branch/commit conventions, local dev
  setup, the PR process. The answer to "I want to help, where do I start?"
- **`CODE_OF_CONDUCT.md`** — the behavioral ground rules for anyone interacting in the project's
  spaces (issues, PRs, discussions). We used the **Contributor Covenant**, the de facto standard
  text nearly every major open-source project adopts rather than writing their own from scratch.
- **`SECURITY.md`** — how to report a vulnerability *privately* rather than in a public GitHub
  issue (which would announce the hole to everyone before it's fixed). Especially relevant here
  since Interpose's whole purpose is security/governance tooling — see the project's own
  `SECURITY.md` for the reasoning about pre-1.0 status and scope.
- **`CHANGELOG.md`** — a human-readable, chronological record of what changed, release by
  release, following the **Keep a Changelog** convention. Different from `git log`: git history
  is a record of *commits* (implementation detail, many of them noise); a changelog is a curated
  record of *what a user or contributor needs to know changed*.
- **Issue and PR templates** (`.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`) —
  structured prompts so a bug report or PR description reliably contains the information needed
  to act on it, instead of "it doesn't work, please help."

## Why bother, for a solo project with no contributors yet

Two reasons: first, these files are exactly what Room 1 of this project's audience (the
MCP/open-source community, see `concepts/02-interpose-gateway-overview.md`) uses to judge
whether a repo is a serious, maintained project versus a one-off script dump — before anyone
reads a line of code. Second, writing them now is cheap and forces useful decisions early (how
do we want contributions to flow? what's actually in scope for a security report?) rather than
improvising them under pressure later.

## What CI adds on top

**CI (Continuous Integration)** means: every time code changes (here, on push to `main` or on
any pull request), an automated pipeline runs — in our case, `.github/workflows/ci.yml` runs
`ruff` (lint: catches style issues and some real bugs, like unused imports or obvious logic
errors) and `pytest` (runs the test suite) on GitHub's own servers, not your machine.

Why this matters even solo: it's an *independent* check. Code that "works on my machine" but
was actually relying on something local (a stale cache, an environment variable you forgot you
set) gets caught, because CI starts from nothing every time. Combined with branch protection
(`concepts/11-git-branching-and-github-flow.md`) requiring CI to pass before a PR can merge,
it's the mechanism that actually enforces "`main` is always deployable" — a policy is just words
until something automated refuses to let it be violated.

We used **GitHub Actions** specifically because the repo is already on GitHub — it's built in,
free for public repos, and defined declaratively in YAML checked into the repo itself (so the
pipeline's history is versioned right alongside the code it tests).

## Related

- `concepts/11-git-branching-and-github-flow.md`
- `.github/workflows/ci.yml`
