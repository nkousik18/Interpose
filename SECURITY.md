# Security Policy

## Project status

Interpose is a pre-1.0 portfolio/learning project (see `README.md`, `docs/ROADMAP.md`). It is
**not production-hardened, not regulator-approved, and the AML policy pack is illustrative
only**, built on public synthetic data (see `concepts/04-aml-ofac-glossary.md`). Treat any
deployment accordingly.

That said — this project's entire premise is enforcing security/governance policy on AI agent
tool calls, so vulnerabilities in it are taken seriously and reports are genuinely welcome, pre-1.0 status notwithstanding.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security vulnerabilities. Instead, use
[GitHub's private vulnerability reporting](https://github.com/nkousik18/Interpose/security/advisories/new)
for this repository (Security tab → "Report a vulnerability").

Include, if possible:
- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof of concept.
- Any suggested remediation.

## Supported versions

Pre-1.0: only the latest commit on `main` is supported. Once `v0.1.0` ships, this section will
be updated with a version support table.

## Scope

The adversarial test suite (`tests/adversarial/`, once built) documents the attack classes
Interpose is explicitly designed to catch, and `docs/INTERPOSE_SCOPING.md` Section 13 documents
the threat model and what's explicitly out of scope. Reports about behavior already documented
as out-of-scope are still welcome as discussion, but won't be treated as vulnerabilities.
