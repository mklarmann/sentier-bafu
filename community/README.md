# Take part

There are three ways in. Each starts with an issue, so the discussion is public and linked from the [site](https://sentier-dev.github.io/sentier-bafu/).

## Report a finding

You measured something in BAFU's data that cannot be right, or that you cannot explain.

1. [Open a finding](https://github.com/sentier-dev/sentier-bafu/issues/new?template=bafu-data-finding.yml) with the dataset code, the release, what you measured and how, and why it cannot be right.
2. It gets a number and a record in [findings/](findings/), from the [template](templates/finding.json). The record is marked as awaiting a second measurement and names the next action and who owns it.
3. A second person repeats the measurement on BAFU's release files, never on an import. Then the mark and the `needs-triage` label come off.
4. Findings go to BAFU in batches. BAFU decides what it changes. Its answer is recorded, and so is the release that contains a correction.

A finding that does not survive re-measurement stays in the ledger as withdrawn, so nobody finds it again.

## Propose a contribution

A correction that is not yet a patch, a mapping, a model, a rebuilt inventory or a method variant. [Open a contribution](https://github.com/sentier-dev/sentier-bafu/issues/new?template=community-contribution.yml) and add a record. [Contributions](workflow.md) explains the classes, the steps and what review means.

## Re-measure or review

The most useful help is a second pair of eyes. Take a finding that is [awaiting a second measurement](https://sentier-dev.github.io/sentier-bafu/findings.html#stage-needs-triage), repeat it on the release files and say what you got in its issue. Or review an open pull request.

Not sure where something belongs? [Start a discussion](https://github.com/sentier-dev/sentier-bafu/issues/new?template=discussion.yml).

## Rules we keep

- Measure on BAFU's release files. Say what you measured and what you did not.
- Quote dataset names and values. Never paste text from BAFU's LCI reports.
- No confidential material, restricted exports or private correspondence.
- People review and merge. Work done by an agent says so.
- Nothing here implies BAFU's endorsement.

## Check a change

```sh
python3 scripts/community.py check   # the records and the generated ledger
python3 scripts/community.py index   # regenerate community/findings.md after editing a record
python3 -m unittest discover -s community/tests
```

To compare a candidate build with its baseline:

```sh
python3 scripts/community.py compare baseline-summary.json candidate-summary.json --out .local/comparisons/example.json
```

A comparison reports differences. It does not decide whether a change is right; that takes evidence and named reviewers.
