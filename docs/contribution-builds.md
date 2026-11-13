# Building a contribution beside the patched release

A contribution that changes the inventory (a variant such as residual electricity mixes, a
rebuilt supply chain) is never applied to the patched release. It is built as a database of
its own: the patched release plus that one contribution, under the contribution's own name,
labelled Modified Data, with the contribution's id in its metadata. BAFU's numbers and the
patched release's numbers stay where they are; the variant stands beside them.

This page says how that works and what a contribution has to deliver to be built this way.
No real contribution is built yet. The mechanism is tested on a made-up release with a
made-up contribution (`release-build-tests/test_whole_path.py`, `test_layer.py`).

## What happens

```
python3 scripts/build_release.py build RELEASE OUT --contribution community/layers/C012-residual-electricity.json
python3 scripts/build_release.py compare PATCHED_BUILD OUT --out comparison.json
```

or, as part of the whole path, `python3 scripts/build_release.py release RELEASE OUT`, which
builds, after the patched release, every layer in `community/layers/` that names who
authorised it. A layer whose `authorised_by` is `null` is left out of a release run and
listed in it as skipped; it is built only when it is named with `--contribution`, and its
database and its exports then say "proposed, not authorised".

1. The patch tool, the adapter and the importer run as for the patched release.
2. The step `layer` applies the layer's changes to the importer's tables
   (`scripts/release_build/layer.py`) and writes `layer-receipt.json`: every input it
   changed, with its supplier before and after.
3. The database is written under the layer's own name. Its metadata carries the label
   Modified Data, the patch ids, and the contribution: id, name, title, author, authoriser,
   the SHA-256 of the layer file and its changes.
4. The audit checks, in the database, that every change the layer declares is there.
5. The comparison is made against the patched release: which rows the layer changed, and
   which scores moved because of it. A changed row that the layer does not account for
   fails the comparison. The layer accounts for an input only if its receipt lists that
   input, by dataset and position, with the supplier it had and the one it has: another
   changed input of a dataset the layer touches is unexplained. A patch that both builds
   carry explains no difference between them.
6. The exports are written from the contribution's database, under its name. Everything
   a reader sees names it as that contribution's database and never as the patched
   release: the statement inside every file, the record of modifications, the note of each
   dataset and the SimaPro project carry the contribution's id and whether somebody
   authorised it ("proposed, not authorised" if nobody has). Each dataset the layer changed
   lists the contribution among the steps that changed it, and a dataset that only the layer
   changed is in the record too.
7. The manifest lists the contribution in its own section, `contributions`, beside the
   patched release and not among its patches.

A build refuses to put a contribution into a database named `bafu-2026` or
`bafu-2026-v1-patched`. The refusal is in four places, so that no single mistake gets past
it: the layer file is not accepted with such a name, the entry point does not accept
`--database` beside `--contribution`, the step that marks the database stops, and the audit
fails a database of one of those names whose metadata names a contribution.

## The layer file

One JSON file per contribution, `community/layers/<id>-<name>.json`:

