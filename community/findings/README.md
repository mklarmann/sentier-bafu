# Finding records

One JSON file per finding, named after its number: `F31.json`.

A record holds what was observed, on which datasets and releases, how it was measured, where it
is discussed and what happens next. `python3 scripts/community.py check` validates every record.

**How a record is created.** A finding starts as an
[issue](https://github.com/sentier-dev/sentier-bafu/issues/new?template=bafu-data-finding.yml).
A pull request then adds one file here, from the [template](../templates/finding.json), and a
person reviews and merges it.

**Where the list is published.** The [site](https://sentier-dev.github.io/sentier-bafu/findings.html)
shows every record with its discussion. The build also publishes a one-line-per-finding table,
[`ledger.md`](https://sentier-dev.github.io/sentier-bafu/ledger.md), and a machine-readable
[`findings.json`](https://sentier-dev.github.io/sentier-bafu/findings.json). No generated list is
kept in the repository, so a pull request that adds a finding touches one file.
