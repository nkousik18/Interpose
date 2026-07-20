# Session log

Purpose: a new session (new context window, possibly a new machine) should be able to read this
file and know *exactly* where things stand — not just which phase we're in (`docs/ROADMAP.md`
covers that), but what happened last time, what was decided, and what the immediate next step
is. See `concepts/13-session-continuity-and-progress-logs.md` for why this file exists and how
it fits alongside `CLAUDE.md`, `docs/ROADMAP.md`, and `CHANGELOG.md`.

Newest entry first. One entry per work session (not necessarily per calendar day).

---

## 2026-07-20 — Project kickoff: scaffold, environment, first data, rename, GitHub setup

**What happened:**
- Read the full `docs/INTERPOSE_SCOPING.md` (287KB planning doc) and confirmed shared
  understanding of the project before writing anything.
- Scaffolded the repo per the scoping doc's Section 6.16 layout; established `CLAUDE.md` and
  `concepts/` as working conventions (one plain-language explainer per new tool/domain idea).
- Adapted the scoping doc's fixed day-by-day plan (Section 14) into `docs/ROADMAP.md` — same
  phases and gates, but paced by understanding rather than the calendar.
- Set up local dev environment: `uv`-managed Python 3.12, Docker, `kubectl`, `helm`,
  `terraform`, `kind` — each installed and verified working (not just installed — actually ran
  a `kind` cluster up/down, ran a real MCP client/server round trip).
- Caught and fixed a Homebrew `autoremove` side effect that had silently uninstalled `node` and
  `mongosh`; reinstalled both.
- Downloaded and validated the OFAC SDN sanctions list (19,169 entries) and the IBM AML
  HI-Medium dataset from Kaggle (31.9M transaction rows, ~2.8GB) — corrected two scoping-doc
  inaccuracies along the way (HI-Medium is ~32M rows, not ~180M as stated; the dataset's actual
  license is CDLA-Sharing-1.0, not CC-BY 4.0).
- Renamed the project from "Sentinel" (felt generic) to **Interpose**, throughout the repo,
  local data directories, and all documentation.
- Created the GitHub repo, pushed `main`, added standard OSS scaffolding (`CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, issue/PR templates, GitHub Actions CI),
  adopted **GitHub Flow** as the branching convention, and set branch protection on `main`
  (PR + passing CI required; verified live that admin bypass is possible by design).
- Added 13 `concepts/` docs so far (00 through 12): CLAUDE.md files, MCP, the
  Interpose/gateway architecture, SLA/SLO/latency, the AML/OFAC glossary, Python envs & `uv`,
  containers & Docker, Kubernetes, Terraform/IaC, the MCP handshake, open data licensing,
  git branching & GitHub Flow, and OSS community-health files.

**Decisions made:**
- Branching model: GitHub Flow (not GitFlow, not trunk-based-forever) — see
  `concepts/11-git-branching-and-github-flow.md`.
- Learning pace over calendar pace: ~30 days, flexible by about a week, gated on actually
  understanding each concept, not on hitting fixed days.

**Current state:**
- Phase 0 (Prep) nearly complete. Repo, environment, CI, and both source datasets are in place.
- Only remaining Phase 0 item: **subsample the IBM AML dataset down to ~500K accounts**, which
  requires setting up Spark/PySpark locally first (a new tool + concept, not yet introduced).

**Next steps:**
1. Set up Spark/PySpark locally (new concept doc needed: what Spark is, why a distributed
   processing engine for a laptop-sized job, Java runtime dependency).
2. Run the subsampling job per `docs/INTERPOSE_SCOPING.md` Section 10.3 (seed 42, ~500K
   accounts, verify laundering-label ratio and graph connectivity preserved).
3. That completes Phase 0's gate — move into Phase 1 (Foundation): the FastAPI gateway request
   lifecycle.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should be rotated (Settings → API →
  regenerate) — flagged, not yet confirmed done.