```json
{
  "schema": "sentier-bafu/contribution-layer/1",
  "contribution": "C012",
  "name": "residual-electricity",
  "database": "bafu-2026-v1-c012-residual-electricity",
  "title": "Consumers of the Swiss supply mix take the residual mix instead",
  "authored_by": "A person",
  "authorised_by": null,
  "references": ["https://github.com/sentier-dev/sentier-bafu/issues/0"],
  "release": {"fingerprint": "<input fingerprint of the provider release>"},
  "changes": [
    {
      "kind": "supplier-substitution",
      "dataset": {"code": "<code>", "name": "<name>", "location": "<location>"},
      "replaced_supplier": {"code": "<code>", "name": "<name>", "location": "<location>"},
      "new_supplier": {"code": "<code>", "name": "<name>", "location": "<location>"},
      "exchange": {"position": 4}
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `contribution` | The id of the contribution's record, `C<number>` |
| `name` | A short name in lower case; with the id it names the step, `C012-residual-electricity` |
| `database` | The database the build writes. It must contain the id (`c012`) and can't be a release's name |
| `title` | One sentence that says what the variant is; it goes into the record of modifications |
| `authored_by`, `authorised_by` | Who wrote the layer; who authorised building it, or `null` |
| `release.fingerprint` | Optional. The input fingerprint of the provider release the layer was written for (the run summary's `release.fingerprint`). The build stops on another release |
| `changes` | At least one change |

A dataset is named by its **code**, the part of its file name after `process_`, together
with its name and location **as the patched release has them** (a location that an import
fix rewrites is written in its rewritten form). The build stops if the release has another
name or location under that code: the layer was written for other data.

One kind of change exists, `supplier-substitution`: an input of `dataset` that is taken
from `replaced_supplier` is taken from `new_supplier` instead. The amount and the unit stay.
`exchange.position` (the place of the input among the dataset's exchanges, from 0) is only
needed when the dataset takes the replaced supplier more than once and not all of those
inputs change; without it, all of them change.

The build stops, and says which change it was, when: a dataset is not in the release; the
dataset has no input from the replaced supplier; the new supplier's unit is not the unit the
input declares (nothing is converted).

## What a real contribution has to deliver

For a variant such as residual electricity mixes:

1. **A contribution record** with an id (`community/contributions/C<number>.json`), of the
   class `variant`, with its evidence and its required checks. The layer file is the
   record's implementation, and the record names it in `layer.file`
   (`community/layers/<id>-<name>.json`). `python3 scripts/community.py check` refuses a
   record that names a file which is not there or cannot be read, a file that names another
   contribution, and a file in the folder that no record names.
2. **The layer file**, as above, written against the patched release it is to be built on.
3. **Every supplier it substitutes to must be a dataset of the release.** This is the
   limit of the mechanism today: a layer can re-route inputs between datasets that exist,
   and it can't add a dataset. A residual mix that is not in BAFU's release needs one of:
   - the new datasets as EcoSpold 1 files, with their own source, licence and a record of
     how each amount was derived, plus a second kind of change (`dataset-addition`) in
     `layer.py` that appends them to the importer's tables. Whether such files may be
     committed depends on what they were derived from; data derived from BAFU's inventory
     is under BAFU's terms;
   - or the residual mix expressed with existing datasets only (a consumer's one input
     from the supply mix replaced by several inputs from existing technology datasets),
     which needs a third kind of change (`supplier-split`: one input replaced by several,
     with shares that sum to one and the same unit).
   Neither kind exists yet. Both are small additions to `layer.py` and its tests, and each
   needs the comparison to know what it changes (`compare_builds.LAYER_FIELDS`).
4. **The shares and their source**, if the variant changes amounts: a substitution keeps
   the amount, so a layer that needs other amounts must say so in a change of its own kind,
   with the source of each number. The build never infers an amount.
5. **A name for the database** that says what it is, and a person who authorises building
   it. An unauthorised layer is built only when it is named, says "proposed, not
   authorised" in its database and its exports, is left out of a release run, and is not
   part of anything that is released.
6. **A statement of what the comparison should show**: which datasets' scores are expected
   to move, in which methods, and roughly by how much. The comparison lists every moved
   score with the step that explains it; the contribution's reviewers compare that with
   the statement. Nothing in the build decides whether the variant is right.

## What is verified, and what is not

Verified on the made-up release: a layer that substitutes one supplier is applied, the
database carries the contribution's name and id, the audit finds the change in the database,
the comparison attributes one changed row and one moved score to the layer and leaves the
patched release's score as it was, the exports name the contribution, and the manifest
lists it. The refusals above each have a test.

Not verified: a layer on BAFU's full release (no real layer exists), a layer with many
changes, and the two kinds of change that a residual mix would need.
