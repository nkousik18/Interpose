# Data sources

Raw data itself is never committed to this repo (see `.gitignore`) — it lives on-disk at
`~/.interpose/data/`. This file documents what's downloaded, from where, and under what license.
Full rationale: `docs/INTERPOSE_SCOPING.md` Section 10.

| Dataset | Location | Source | License | Status |
|---|---|---|---|---|
| OFAC SDN (sanctions) list | `~/.interpose/data/ofac-sdn/sdn.csv` | `sanctionslistservice.ofac.treas.gov`, official Treasury API | Public domain (US federal government work) | Downloaded, 19,169 entries |
| IBM Transactions for AML (HI-Medium) | `~/.interpose/data/ibm-aml-raw/` | Kaggle (`ealtman2019/ibm-transactions-for-anti-money-laundering-aml`) | CDLA-Sharing-1.0 — see `CITATIONS.md` | Raw files downloaded; not yet subsampled |

## Correction vs. the scoping doc

`INTERPOSE_SCOPING.md` Section 10.3 describes the HI-Medium variant as "~180M transactions."
That figure actually describes **HI-Large** (the `HI-Large_Trans.csv` file in the same Kaggle
dataset, ~17GB). The file we actually downloaded, `HI-Medium_Trans.csv`, is **31,898,238 rows
(~2.8GB)**. This doesn't change the plan — HI-Medium was always the deliberate target, scoped
for a laptop — it just corrects the row-count description. The scoping doc's subsampling
procedure (Section 10.3: random-select ~500K accounts, retain both-party-in-sample
transactions, seed 42) still applies, just starting from ~32M rows instead of ~180M.

Also corrected: the license is **CDLA-Sharing-1.0** (Community Data License Agreement –
Sharing), not CC-BY 4.0 as the scoping doc assumed. CDLA-Sharing is a share-alike license for
open data (comparable in spirit to CC-BY-SA) — attribution is still required, and share-alike
means Interpose's own derived/redistributed datasets built from this source should stay under a
compatible open license too. Full text: https://cdla.dev/sharing-1-0/

## What was downloaded

Only the three `HI-Medium_*` files (not the full 8.2GB dataset bundle, which includes much
larger HI-Large/LI-Large variants we don't need):

- `HI-Medium_Trans.csv` — 31,898,238 transaction rows. Columns: `Timestamp`, `From Bank`,
  `Account`, `To Bank`, `Account`, `Amount Received`, `Receiving Currency`, `Amount Paid`,
  `Payment Currency`, `Payment Format`, `Is Laundering`.
- `HI-Medium_accounts.csv` — account metadata. Columns: `Bank Name`, `Bank ID`,
  `Account Number`, `Entity ID`, `Entity Name`.
- `HI-Medium_Patterns.txt` — documents the specific injected laundering patterns (layering,
  structuring, fan-in/out, cycles) present in this split, with references to the account IDs
  involved.

## Refresh notes

- **OFAC**: downloaded once manually for local dev. Interpose's sanctions MCP server (built in
  Phase 3) will fetch it fresh from the same URL on its own startup — this manual copy was just
  to verify the source and format work before writing that server.
- **IBM AML**: downloaded once as raw CSV, still needs subsampling down to ~500K accounts via a
  PySpark job (next Phase 0 step, once Spark is set up) — see Section 10.3 of the scoping doc
  for the exact subsampling procedure and reproducibility seed.
