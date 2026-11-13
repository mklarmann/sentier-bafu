# Contribution layers

This folder holds one JSON file per contribution that changes the inventory, such as a variant with
residual electricity mixes. A file is named `<id>-<name>.json`, for example
`C012-residual-electricity.json`. No such file exists yet.

A contribution is never applied to the patched release. The release build
(`python3 scripts/build_release.py release`) builds every file in this folder as a database of its
own: the patched release plus that one contribution, under the contribution's own name. BAFU's
numbers and the numbers of the patched release stay as they are.

- The contribution's record, `community/contributions/C<number>.json`, names its file here in
  `layer.file`. `python3 scripts/community.py check` refuses a record that names a file which is
  missing or cannot be read, a file that names another contribution, and a file here that no record
  names.
- [docs/contribution-builds.md](../../docs/contribution-builds.md) describes the format of the
  file, what the build does with it and what a contribution has to deliver.
