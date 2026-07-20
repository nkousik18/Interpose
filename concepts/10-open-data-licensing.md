# Open data licenses: public domain vs. CC-BY vs. CDLA-Sharing

Prompted by a real correction we had to make: the scoping doc assumed the IBM AML dataset was
CC-BY 4.0; the actual Kaggle page says CDLA-Sharing-1.0. Worth understanding the difference,
both to fix that specific mistake and because "we handled data licensing correctly" is exactly
the kind of data-governance detail the scoping doc calls out (Section 10.14) as something
enterprise platform teams notice.

## The three licenses touching this project

- **Public domain** (OFAC SDN list): no license at all, because US federal government works
  aren't eligible for copyright. No attribution legally required, no restrictions on use. We
  cite the source anyway (in `data/CITATIONS.md`) purely for reproducibility, not because the
  license demands it.

- **CC-BY 4.0** ("Creative Commons Attribution"): you can use, modify, and redistribute the
  data for any purpose, including commercially, as long as you give credit to the original
  creator. No obligation about what license *your* resulting work carries. This is what the
  scoping doc assumed for the IBM dataset — reasonable to assume for a lot of Kaggle datasets,
  but wrong for this specific one.

- **CDLA-Sharing-1.0** ("Community Data License Agreement – Sharing"), the license the IBM AML
  dataset actually uses: attribution required, *plus* a **share-alike** clause — if you publish
  a dataset that's derived from data under this license, that derived dataset has to carry a
  compatible open license too. It does **not** restrict what you can build *using* the data
  (Sentinel's code, the demo, the blog posts are all unaffected) — the share-alike obligation
  only reaches datasets you redistribute, not software.

## Why the distinction actually matters here

Sentinel doesn't republish the IBM transaction data itself — the raw CSVs stay
`.gitignore`d, never committed, and the repo only ships a small labeled synthetic adversarial
corpus we generate ourselves (see the scoping doc's D3 dataset, Section 10.5). So the
share-alike clause doesn't bite for the MVP as currently scoped. It *would* matter if a later
version published a cleaned/subsampled copy of the AML data alongside the project — that copy
would need to carry CDLA-Sharing-1.0 forward, not a different license.

## The practical habit worth keeping

Don't trust a dataset's license from memory, a scoping doc, or a dataset's reputation — check
the license Kaggle (or whatever host) actually states on the download, every time, and record
it in `data/CITATIONS.md` next to the download itself. We caught this one because the `kaggle
datasets download` output prints the license inline before downloading — that's a cheap,
easy-to-miss verification point worth reading rather than skipping past.

## Related

- `data/README.md`, `data/CITATIONS.md` — the actual records for this project.
- [[04-aml-ofac-glossary]]
