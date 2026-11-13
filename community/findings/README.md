# Finding records

One JSON file per finding: `<number // 1000>/F<number>.json`, for example `0/F31.json` and
`3/F3120.json`. A thousand files to a folder stays browsable.

**What a record holds.** What was observed and how it was measured, the datasets and releases
it concerns, and dated evidence of what happened to it: who reported it, who repeated the
measurement, when it was reported to BAFU, what BAFU answered, and which release corrects it.
A record holds no status. The status is computed from the evidence, so nobody has to keep a
status, a flag and the issue's labels in agreement. The fields are described in
[`schema/finding.schema.json`](../../schema/finding.schema.json), and
`python3 scripts/community.py check` validates every record against it.

**How a record is created.** A finding starts as an
[issue](https://github.com/sentier-dev/sentier-bafu/issues/new?template=bafu-data-finding.yml).
Its number is the number of the issue: issue 48 becomes `F48`. F1 to F32 follow an older
numbering and keep their ids. A pull request then adds one file here, from the
[template](../templates/finding.json), and a person reviews and merges it.

**How evidence is added.** People add evidence, never a status. Each command writes the
records it names and nothing else:

```sh
python3 scripts/community.py repeat F48 --by <login> --date 2026-12-01 --url <comment> --result reproduced
python3 scripts/community.py send --batch 2026-12 --date 2026-12-05 --url <where it is said> F48 F51
python3 scripts/community.py answer F48 --outcome confirmed --date 2026-12-20 --summary "BAFU said …" --url <comment>
python3 scripts/community.py fixed F48 --release 2027-v1 --date 2027-03-01 --url <the check>
python3 scripts/community.py close F48 --as withdrawn --reason "…" --date 2026-12-02
```

A second measurement comes from a second person; the command refuses the reporter. BAFU's
answer is written in our own words, attributed to BAFU, without a person's name.

**Where the list is published.** The [site](https://sentier-dev.github.io/sentier-bafu/findings.html)
shows every record with its discussion. The build also publishes a one-line-per-finding table,
[`ledger.md`](https://sentier-dev.github.io/sentier-bafu/ledger.md), and the same list for tools,
[`api/v1/findings.json`](https://sentier-dev.github.io/sentier-bafu/api/v1/findings.json). No
generated list is kept in the repository, so a pull request that adds a finding touches one file.

Community patches are not copied into records. [`../patches.json`](../patches.json) lists them
with the findings they answer.
