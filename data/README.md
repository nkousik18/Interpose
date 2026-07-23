# Data sources

Raw data itself is never committed to this repo (see `.gitignore`) — it lives on-disk at
`~/.interpose/data/`. This file documents what's downloaded, from where, and under what license.
Full rationale: `docs/INTERPOSE_SCOPING.md` Section 10.

| Dataset | Location | Source | License | Status |
|---|---|---|---|---|
| OFAC SDN (sanctions) list | `~/.interpose/data/ofac-sdn/sdn.csv` | `sanctionslistservice.ofac.treas.gov`, official Treasury API | Public domain (US federal government work) | Downloaded, 19,169 entries |
| IBM Transactions for AML (HI-Medium) | `~/.interpose/data/ibm-aml-raw/` (raw) / `~/.interpose/data/ibm-aml/` (subsampled) | Kaggle (`ealtman2019/ibm-transactions-for-anti-money-laundering-aml`) | CDLA-Sharing-1.0 — see `CITATIONS.md` | Subsampled: 500,000 accounts, 3,158,483 transactions |

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

A third correction, found while running the actual subsampling job: Section 10.3 predicted the
both-parties-in-sample filter would retain "~8–12M transactions" out of ~32M. The real,
measured result is **3,158,483** — see "Subsampling procedure" below for why the doc's estimate
didn't hold and what we did about it. Also, the doc describes account-level `is_launderer` flags
with typology annotations; the actual `HI-Medium_accounts.csv` has no such column (only bank/
entity identity fields). Laundering labels exist solely at the transaction level
(`Is Laundering` 0/1) in `HI-Medium_Trans.csv` and `HI-Medium_Patterns.txt`; "an account is a
launderer" is something we derive (any account touching an `Is Laundering=1` transaction), not
something the raw data states directly.

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

## Subsampling procedure (IBM AML)

Job: `src/interpose/analytics/subsample_aml.py` (`uv run --group analytics python -m
interpose.analytics.subsample_aml`). Seed 42, committed in the script.

Section 10.3's literal procedure — uniformly random-select ~500K accounts, keep transactions
where both parties are sampled — was adjusted after checking what it would actually do to this
data. `HI-Medium_Patterns.txt` contains 2,756 labeled laundering patterns, each a short chain of
specific accounts (5–13 hops). Under pure uniform sampling (~500K of ~2.08M accounts, so each
account has a ~24% chance of being picked), the odds that *every* account in a given chain is
independently drawn together are near zero — the doc's own connectivity-verification requirement
(step 4) would very likely fail under its own step-1 procedure.

What the job actually does:
1. Every account that appears in any `Is Laundering=1` transaction is included unconditionally
   (41,857 accounts) — this guarantees all labeled patterns survive by construction, not by luck.
2. The remaining slots up to 500,000 are filled by a seeded uniform-random draw over every other
   account in the transaction graph (2,077,023 total unique accounts).
3. Transactions are kept where both parties are in the resulting 500K-account set.

**Results** (see `~/.interpose/data/ibm-aml/subsample_report.json` for the full machine-readable
report):

| | Raw HI-Medium | Subsampled |
|---|---|---|
| Transactions | 31,898,238 | 3,158,483 |
| Unique accounts | 2,077,023 | 500,000 |
| Laundering transactions | 35,230 | 35,230 (100% retained) |
| Laundering ratio | 0.110% | 1.115% |

The laundering ratio rises rather than holding steady (the doc's step 3 says "verify the sample
retains labeled laundering cases at their original ratio") because every laundering account is
guaranteed in-sample while most non-laundering accounts are not — this is a direct, understood
consequence of the guaranteed-inclusion design, not a bug. All 35,230 laundering transactions
survive intact. Connectivity check (step 4): the first 100 labeled patterns (spanning all 7
typologies) were checked account-by-account against the final sample — **100/100 fully
preserved**.

Output: Parquet, `~/.interpose/data/ibm-aml/transactions/` (partitioned by `month` — collapses to
a single `month=2022-09` partition since the whole HI-Medium split covers one month) and
`~/.interpose/data/ibm-aml/accounts/` (entity metadata for the sampled accounts only).

## Refresh notes

- **OFAC**: downloaded once manually for local dev. Interpose's sanctions MCP server (built in
  Phase 3) will fetch it fresh from the same URL on its own startup — this manual copy was just
  to verify the source and format work before writing that server.
- **IBM AML**: subsampled once as a one-shot local job. Re-running
  `subsample_aml.py` regenerates the same output deterministically (fixed seed) unless the raw
  CSVs change.
