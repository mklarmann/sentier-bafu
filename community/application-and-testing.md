# Apply and test BAFU/UVEK contribution layers

## Pin and retain the baseline

Use a named provider release and pin the public importer, inventory, methods and mappings. Save the sentier-brightway manifest and input hashes. Keep the baseline export and data root immutable. A baseline using Sentier mappings already contains those mappings; a candidate tests an additional change against that precise build.

## Existing hackathon candidate

The copied-process toolkit is in [sentier-models PR 2](https://github.com/sentier-dev/sentier-models/pull/2). Its implementation remains there; this repository retains the evidence, reproducible experiment and review. Pin the reviewed commit rather than treating an open PR as an accepted release:

```sh
mkdir -p .local
git clone https://github.com/sentier-dev/sentier-models.git .local/hackathon
git -C .local/hackathon fetch origin pull/2/head
git -C .local/hackathon checkout --detach a8c895d37b1ce5027733306eb95d60bb389cb31e
uv venv .local/toolkit-env
uv pip install --python .local/toolkit-env/bin/python -r .local/hackathon/hackathon/bafu-copied-processes/requirements.txt
.local/toolkit-env/bin/python .local/hackathon/hackathon/bafu-copied-processes/src/full_run.py --data-root ../sentier-inventory
```

Pin the inventory checkout to the contribution's baseline revision. The script reports failure counts but can still exit zero; inspect the content-round-trip failure count explicitly. This check covers the toolkit's selected families and columns with its stated numeric tolerance. It is not a full-inventory or LCIA parity claim.

For application testing, follow the toolkit's validate/rebuild_inventory.py and compare_multi.py instructions using a **copy** of the baseline data root. Export baseline and reconstructed candidate to separate paths with sentier-brightway; compare stock bw2calc scores across agreed products and methods. Never rebuild the canonical data root in place. Keep the baseline inventory pin aligned with the exported baseline; the installer's pinned cache can differ from the current inventory checkout.

**Checks run on 21 October 2026** ([run record](runs/hackathon-checks-2026-10-21.json)):
- **Round trip:** an exact comparison (no tolerance) across 766 families and 129,687 rows
  finds no mismatch, so the representation is lossless as claimed.
- **`forecast-held-out-validation` fails.** The rule was written before results were computed.
  With undefined F1 counted as 0 and the eight regional aggregates not scored as
  members, a simple baseline (technologies used by at least half the other members)
  scores F1 0.80 and MAE 0.050, against the MILP's 0.65 and 0.061.
- **`units-and-mass-balance` fails.** The sum-to-one constraint is applied to 90 families
  whose inputs share one unit; in 22 of them no member sums to one.
- **Score parity** was not run.
- **To install at all,** pin `pulp<4`: `pulp>=2.7` resolves to 4.1.0, which breaks the
  forecast. The toolkit also needs the inventory revision it was tested on, because
  sentier-inventory's layout changed on 13 October.

Forecasting is a different layer from lossless representation: test held-out products and locations, unit compatibility and physically meaningful share constraints; do not claim forecast outputs are source observations or mass-balanced merely because all inputs share a unit.

## Other contributions

Use existing importer plugins and ordered mapping packages. Pin their precedence, unit conversions, chemical identity and context, retain unresolved flows, and record intentional output changes. Keep source-inventory corrections distinct from representation, importer and mapping changes.

Record run summaries using community/templates/run-summary.json, compare equivalent summaries with scripts/community.py, then attach checks and public evidence to the contribution record. Numerical differences alone do not establish improvement.
