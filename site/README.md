# Public site

The site is built from the records, not written by hand:

- one page per finding (`community/findings/<number // 1000>/F<number>.json`) and per contribution (`community/contributions/C*.json`), so it holds thousands of them;
- a findings list with search and a status filter, and the status counts on the overview;
- the prose pages named in `site/config.json`. `<!-- findings-list -->` and `<!-- contributions-list -->` in a page mark where a list goes.

A finding record holds dated evidence and no status. The status is computed from the evidence when the site is built. GitHub adds what only the tracker knows: comment counts, last activity, and issues filed as findings that have no record yet (shown by number only). Without network access the site builds from the records alone; `--offline` forces that, `--issues FILE` reads a snapshot, and `--require-issues` fails the build when GitHub cannot be read, which the deploy uses so a failed read keeps the last published site.

```sh
uv run --no-project --with markdown==3.7 scripts/build_site.py
python3 scripts/check_site.py _site
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

The build validates every record first, with the rules of `python3 scripts/community.py check`, and writes nothing while a record is invalid. It names the file and the rule. The page writer also refuses any path outside the output folder.

`_site/` is ignored. Inventory files, licensed data and private evidence are never build inputs, and `check_site.py` refuses data file types in the output.

[The Documentation workflow](../.github/workflows/pages.yml) deploys to GitHub Pages after a push to `main`, once a day, and when an issue is opened, closed or relabelled. Pull requests build and check the site without deploying it.

The design follows [Départ de Sentier's website](https://www.d-d-s.ch/): the green logo from [Depart-de-Sentier/dds-logo](https://github.com/Depart-de-Sentier/dds-logo) by Sylvain Prevost (CC BY 4.0), Nunito from [Google Fonts](https://github.com/google/fonts/tree/main/ofl/nunito) under `site/assets/OFL.txt`, dark green `#3C5343`, beige `#F0EEE1` and sage `#84AE99`. The renderer and stylesheet are meant to be shared with the sibling dataset sites; dataset-specific text lives in `site/config.json` and the Markdown sources.

## Words

The public word for where a finding stands is **status**, and the site shows it in words. The keys below stay inside the code, the JSON and `data-stage` attributes. Texts carry a `{provider}` placeholder; the name comes from `provider` in `site/config.json`.

| Key | Status shown | Reached when the record has |
|---|---|---|
| `filed` | Needs a second measurement | nothing but `reported` |
| `confirmed` | Repeated, not yet reported | `repeated` with result `reproduced`, by someone other than the reporter |
| `sent` | Reported to BAFU | `sent` |
| `answered` | Answered by BAFU | `answer` |
| `fixed` | Corrected by BAFU | `fixed_in` |
| `not-a-defect` | For information | `closed.as = "not-a-defect"` |
| `withdrawn` | Withdrawn | `closed.as = "withdrawn"` |

The status is the first that applies of `closed`, `fixed_in`, `answer`, `sent`, `repeated`; otherwise the finding is `filed`. A community patch and BAFU's answer are facts beside the status, never a status.

Provider releases are a fixed list in `site/config.json` (`releases`: id and name). Records name releases by id; registering a new BAFU release is one line there.

## Interface for page builders

Everything a page needs comes from two modules. Neither is specific to a template.

`scripts/community.py` (records, standard library only):

| Call | Gives |
|---|---|
| `problems(root)` | `(errors, notes, summary)`: every error in the records. The build refuses on any. |
| `load_config(root)` | `provider`, `repository`, `site_url`, `releases` |
| `load_findings(root)` | every finding record in number order; `record.path` is its file in the repository |
| `load_contributions(root)` | every contribution record; `record.path` likewise |
| `load_patches(root)` | `community/patches.json`: the community patches with the findings they answer |
| `stage(record)` | the status key of a finding |
| `STATUSES`, `statuses(provider)` | the vocabulary in path order: `key`, `label`, `description` (one sentence, true of every finding with that status) |
| `status_label(key, provider)`, `status_description(key, provider)` | the words for one key |
| `KINDS`, `OUTCOMES`, `DATASET_ROLES` | kind of a finding, outcome of BAFU's answer, role of a listed dataset, each with its words |
| `CONTRIBUTION_CLASSES`, `CONTRIBUTION_GROUPS` | class of a contribution; the group says whether it can enter the patched release or stands beside BAFU's numbers |
| `evidence(record)` | the dated evidence of a record, oldest first: `(date, name, block)` |
| `last_change(record)` | date of the newest evidence: when the finding changed, not when its issue did |
| `waiting_since(record)` | that date while the finding is still on the path; `None` once it is corrected or closed |
| `changes(findings)` | every dated event of every finding, newest first: for a "what changed" page or a feed |
| `related(findings)` | `{id: [ids]}` in both directions; a record names a relation on one side only |
| `patches_by_finding(patches)`, `patches_without_finding(patches)` | the join of patches and findings |
| `dataset_index(findings, patches)` | `{code: {name, location, findings: [{id, role}], patches}}` |
| `release_index(findings, config)` | `{release id: {name, findings, corrected}}` |
| `concerns(record)`, `release_names(record, config)`, `discussion_links(record, repository)` | one-line texts and links for lists |
| `index_text(findings, config)` | the one-line-per-finding table published as `ledger.md` |

`scripts/triage.py` (records joined with the tracker):

| Call | Gives |
|---|---|
| `load_issues(repository, snapshot, offline, require)` | the finding issues from GitHub or a snapshot |
| `assemble(findings, repository, issues, patches)` | `findings`: every record as a dict plus `stage`, `path`, `tracker` (the issue's data or `None`), `patches`, `related`, `changed`, `waiting_since`; `counts` by status key; `unlisted`: finding issues without a record; `without_issue`; `label_differences` |
| `expected_labels(stage)` | the labels a record's issue should carry |

`label_differences` is for maintainers and for a job that writes labels from records. The build prints a one-line summary in its log and puts nothing about labels on a page.

A dataset in a record has a `role`: `subject` (the default: the observation is in this dataset), `affected` (a consumer whose result changes) or `named` (a supplier or a comparison the text names). The dataset index carries all three, so a lookup by code cannot miss; a page decides which to show.

## Machine-readable outputs

Coordination data only; no inventory rows.

| File | Content |
|---|---|
| `api/v1/findings.json` | the status vocabulary and one entry per finding: `id`, `issue`, `title`, `kind`, `status`, `status_label`, `datasets` (codes), `scope`, `releases`, `patches`, `answer_outcome`, the date of each step, `changed`, `waiting_since`, `url`, `json` |
| `api/v1/findings/F<n>.json` | the full record and what is derived from it: status, patches, related findings, dates, the issue's activity |
| `api/v1/datasets.json` | `{code: {name, location, findings: [{id, role}], patches}}` |
| `api/v1/contributions.json` | the classes and one entry per contribution |
| `api/v1/status.json` | counts by status and the identity of the build |
| `schema/finding.schema.json`, `schema/contribution.schema.json` | the JSON Schema of the records, the same files `community.py check` validates against |
| `ledger.md` | the one-line-per-finding table |
| `findings.json`, `status.json` | at the root, in their earlier shape, for readers that have not moved to `api/v1` |

Inside `api/v1` a field is never renamed or removed; fields may be added. A change that breaks a reader gets `api/v2` beside it.
