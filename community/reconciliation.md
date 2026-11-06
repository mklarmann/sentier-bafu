# Reconciliation receipt: findings and community patches, 21 October 2026

This receipt accounts for every finding (F1–F17, and since 4 November F19, F21
and F29–F31) and contribution (C001, C002)
against the public metadata of the
[bafu-community-fixes](https://github.com/sentier-dev/bafu-community-fixes)
patches at revision `053c799`. The records themselves are in
[reconciliation.json](reconciliation.json); `scripts/community.py check` keeps them
consistent with the [findings ledger](findings.md). It delivers
[#22](https://github.com/sentier-dev/sentier-bafu/issues/22).

Provider responses are cited as the patches record them ("Marine Manche, BAFU
(email, 12 October 2026)"); no correspondence is reproduced. A provider
confirmation is not a provider adoption: on 21 October no finding was
`upstream-fixed`, because no official BAFU release containing a correction had
been verified. F17 became `upstream-fixed` on 4 November (below).

## Updated

| Finding | Before | After | Why |
|---|---|---|---|
| F1 strawberries | open | upstream-reported | BAFU confirmed the error and announced a correction for its next release. Patch 0001 applies the amounts BAFU gave until then. |
| F3 supplier locations | open | upstream-reported | BAFU confirmed and announced a correction. Patch 0002 uses the suppliers' locations for the 25 exchanges until then. |
| F8 aggregated datasets | informational | handled-in-layer | Patch 0011 flags 40 datasets type 2; all 37 structural candidates are among them (UUID membership checked). A full `--strict` run is recorded in its PR. The question to BAFU is still open. Changed in PR #33. |
| F11 retired datasets | open | upstream-reported | BAFU explained the convention and announced a "not maintained" category. Patch 0003 flags the 1,289 prefixed datasets; the 57 unprefixed obsolete datasets are not flagged. |

F1, F3 and F11 are `upstream-reported`, not `handled-in-layer`. BAFU has
answered, which closes the question the ledger's `handled-in-layer` keeps open,
and no contribution record or candidate build exists for patches 0001–0003.
The patches and BAFU's confirmation are recorded as separate fields.

## Preserved unchanged

- **Open, awaiting BAFU:** F2 (R134a, ×10), F7 (LCIA workbook totals),
  F9 (CEM II lorry transport), F10 (straw bale without flows: no type flag
  can supply missing flows, so patch 0011 does not address it), F13–F16
  (re-measured on 21 October 2026; see #28–#31).
- **Added on 21 October, after the reconciliation:** F17 (#35, swapped ecotoxicity
  sub-indicator columns in the published workbook), then open and awaiting an
  independent re-measurement; `upstream-fixed` since 4 November (below).
- **Informational:** F5 (chloride sub-compartments), F6 (concrete effluent),
  F12 (elementary flows in two units).
- **Withdrawn:** F4, kept so nobody re-finds it.
- **Contributions:** C001 and C002 stay `proposed` with their recorded gaps.
  C001 is a separate scenario; C002's passed checks are file checks only, and
  flow correspondence does not demonstrate LCIA integration.
- **Counts kept distinct:** the 37 structural aggregated candidates (F8) and
  the 22 the hackathon reports rebuilt describe different stages.

## Still unresolved

Every record that is not withdrawn names a next action, a review role and an
evidence link in [reconciliation.json](reconciliation.json). In short:

| Next action | Role | Records |
|---|---|---|
| Verify the correction in the next BAFU release, then mark it upstream-fixed and retire the patch; for F11, also ask about the 57 unprefixed obsolete datasets | maintainer | F1, F3, F11 |
| Send to BAFU with the next batch | maintainer | F2, F6, F8, F9, F10, F13, F14, F15, F16 |
| Recompute from an independent score run | reviewer | F7 |
| Re-measure independently, then send to BAFU | reviewer | F19, F21, F29, F30, F31 |
| Check the flow crosswalk | flow curator | F5 |
| Importer parity or pinned LCIA package | importer maintainer | F12, C002 |
| Run the missing checks | reviewer | C001 |


## Added on 4 November 2026

| Finding | Before | After | Why |
|---|---|---|---|
| F17 swapped ecotoxicity headers | open | upstream-fixed | BAFU's corrected workbook of 15 July 2026 exchanges the two header labels; compared cell by cell with the June file, every value is identical. We had measured the June file. A tool reading the columns by position keeps the swap ([#35](https://github.com/sentier-dev/sentier-bafu/issues/35#issuecomment-6416361584)). |
| F12 flows in two units | informational | informational | Re-counted by name and compartment: 112 flows, including Nm3 and m3 on two gas resources; the first count listed three unit pairs ([#32](https://github.com/sentier-dev/sentier-bafu/issues/32)). |
| F19 asparagus seedling | — | open | Filed as [#41](https://github.com/sentier-dev/sentier-bafu/issues/41). |
| F21 gas combustion at 0.5 MJ/MJ | — | open | Filed as [#42](https://github.com/sentier-dev/sentier-bafu/issues/42). |
| F29 SO₂ in Ecological Scarcity 2021 | — | open | Filed as [#43](https://github.com/sentier-dev/sentier-bafu/issues/43). |
| F30 CAS on `Nitrogen` to water | — | open | Filed as [#44](https://github.com/sentier-dev/sentier-bafu/issues/44); a question, no double count shown. |
| F31 exchanges without a flow-list row | — | open | Filed as [#45](https://github.com/sentier-dev/sentier-bafu/issues/45); refines the withdrawn F4. For 2026 only the RAF name is a real difference: the uranium gap is in the 2025 flow list. |

Numbers follow the lci-bafu-catalog ledger, so F18, F20 and F22–F28, which have no issue here, are not listed. The five new findings were filed on 31 October and have not been re-measured by a second person; no patch applies to them.

## Asks and earlier interpretations kept

Each record's `retained` list keeps what a status change must not erase:
- **Asks:** the `aggregated` column (F8, #3), the question about 196588 (F10)
  and the `maintenance` column (F11, #4) for sentier-inventory.
- **Earlier interpretations:** the corrected mass-balance framing of F1, and
  the fixes originally filed with #29 (F14) and #31 (F16), which the
  re-measurement overturned.

## Patches without a finding

Patches 0004–0010 carry Brightway Flows corrections and links. No
sentier-bafu finding corresponds to them, and they are listed as such, so all
eleven patches are accounted for.

## What this does not establish

It does not verify that any patch reproduces BAFU's intended values, that a
pipeline run applied patches 0001–0003 (only patch 0011's run is cited), or
that reviewers reached consensus: those fields stay empty until evidence
exists. The check cannot confirm that the patch list is complete; that rests
on the pinned revision.
