# BAFU mapping import: implementation and tracked work

Chris’s BAFU mapping work is feeding into the shared Sentier import routines.
Concrete fixes and discussion belong in repository issues and pull requests.
This page is a maintained entry point to those changes and the import contract.

## Source fixes available for review

Status: 12 October 2026. The Sentier changes are implemented and tested on their PR
branches; follow the PRs for review, CI and merge status. Catalog !25 has merged
(source `131369a`); its served release is unchanged.

| Import behavior | Implementation | Tracking |
|---|---|---|
| Reject non-positive/non-finite conversion factors before the BAFU mapping producer emits a package. | [sentier-importers #30](https://github.com/sentier-dev/sentier-importers/pull/30) | [sentier-bafu #14](https://github.com/sentier-dev/sentier-bafu/issues/14) |
| Check declared source units, reject invalid factors and refuse conflicting units for one target flow before export or database writes. | [sentier-brightway #4](https://github.com/sentier-dev/sentier-brightway/pull/4) | [sentier-bafu #14](https://github.com/sentier-dev/sentier-bafu/issues/14) |
| Refuse nonempty CF-fallback instructions that the current direct EF bridge cannot apply, rather than silently ignoring them. | [sentier-brightway #4](https://github.com/sentier-dev/sentier-brightway/pull/4) | [sentier-bafu #15](https://github.com/sentier-dev/sentier-bafu/issues/15) |
| Bind native BAFU exchanges to targets with compatible units in the Catalog importer. | [Catalog !25](https://gitlab.com/eos-lci/lci-bafu-catalog/-/merge_requests/25) | [Catalog #26](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/26) |

Sentier’s flow IDs already include the source unit and sub-compartment. The
Brightway consumer already multiplies mapped amounts and adjusts normal and
lognormal distributions. The added tests exercise actual file exports for
Bq→kBq, km→m and kWh→MJ, positive and negative amounts, distribution parameters
and bounds. Explicit zero CFs remain present in the exported method.

## Use the current import route

Use [sentier-importers](https://github.com/sentier-dev/sentier-importers) to
produce Sentier records and mapping packages, and
[sentier-brightway](https://github.com/sentier-dev/sentier-brightway) to consume
the pinned BAFU→EF 3.1 package. Keep the source flow identity and its unit;
one shared target flow must have one unit, with each source’s conversion
factor applied exactly once. Declared Bq→kBq, km→m and kWh→MJ mappings need
their explicit correct multiplier; missing/null factors cannot default these
magnitude changes to one. A unit/fallback refusal identifies a package,
entry or flow that needs fixing before the build can proceed.

**Comparison with BAFU's published results.** The score comparison of this route against BAFU's
published LCIA results, and where its differences come from, is in
[Evidence and build validation](build-validation.md#compare-scores-with-bafus-published-results).
It does not use C002's mapping, so C002's own comparison stays not run.

These fixes do not turn the current EF 3.1 bridge into a consumer of the
BAFU→openLCA 2.8.2 mapping. That integration remains
[C002](contributions/C002.json). Its next inputs are the pinned LCIA package
and executable scoring path, plus an explicit method/category policy for
ordered CF fallbacks, zero factors, units, directions and regions. Work on
that policy with Chris in [#15](https://github.com/sentier-dev/sentier-bafu/issues/15).
A candidate method still needs its own application and reproduction checks.
Source-code fixes to our importer can proceed independently of a provider’s
decision about an official distribution.

## Aggregated dataset list

The [F8 source list and counting criteria](findings.md#f8-the-list-behind-the-37-unflagged-candidates)
identify the 37 unflagged structural candidates, including their UUIDs. The
hackathon separately reports 22 of those candidates rebuilt. These counts
describe different stages; a comparison with another search should use the
dataset identifiers.

## Why this page remains

The existing `mapping-review.html` URL stays useful for links already shared.
It now points to implementation and issue status rather than a standalone
assessment of Chris’s reports. The earlier file-consistency receipt remains
in C002’s history; it does not establish score reproduction, adoption or team
consensus. [Import & use](../site/import.md) and
[application tests](application-and-testing.md) describe the general workflow.
