# Data and terms

This page is a short reading of BAFU's Terms of Use (BAFU:20XY) for people working in
this workspace and in the repositories it connects: what the terms require of every copy
of the data that is passed on. It is a reading, not legal advice; where it matters, ask
BAFU (lca@bafu.admin.ch) rather than guess.

The full reading, with every clause and what sentier.dev's wiki says about it, is on
[lca-wiki › bafu › access and licence](https://github.com/sentier-dev/lca-wiki/blob/main/bafu/knowledge/access-and-licence.md).

## The clauses that matter here

| Clause | Obligation |
|---|---|
| **2.1** | The unmodified Data may be used, processed, analysed and reused freely — in studies and in calculators — **as long as it is not sold, resold, distributed or marketed separately, "as such or as a part of another database"**. |
| **2.2** | Any other use needs an explicit agreement with BAFU. |
| **2.3** | Credit: *"Life Cycle Inventory database of the Swiss Federal Administration, BAFU:20XY"*, with the release year. |
| **3.2–3.3** | **Every modification documented** (which datasets, what changed, why) in a **standalone document that travels with the modified data**. |
| **3.4** | Modified Data passed to a third party is shared under **substantially equivalent terms** (share-alike), with the 2.3 credit. |
| **3.5** | Modified Data is **labelled as modified**, never presented as the original. |
| **4** | The LCI *Reports* are the authors' copyright; never paste their text — cite by title. |
| **5** | No additional restrictions of your own (legal, technical, DRM). |
| **7** | The terms bind the version you downloaded; **taking a copy is the act of acceptance** — so a service that hands out copies must obtain that acceptance first. |

## What that means here

- **Findings quote dataset codes, names and the specific values under
  discussion.** The findings list describes the data; it does not reproduce it.
  Contributions refer to the import of BAFU's release by commit and checksum;
  builds of a changed version stay in local folders that are not committed.
- **Any build** (an import, a relinking onto EF 3.1 flows, a method binding)
  is *modified* in the sense of clause 3 the moment it drops, re-points or
  re-declares anything. The honest default is to treat every served build as
  Modified Data: label it, ship its record of modifications with it, credit
  the release.
- **A record of modifications is data, not prose.** One entry per change with
  the dataset(s), the nature of the change, the rationale and the evidence;
  generated from the records that produced the build, so it cannot drift from
  what was built. lci-bafu-catalog's `corrections/<release>.json` →
  `BAFU_ATTRIBUTION.md` is one working example.
- **Redistributing the inventory itself** — the whole set of datasets as files
  — is the thing clause 2.1 names. Whether a public repository holding the full
  release as parquet is covered by 3.4 (share-alike Modified Data) or needs a
  2.2 agreement is BAFU's call, and the question is open: see
  [#1](https://github.com/sentier-dev/sentier-bafu/issues/1). Until it is
  answered, say on the artefact which basis it claims.

## What a copy must carry

A served build, a package, a parquet set or an export derived from the Data
carries, next to the data: the 2.3 credit with the release year, the label
*Modified Data* if anything was changed, the record of modifications, and the
share-alike terms (3.4). Metadata inside the database (so a clone inherits it)
plus a human-readable file beside it is the pattern that survived review.
