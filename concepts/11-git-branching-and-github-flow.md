# Git branching strategies, and why GitHub Flow

## The problem a branching strategy solves

Once more than one thing is happening in a repo at once — you're mid-way through a risky change
and want to try something else, or (later) more than one person is contributing — pushing
everything straight to `main` gets dangerous: a half-finished change can leave `main` in a
broken state for anyone else who pulls it. A branching strategy is just a team's agreed-upon
answer to "where does work-in-progress live, and when does it become part of the real history?"

## The main options, briefly

- **Trunk-based / direct-to-main**: everyone commits straight to `main`, often multiple times a
  day, relying on small changes and strong automated tests to keep it always releasable. What
  we were doing until now — reasonable for the earliest, fastest-moving days of a solo project.
- **GitHub Flow**: `main` is always deployable; every change (however small) happens on a
  short-lived branch, gets reviewed via a pull request, and merges back in. No other permanent
  branches. This is the default most modern open-source projects and companies use today.
- **GitFlow**: adds long-lived `develop` (integration branch), plus `release/*` and `hotfix/*`
  branches around it, on top of GitHub Flow's idea. Built for software with scheduled,
  versioned releases that need to patch older versions independently (think: an app with
  version 1.x still getting security fixes while 2.x is in active development). More ceremony
  than a fast-moving MVP needs — worth knowing about because some enterprise teams (exactly the
  audience this project targets, see `concepts/02-interpose-gateway-overview.md`) still use it,
  but not what we're adopting here.

## What we picked, and why

**GitHub Flow.** Reasoning: Interpose has no parallel-maintained released versions yet (there's
nothing to hotfix), it's not enterprise software with scheduled release trains, and GitHub Flow
is genuinely the more current default — citing it in an interview reads as "knows what teams
actually do now," not "knows the textbook model." Concretely, from here on:

- New work happens on a branch named `feat/...`, `fix/...`, `docs/...`, or `chore/...` (see
  `CONTRIBUTING.md`).
- It merges into `main` via a pull request, not a direct push.
- `main` gets branch protection (no direct pushes, no force-push) so this is enforced rather
  than just agreed-upon.

## What "branch protection" actually is

A GitHub setting on a specific branch (here, `main`) that enforces rules automatically —
blocking direct pushes, requiring a pull request first, requiring CI to pass before merging,
etc. Without it, a branching strategy is just a convention anyone (including future-me, in a
hurry) can accidentally skip. With it, the platform refuses the shortcut.

## Related

- `.github/workflows/ci.yml` — the automated check that a PR must pass before merging.
- `concepts/12-oss-community-health-files.md`
