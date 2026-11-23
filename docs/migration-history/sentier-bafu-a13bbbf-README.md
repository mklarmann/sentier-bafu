<p><img src="site/assets/sentier.svg" alt="sentier.dev" width="160"></p>

# BAFU / UVEK · a shared dataset workspace

**Reproduce the import. Bring contributions into application and testing. Build reviewed consensus and return actionable recommendations to BAFU.**

This public Sentier project connects partner evidence, Brightcon hackathon work, candidate improvements and the discussion around BAFU/UVEK. It spans releases and preserves the provider's canonical source alongside traceable, separately identified candidate layers.

[Import & use](site/import.md) · [Findings ledger](community/findings.md) · [Evidence & testing](community/build-validation.md) · [Contribute](community/README.md) · [Consensus](community/workflow.md)

## Consolidating the community work

The [migration and UX plan](docs/plans/bafu-community/README.md) brings the
working [community-fixes pipeline](https://github.com/sentier-dev/bafu-community-fixes)
and this evidence workspace together. Community-fixes is authoritative where
they conflict. Its package and commands stay stable; migration parity and the
new review experience are tracked as separate tasks. The pipeline has not yet
been merged into this repository. See the [consolidation issues](https://github.com/sentier-dev/sentier-bafu/issues/18)
and the [architecture decisions](docs/adr/).

## Start with the import

[Sentier importers](https://github.com/sentier-dev/sentier-importers) parses the provider release. [Inventory](https://github.com/sentier-dev/sentier-inventory), [methods](https://github.com/sentier-dev/sentier-methods) and [mappings](https://github.com/sentier-dev/sentier-mappings) hold the derived artifacts; [sentier-brightway](https://github.com/sentier-dev/sentier-brightway) builds the pinned application baseline.

```sh
git clone https://github.com/sentier-dev/sentier-brightway.git
cd sentier-brightway
uv sync
uv run sentier-brightway coverage
uv run sentier-brightway files --out ../bafu-baseline
```

Record the release, input hashes, manifest pins and residual coverage. The build includes its pinned mappings and transformations; treat it as a derived build. Obtain raw exports under the provider's terms for regeneration. The redistribution basis for the full published inventory remains [open in issue #1](https://github.com/sentier-dev/sentier-bafu/issues/1); read [data and attribution](docs/terms-of-use.md) before sharing builds.

## Bring evidence, then test the claim

| Step | What belongs here |
|---|---|
| Canonical import | Source release, identifiers, hashes and reproducible import path |
| Partner contributions | Findings, proposed mappings, models and scenarios with evidence |
| Application & testing | Separate candidates, named exchange changes, coverage and score comparisons |
| Reviewed consensus | Actual reviewer decisions, objections and their disposition |
| Recommendations to BAFU | Agreed findings, delivery evidence and provider responses |

A **finding** starts with the source release, dataset code, what you measured and how. Read [the ledger](community/findings.md), then [open an issue](https://github.com/sentier-dev/sentier-bafu/issues/new/choose). Reproduce observations against the provider's source files before concluding that BAFU's data is wrong. An importer defect belongs to the component that introduced it.

A **contribution layer** gets a [record](community/templates/contribution.json), isolated candidate build and [validation plan](community/build-validation.md). A reconstruction of an aggregated inventory is a new inventory claim; representation parity, inventory correction and forecasting require different tests.

## Current work

- The [hackathon copied-process contribution](community/contributions/C001.json) remains proposed. Its [round-trip run](community/runs/hackathon-roundtrip.json) passed across 766 families; units/mass balance, score parity and held-out forecasting validation remain open.
- The [lci-bafu-catalog findings](community/findings.md) connect source observations with their discussion threads. [Importer parity](https://github.com/sentier-dev/sentier-bafu/issues/2), [aggregation](https://github.com/sentier-dev/sentier-bafu/issues/3), [maintenance](https://github.com/sentier-dev/sentier-bafu/issues/4) and [method/build identity](https://github.com/sentier-dev/sentier-bafu/issues/5) have separate evidence and follow-up requirements.
- The [measured BAFU export audit](community/runs/bafu-export-audit.json) passes identity/count checks and core-gas characterization coverage on the pinned 420,063-row registry; it does not claim raw-source or score parity.
- Shared tooling checks named row-count deltas, required characterization, exact artifact-hash metadata and portable summary identity. Passing a supplied audit does not establish source parity or partner agreement.

```sh
python3 scripts/community.py check
python3 -m unittest discover -s community/tests
python3 scripts/build_checks.py path/to/build-audit.json
```

The [synthetic audit example](community/templates/build-audit.json) is a format demonstration, not a measured BAFU build.

## Documentation site

**[Open the BAFU / UVEK site](https://sentier-dev.github.io/sentier-bafu/).** The responsive site shares Sentier's visual identity with [the AGRIBALYSE review preview](https://mklarmann.github.io/sentier-agribalyse/). Its public pages cover import, findings, application tests and consensus. The [Documentation workflow](.github/workflows/pages.yml) checks pull requests and publishes updates from `main` to GitHub Pages. Build locally with `uv run --no-project --with markdown==3.7 scripts/build_site.py`; see [site maintenance](site/README.md). Generated pages contain coordination material only, with no inventory downloads.

## Data, credit and participation

Original code and documentation are MIT. Source datasets retain their own terms, attribution and modification requirements. Keep restricted exports and confidential partner evidence local. No new reviewer consensus, sent recommendation or provider endorsement is implied by the workspace. See [the workflow](community/workflow.md), [recommendation tracker](community/recommendations/tracker.json) and [terms](docs/terms-of-use.md).
