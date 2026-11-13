# Contributions

A contribution is a proposal that goes beyond a single finding: a mapping, a model, a rebuilt inventory, or a method variant such as residual electricity mixes. It comes with its evidence and with the checks it must pass.

A contribution never replaces BAFU's numbers. Some kinds can enter the [patched release](patched-release.md). The others stand beside BAFU's release under their own name.

<!-- contributions-list -->

## Kinds of contribution

What a change does to BAFU's release decides where it can go.

**Can enter the patched release**

- **Import fix.** A preparation that every reader of the release files needs, such as schema repairs, unique exchange numbers and valid location codes. The patch tool records each import fix on the datasets it changes.
- **Linking repair.** An input names a supplier that cannot be found. The input is linked to the dataset that exists. Example: in [F3](../community/findings/0/F3.json), inputs name the location `ENTSO`, and the suppliers are registered as `ENTSO-E`.
- **Re-declaration.** A unit or a label that BAFU's own change log corrects. The change log is the evidence.

**Stands beside BAFU's numbers**

- **Variant.** A method variant or a data variant, such as a residual electricity mix.
- **Model.** A model or a rebuilt inventory. It is a new inventory with its own tests.
- **Mapping.** A correspondence between flows, datasets or methods.

A contribution of the second group keeps its own name, so that users choose it knowingly. It can be excellent and still not be BAFU's number.

An amount that BAFU has not confirmed does not enter the patched release. The three amounts that patch 0001 changes are the ones that BAFU gave in its answer to [F1](../community/findings/0/F1.json). A workaround in one user's own inventory does not belong in this workspace.

## How a contribution moves

A contribution is **proposed**, then **testing**, then **reviewing**. It ends as **accepted**, **rejected** or **superseded**.

1. **Propose.** Open a [contribution issue](https://github.com/sentier-dev/sentier-bafu/issues/new?template=community-contribution.yml). A record is added to the repository in a pull request. It names the BAFU release the work is based on, the exact version of the code or files, and the checks the contribution must pass.
2. **Build beside, never in place.** BAFU's release and the changed version are built separately, from the same inputs.
3. **Test.** The checks that the record names are run, and each result is attached with a link. A check that failed or was not run stays visible on the contribution's page. [How builds are checked](../community/build-validation.md) describes the checks on a build.
4. **Review.** The record names the reviewers. They approve the exact version that was tested. Objections are recorded with their answers. A contribution without named reviewers cannot be accepted.
5. **Decide.** A contribution can be accepted only when every required check has passed and every named reviewer has approved. An accepted contribution may become a recommendation to BAFU. BAFU decides what it does with it.

## What review means here

- People approve. An automated check verifies the record, not the science.
- An approval names the BAFU release and the exact version it covers. It does not carry over to a later version.
- Nobody is named as a reviewer or contact without their agreement. Silence is not consent.
- A merged pull request is not BAFU's endorsement.

The working document for contributors is [the contribution workflow](../community/workflow.md) in the repository. It describes the record, the commands and how a recommendation is recorded.
