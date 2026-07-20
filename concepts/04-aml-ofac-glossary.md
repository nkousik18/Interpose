# AML / OFAC / compliance glossary

Just enough domain vocabulary to follow the demo we're building — not a compliance course.
Sentinel's AML pack is illustrative and uses public synthetic data; nothing here should be
treated as real regulatory guidance. See [[02-sentinel-gateway-overview]] for why AML was
chosen as the demo domain.

## Core terms

- **AML (Anti-Money Laundering)**: laws and processes aimed at stopping criminals from making
  illegally-obtained money look legitimate ("laundering" it) by moving it through the financial
  system. Banks are legally required to watch for and report suspicious activity.

- **KYC (Know Your Customer)**: the process of verifying who a customer actually is before or
  while doing business with them (identity checks, background info). Upstream of AML monitoring
  — you can't watch for suspicious *behavior* if you don't know *who* is behaving.

- **Sanctions / OFAC**: governments maintain lists of individuals, companies, and countries that
  others are legally barred from doing business with. **OFAC** (Office of Foreign Assets
  Control) is the U.S. Treasury body that maintains the most commonly referenced such list (the
  "SDN list" — Specially Designated Nationals). "Sanctions screening" means checking a name
  against this list before transacting with them. Sentinel's demo uses the *public* OFAC list.

- **SAR (Suspicious Activity Report)**: a formal report a financial institution is legally
  required to file with regulators when it detects potentially suspicious activity. Real SARs
  are legally sensitive documents; Sentinel's demo produces an illustrative "investigation
  report" that is explicitly *not* a real SAR and makes no filing claim.

- **Structuring**: deliberately breaking up a large transaction into many smaller ones to stay
  under a reporting threshold and avoid detection (e.g. many transfers just under $10,000
  instead of one $50,000 transfer). One of the classic patterns AML monitoring looks for, and
  one of the heuristics Sentinel's demo transaction-graph server implements
  (`structuring_check`, per the scoping doc's Section 6.17).

- **Beneficial owner**: the real human who ultimately owns or controls an entity (a shell
  company, a trust), even if their name isn't on the paperwork. Discovering beneficial
  ownership is a hard, deep problem in real AML work — explicitly *out of scope* for Sentinel's
  demo (the scoping doc calls this out directly as something not to be tempted into building).

## Terms specific to how Sentinel uses this domain

- **HITL (Human-In-The-Loop)**: a policy outcome where, instead of allow/deny, the call is
  *held* pending a human's explicit approval or denial. This is the concrete mechanism by which
  Sentinel turns "an AI agent wants to take a real-world action in a regulated domain" into
  something a compliance team actually controls, rather than something the agent just does
  autonomously. We'll build this in Week 2.

- **Investigation agent**: the demo LangGraph agent that plays the role of a junior AML analyst
  — given a suspicious account, it calls tools (sanctions checks, transaction history) through
  Sentinel, and produces a written assessment. It's the thing generating the ~40 tool calls per
  demo run that Sentinel's policy engine and audit log get exercised against.

## Why the scoping doc is so insistent this isn't a real compliance product

A few reasons worth internalizing (useful in an interview context too): using synthetic/public
data and disclaiming "not regulator-approved" avoids (a) implying false compliance guarantees
to anyone who stumbles on the repo, (b) scope creep into building an actually-correct AML
detection system (a genuinely hard, multi-year problem for real compliance teams), and (c) any
suggestion the project is production financial software rather than a governance-layer
demonstration.

## Related

- [[02-sentinel-gateway-overview]]
