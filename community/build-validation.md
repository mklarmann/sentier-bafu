# Evidence and build validation

An import that links every exchange can still score incorrectly. Use three separate checks: **exchange reconciliation**, **characterization coverage**, and **equivalent-scope result comparison**. The shared audit tools were added following [lci-bafu-catalog's importer-parity discussion](https://github.com/sentier-dev/sentier-bafu/issues/2) and [method/build-identity findings](https://github.com/sentier-dev/sentier-bafu/issues/5).

## Account for every changed row

Report process, production, technosphere and biosphere counts at the source, imported and served stages. Each change needs a unique id, transition, exchange kind, signed row-count delta, reason and evidence link. The audit fails if the measured delta differs from the recorded changes. An equal total alone does not establish parity: compare stable exchange identities, amounts, units, compartments and declared supplier locations as well.

Keep declared supplier geography separately from resolved target geography. Stable dataset identifiers should determine links where available; a link resolved by identifier does not erase contradictory source metadata. Preserve raw lifecycle and aggregation signals rather than burying them in comments or assuming a sector folder captures retirement.

The reported BAFU counts and exceptions in [issue #2](https://github.com/sentier-dev/sentier-bafu/issues/2) are the investigation baseline, not an already reconciled result. The 22-row served difference and one technosphere-row difference still need named explanations. The flags and structural aggregation counts in [issue #3](https://github.com/sentier-dev/sentier-bafu/issues/3) also need identity lists and overlap accounting before they become acceptance thresholds.

## Check characterization, not just linking

For each method, list the emitted flow keys, the flow keys required by its documented policy, the actual factors and explicit exclusions with evidence. Use complete identities (database/code, compartment, unit and region as appropriate), not substance name alone. **A supplied zero factor counts as characterized; an absent factor does not.** Never infer fossil versus non-fossil methane or copy an AR6 factor into EF 3.1 without the method source.

The required-flow list must come from the measured final inventory and a cited method policy. This tool checks the submitted audit; it cannot prove that a manually supplied inventory list is complete. Named exception evidence is still subject to review.

```sh
python3 scripts/build_checks.py path/to/build-audit.json
```

Start with [the synthetic audit example](../community/templates/build-audit.json). It demonstrates the format; its values and hashes are synthetic and certify no dataset build. A failed audit exits nonzero.

### Measured BAFU export audit

`audit_registry.py` reads the final parquet registry produced by sentier-brightway. It checks manifest counts, consumer/target identities, finite amounts and CFs, duplicate factors and core CO2/CH4/N2O air-flow coverage in the headline EF 3.1 climate method. It reports missing coverage for every method without assuming that every substance should receive a factor in every category. It emits counts and hashes, not inventory amounts or factor tables.

```sh
uv run --no-project --python 3.12 --with pandas==2.2.3 --with pyarrow==19.0.1 scripts/audit_registry.py path/to/export --out .local/new-audit.json
```

The usage line in the script's docstring omits `--no-project --python 3.12`; the script is left unchanged because the export audit pins its SHA-256. Use the command above.

The [measured export audit](runs/bafu-export-audit.json) passed on the previously generated, pinned baseline: **11,947 processes; 11,947 production, 114,369 technosphere and 293,747 biosphere exchanges**. All 420,063 exchange rows were retained in this exported registry. No missing core-gas factors were found under the stated policy. The report records input source pins, script and artifact hashes and per-method coverage.

This establishes registry counts and identities, not raw ecoSpold parity, factor correctness, full greenhouse-gas coverage or LCIA score parity. In particular, the reported lci-bafu served-build differences remain unresolved. The script refuses to overwrite an evidence file.

## Pin the inputs and the outputs

Keep source hashes and implementation revisions alongside actual SHA-256 hashes of output files. Hash the complete file bytes locally, for example with `shasum -a 256 path/to/output`.

The audit emits a **summary_sha256** over the dataset, scope, counts, changes, characterization audit, probes and applied packages. It ignores timestamps, serving locations and importer revisions, canonicalizes probe floats to 12 significant digits, and sorts unordered identity lists. That makes aggregate summaries comparable across rebuilds with negligible floating-point noise. It is a summary identity, **not a hash of the complete inventory** and not proof of numerical equivalence. The exact output-file hashes remain separate and may differ across platforms. Record score tolerances explicitly in the application test.

## Validate the contribution's actual claim

- **Import or mapping repair:** reproduce source identity and amounts; explain every added, removed, converted or redirected exchange; compare coverage and scores.
- **Representation/compression:** demonstrate lossless reconstruction within stated tolerances across the complete claimed columns, and score parity. A successful family round-trip alone is not an LCIA validation.
- **Disaggregation/reconstruction:** give the new inventory its own identity. Compare against the aggregated original; even a high mass-coverage ratio does not imply matching impacts.
- **Scenario or forecast:** hold scope fixed and record assumptions, uncertainty and held-out validation. A scenario is not automatically a correction of the provider's source dataset.

Publish only permitted aggregate evidence and metadata. Inventories, licensed background files and confidential partner evidence stay local. A passing technical check is not partner consensus; [the review workflow](workflow.md) records those decisions separately.
