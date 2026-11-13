# Contribution workflow

This is the working document for people who propose, test or review a contribution. The site's [Contributions](https://sentier-dev.github.io/sentier-bafu/contributions.html) page lists the contributions and gives the short version of this text.

A contribution is a proposal that goes beyond a single finding: a mapping, a model, a rebuilt inventory, or a method variant such as residual electricity mixes. It comes with its evidence and with the checks it must pass. A contribution never replaces BAFU's numbers.

## Kinds of contribution

What a change does to BAFU's release decides where it can go. The record names the kind in its field `class`.

| `class` | Kind | Where it can go |
|---|---|---|
| `import-fix` | **Import fix.** A preparation that every reader of the release files needs, such as schema repairs, unique exchange numbers and valid location codes. | Can enter the patched release |
| `linking-repair` | **Linking repair.** An input names a supplier that cannot be found, and is linked to the dataset that exists. | Can enter the patched release |
| `re-declaration` | **Re-declaration.** A unit or a label that BAFU's own change log corrects. The change log is the evidence. | Can enter the patched release |
| `variant` | **Variant.** A method variant or a data variant, such as a residual electricity mix. | Stands beside BAFU's numbers, under its own name |
| `model` | **Model.** A model or a rebuilt inventory: a new inventory with its own tests. | Stands beside BAFU's numbers, under its own name |
| `mapping` | **Mapping.** A correspondence between flows, datasets or methods. | Stands beside BAFU's numbers, under its own name |

A contribution that stands beside BAFU's numbers says what it replaces, how, and how well. It can be excellent and still not be BAFU's number, so it keeps its own name and users choose it knowingly.

An amount that BAFU has not confirmed does not enter the patched release. A workaround in one user's own inventory does not belong in this repository.

lci-bafu-catalog, a separate public project that imports the same release, sorts changes into classes A to E. A is an import fix, B a linking repair, C a re-declaration, D a value change or a variant, and E a workaround in a user's own inventory.

## The record

A contribution has one record, `contributions/C<number>.json`. Start it from the [template](templates/contribution.json). The fields and their rules are in [the schema](../schema/contribution.schema.json), and `python3 scripts/community.py check` validates every record against it.

The record holds:

- the number, a title that names the thing proposed, the kind and the status;
- the BAFU release the work is based on, with the repository and revision of the import and the checksums of its inputs;
- the changed version: where its code or files are, and their exact revision or checksum;
- the checks the contribution must pass, and every run with the result of each check and a public link to the evidence;
- the reviewers, their approvals of an exact version, and objections with their answers;
- what the checks cover and what they do not cover, the next step and who takes it.

## Status

A contribution is **proposed**, then **testing**, then **reviewing**. It ends as **accepted**, **rejected** or **superseded**.

## Steps

1. **Propose.** Open a [contribution issue](https://github.com/sentier-dev/sentier-bafu/issues/new?template=community-contribution.yml). Add the record in a pull request.
2. **Build beside, never in place.** Build BAFU's release and the changed version separately, from the same inputs, at exact revisions. Keep both builds in a local folder that is not committed, such as `.local/`.
3. **Test.** Run the checks that the record names. Add each result to the record, with a public link to its evidence. A check that failed or was not run stays in the record. [How builds are checked](build-validation.md) describes the checks on a build, and [application-and-testing.md](application-and-testing.md) shows the steps for C001.
4. **Review.** The reviewers named in the record approve the exact version that was tested. An objection is recorded with its answer and a link.
5. **Decide.** A maintainer sets the status. `check` refuses the status `accepted` when a required check has not passed with public evidence, when a named reviewer has not approved the exact version that was tested, or when an objection has no answer.
6. **Recommend.** An accepted contribution may become a recommendation to BAFU. BAFU decides what it does with it.

To compare two builds, write a run summary for each from the [template](templates/run-summary.json) and run:

```sh
python3 scripts/community.py compare bafu-release-summary.json changed-version-summary.json --out .local/comparisons/example.json
```

The command refuses two summaries that are not based on the same build of BAFU's release, or that differ in scope or in the set of measured quantities. It reports the difference for each quantity. It does not decide whether a change is right. That takes evidence and review.

## What review means here

- People approve. An automated check verifies the record, not the science.
- An approval names the BAFU release and the exact version it covers. It does not carry over to a later version.
- Nobody is named as a reviewer or contact without their agreement. Silence is not consent.
- A merged pull request is not BAFU's endorsement.

## Recommendations to BAFU

[`recommendations/tracker.json`](recommendations/tracker.json) lists the recommendations. A recommendation is `draft`, then `ready`, `sent`, `acknowledged` and `resolved`. `check` refuses `ready` unless the contribution is accepted and the recipient is named. It refuses `sent` without a link that shows the delivery, and `acknowledged` without a link to the answer.
