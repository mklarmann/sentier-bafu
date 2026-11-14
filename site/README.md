# Public site

The site is built from the records, not written by hand:

- one page per finding (`community/findings/<number // 1000>/F<number>.json`) and per contribution (`community/contributions/C*.json`), so it holds thousands of them;
- one page per dataset a finding names (`datasets/<code>.html`), per BAFU release (`releases/<id>.html`) and per report to BAFU (`feedback/<batch>.html`);
- the overview, what changed (`changes.html`, `feed.xml`), housekeeping for maintainers, the sitemap;
- the prose pages named in `site/config.json`, written in Markdown, with generated blocks where a marker asks for one.

A finding record holds dated evidence and no status. The status is computed from the evidence when the site is built. GitHub adds what only the tracker knows: comment counts, last activity, and issues filed as findings that have no record yet (shown by number only). Without network access the site builds from the records alone; `--offline` forces that, `--issues FILE` reads a snapshot, and `--require-issues` fails the build when GitHub cannot be read, which the deploy uses so a failed read keeps the last published site.

The repository root also holds the patch tool's package, `bafu-community-fixes`, which needs Python 3.14 (`.python-version`). The site tooling runs on Python 3.12 outside that project, so pass `--no-project --python 3.12` to `uv run`, as the workflows do.

```sh
uv run --no-project --python 3.12 --with markdown==3.7 python scripts/build_site.py --offline --out _site
uv run --no-project --python 3.12 python scripts/check_site.py _site
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

The build validates every record first, with the rules of `python3 scripts/community.py check`, and writes nothing while a record is invalid. It names the file and the rule. The page writer also refuses any path outside the output folder. Two builds of one revision on one day are identical; set `SOURCE_DATE_EPOCH` to fix the day. A rebuild removes every file an earlier build wrote and this one does not.

`_site/` is ignored. Inventory files, licensed data and private evidence are never build inputs, and `check_site.py` refuses data file types and any XML file other than the feed and the sitemap.

[The Site workflow](../.github/workflows/pages.yml) deploys to GitHub Pages after a push to `main`, once a day, and when an issue is opened, closed or reopened. Pull requests are built and checked by [the Checks workflow](../.github/workflows/checks.yml), without the network and without deploying. [docs/automation.md](../docs/automation.md) describes every workflow.

The design follows [Départ de Sentier's website](https://www.d-d-s.ch/): the green logo from [Depart-de-Sentier/dds-logo](https://github.com/Depart-de-Sentier/dds-logo) by Sylvain Prevost (CC BY 4.0), Nunito from [Google Fonts](https://github.com/google/fonts/tree/main/ofl/nunito) under `site/assets/OFL.txt`, dark green `#3C5343`, beige `#F0EEE1` and sage `#84AE99`. The renderer and stylesheet are meant to be shared with the sibling dataset sites; dataset-specific text lives in `site/config.json` and the Markdown sources.

## Where things are

| File | What it is |
|---|---|
| `scripts/build_site.py` | reads the inputs, decides which pages exist, writes them |
| `scripts/sitebuild/` | the templates, one function per component: `shell` (frame), `prose` (Markdown, tables, step lists), `status` (tracker, meter, status links), `findings`, `contributions`, `overview`, `pages` (feedback, releases, datasets, changes, housekeeping), `data` (JSON outputs) |
| `scripts/triage.py` | the records joined with the issue tracker; `steps(record)` places a finding on its path |
| `scripts/check_site.py` | checks the built site: links, anchors, ids, page basics, JSON and XML, no inventory files |
| `site/style.css` | the stylesheet: tokens first, then one section per component |
| `site/assets/list.js` | search, filters and sorting of the lists; the only script |
| `site/assets/nunito-latin.woff2` | the font, a Latin subset of `site/font/nunito.ttf` (command below) |
| `site/config.json` | name, navigation, footer, the prose pages, the assessment files, the redirects |
| `community/tests/test_site.py` | the tests of the build |

The font subset is made once and committed. To make it again:

```sh
uv run --no-project --python 3.12 --with fonttools==4.55.0 --with brotli==1.1.0 \
  pyftsubset site/font/nunito.ttf --flavor=woff2 --layout-features='*' \
  --unicodes="U+0020-007E,U+00A0-024F,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2070-209F,U+20AC,U+2122,U+2212,U+2215,U+2248,U+2260-2265" \
  --output-file=site/assets/nunito-latin.woff2
```

Nunito has no arrows: the stylesheet draws them. Do not type "→" or "↗" into generated text.

## A sibling site

The scripts in `scripts/`, the stylesheet and the two scripts of the pages are the same files in every dataset's repository. What differs from one dataset to another is said in `site/config.json`, and a test builds a made-up sibling from these files (`community/tests/test_sibling_site.py`). A key that is left out has the value in the last column.

| Key | What it says | Left out |
|---|---|---|
| `provider`, `dataset`, `repository`, `site_url`, `releases` | whose data it is, what the database is called, where the repository and the site are, and the provider's releases. A release has an `id` (any name that can be the name of a page: `2026-v1`, `3.2`), a `name`, and may name its `background` (what the release is built on) | required, except `dataset` |
| `index` | the index colour of this dataset's site: one colour as `"#rrggbb"`, or `{"color", "dark", "tint", "soft"}`. The build works out what is not given and refuses a colour that can't be read (below) | the brand's green |
| `dataset_code_pattern` | what a dataset number looks like, as a pattern (`^[0-9]{6}$`): the findings list then looks a number up exactly and leads to the dataset's page | datasets have no number to look up |
| `lookup_example` | the example in the lookup field | `F1` |
| `finding_label`, `finding_form` | the label of an issue that is a finding, and the file name of its form in `.github/ISSUE_TEMPLATE/`. The form's field for the release is headed "*provider* release it was observed in" | `finding`, `data-finding.yml` |
| `older_numbering_until`, `older_numbering_note` | the last finding number of an older numbering, and a sentence about it for the table of findings | this repository's number; a sibling sets `0` |
| `ledger_notes` | sentences for the head of the table of findings (`ledger.md`) | none |
| `nav`, `footer`, `documents`, `redirects` | the pages of the site | required |

The shared files, which a sibling copies as they are:

- `scripts/build_site.py`, `scripts/check_site.py`, `scripts/community.py`, `scripts/triage.py`, `scripts/intake.py`, `scripts/sync.py`, `scripts/github_api.py` and the folder `scripts/sitebuild`;
- `site/style.css`, and of `site/assets`: `list.js`, `nunito-latin.woff2`, `OFL.txt`, `dds-logo.svg`, `favicon-32x32.png`;
- the folder `schema`.

Everything else is a repository's own: its configuration, its pages, its records, its issue forms and its workflows. `scripts/intake.py` reports the checks under the names that the repository's own `.github/workflows/checks.yml` gives its jobs.

What belongs to the patch tool and the release build is not shared, and the shared files run without it: `src/`, `scripts/release_build/`, `scripts/build_release.py`, `scripts/export_release.py`, `scripts/last_run.py`, `scripts/patches_snapshot.py`, `site/patched-release.md`, `site/run-steps.json`, `site/assets/replay.js`, and the workflows `full-release.yml` and `release-build.yml`. The test builds its sibling from the shared files alone and starts the sibling's own copy of the scripts, so a shared file that reaches for one of these fails there.

A site has a page for the patched release only if `documents` lists `patched-release.html`. Without it no page links there, the build reads no release build, and `api/v1/last-run.json` is not written.

A finding names its datasets by number (`code`, a whole number). Where the datasets of a provider have no number, a finding lists none and says in `scope` what it is about.

### The index colour

Every Sentier dataset site has the same frame: the logo, the paper, the type. The index colour marks which dataset a reader is on: a band over the masthead, the current item of the navigation, headings, links, buttons, the focus ring, and the dark stage on "Patch and release". Three signals stay the same on every site and are never the index colour: amber for waiting, red-brown for failed, green for good.

The stylesheet reads the colour from four tokens (`--index`, `--index-dark`, `--index-soft`, `--index-tint`). A site that sets `index` gets one rule on every page that sets them, and `scripts/sitebuild/theme.py` checks the colour before anything is written:

| Pair | Least contrast |
|---|---|
| the colour on the paper and on a card; white on the colour | 4.5 to 1 |
| the stage's text on the dark colour | 7 to 1 |
| the dark colour on the tint | 4.5 to 1 |
| the soft colour on the dark colour (marks, never text) | 3 to 1 |

The hue of the colour may not lie between 345 and 60 degrees, where amber and red-brown are: a reader would take the site's colour for a status. A grey passes, whatever its hue.

## Prose pages

A prose page is a Markdown file named under `documents` in `site/config.json`:

```json
{"title": "Take part", "source": "site/take-part.md", "page": "take-part.html", "description": "One sentence for search engines."}
```

`title` is the browser title, `description` the meta description. `also` lists other source paths that lead to the same page (for a source that was renamed). A page with three or more second-level headings gets "On this page" beside it; a page that holds a list of records takes the full width instead.

### Generated blocks

A comment on a line of its own is replaced by a generated block. Both forms work: `<!-- patch-table -->` and `<!-- generated: patch-table -->`.

| Marker | What it puts there |
|---|---|
| `findings-list` | the findings list with its status links, search, filters and sorting |
| `contributions-list` | the contributions list with search and a status filter |
| `status-tracker` | the five steps of a finding's path with the number of findings that wait after each, and the two statuses off the path |
| `status-vocabulary` | every status with its meter and the sentence that explains it |
| `feedback-lists` | reported without answer, answered, resolved, repeated and not yet reported, each as a count and a list; then the reports by date |
| `second-measurement-list` | the five findings that have waited longest for a second measurement, and a link to all of them |
| `recent-changes` | the five newest dated steps |
| `patch-table` | every community patch from `community/patches.json`, which `scripts/patches_snapshot.py` writes from the patch registry: what it does, the finding it answers, who wrote it, who authorised it |
| `last-run` | the last release build as the opening of a page: which run it is and whether it worked, then the run step by step (what each step does, the run's numbers for it, every line it printed, with a replay), and the three answers: did it work, what is blocking, what was in it. What precedes the marker and the block itself stand above the page's two columns, over the full width; "On this page" begins below. What a step does is told in `site/run-steps.json`, in plain words and without a number: every number comes from the run. The lines are the run's, character for character: they wrap, and a reader can have each on one line, have them over the whole width, copy them, or point at one (the time of a line is its link, `#run-line-N`). The run prints no colour; the name of a step, a command, a word that says how something ended and a checksum are told apart by the page, by the words alone, and no character is added or taken. A run that nobody asked to publish ends at a last step that says so, and is not drawn as a step that failed or was left out. Read by `scripts/last_run.py` from GitHub when the site is built; `--last-run FILE` gives a saved record instead, and `--offline` builds without one. `--built-by OWNER/NAME` names the repository whose runs are read; a copy built by another repository than the site's own carries a preview notice on every page |
| `release-packages` | the published releases with the files each holds, and the files of the last run with size, checksum and where they can be had. Nothing is offered for download that no release holds. The same files stand, small, beside the text under "On this page" once the reader has scrolled past this block |
| `data-files` | the machine-readable files with links |
| `lookup` | the field that looks up a dataset code, a finding number or a word |

Use `findings-list` and `contributions-list` once per page. A comment with any other text stays a comment.

### Counts

A number that follows the records is never typed. `<!-- count:NAME -->` anywhere in a sentence, a list or a table cell becomes the number:

`findings`, `contributions`, `patches`, `patches-with-finding`, `patches-without-finding`, `findings-with-patch`, `datasets`, `releases`, and `status:KEY` for each status key (`status:filed`, `status:confirmed`, `status:sent`, `status:answered`, `status:fixed`, `status:not-a-defect`, `status:withdrawn`).

An unknown name stops the build.

### Links

Write links as they work on GitHub; the build resolves them.

- To another page source (`take-part.md`, `../docs/terms-of-use.md`): the page built from it.
- To a record (`../community/findings/0/F3.json`): that record's page. A record that is not there stops the build.
- To a file of the built site, named from the `site/` folder (`feed.xml`, `api/v1/findings.json`, `changes.html`, `releases/2026-v1.html`, `datasets/188725.html`): that file. A file the site does not have stops the build.
- To a status in the findings list: `findings.md#stage-filed` (the keys of the table under "Words"). The anchor always exists.
- To anything else in the repository: the file on GitHub.

### Tables and step lists

A table becomes labelled rows on a narrow screen; nothing scrolls sideways. Keep a table to four columns where possible (five or more stack already on a tablet). A first column of short labels stays on one line. A first cell that starts with a bold key of up to three characters (`**A**`) shows the key as a tile.

A table whose first heading is `Step` becomes a numbered step list: the first column is the step's name (a leading "1." is dropped), the last column its state, the columns between its text. The state decides the mark:

| State text | Mark |
|---|---|
| starts with "Works", "Done" or "N patches", without "not", "only", "except", "but" or "part" | works |
| "Planned", "Does not exist …", "Not started" | does not exist yet |
| anything else | works in part |

To say it outright, start the state with `ok:`, `part:` or `todo:`; the prefix is not shown.

### Assessment of a contribution

`assessments` in `site/config.json` names, per contribution, the Markdown files shown as the "Assessment" section of its page, in order. Their headings are lowered by two levels. A link to such a file from another page leads to the contribution's page.

## Words

The public word for where a finding stands is **status**, and the site shows it in words. The keys below stay inside the code, the JSON, `data-stage` attributes and the anchors `#stage-<key>`. Texts carry a `{provider}` placeholder; the name comes from `provider` in `site/config.json`.

| Key | Status shown | Reached when the record has |
|---|---|---|
| `filed` | Needs a second measurement | nothing but `reported` |
| `confirmed` | Repeated, not yet reported | `repeated` with result `reproduced`, by someone other than the reporter |
| `sent` | Reported to BAFU | `sent` |
| `answered` | Answered by BAFU | `answer` |
| `fixed` | Resolved | `fixed_in` |
| `not-a-defect` | For information | `closed.as = "not-a-defect"` |
| `withdrawn` | Withdrawn | `closed.as = "withdrawn"` |

The status is the first that applies of `closed`, `fixed_in`, `answer`, `sent`, `repeated`; otherwise the finding is `filed`. A community patch and BAFU's answer are facts beside the status, never a status.

The tracker shows the five steps of the path, in these words wherever it appears: Measured, Repeated, Reported to BAFU, Answered by BAFU, Resolved. A step is shown as done only when the record holds its evidence. A step without evidence that a later step has passed says "not recorded". The feedback is continuous and not tied to BAFU's releases: a finding is resolved once a BAFU release covers the point, and no generated text frames the path as waiting for a release or says what BAFU will do.

Generated text follows the house style: British spelling; "12 October 2026" in prose and "12 Oct 2026" in lists, always inside `<time datetime>`; no person's name except the author and the authoriser of a community patch, as the registry gives them; never stage, triage, ledger, layer, upstream, provider, candidate or fix (except "import fix") for the site's own things.

Provider releases are a fixed list in `site/config.json` (`releases`: id and name, and `archive_sha256` where the patch tool downloads the release, so that the manifest of a patched release can name it). Records name releases by id; registering a new BAFU release is one entry there.

`older_numbering_until` in `site/config.json` is the last finding number of an older numbering: above it, the id of a finding is F followed by the number of its issue. It is 47 here, and 47 when the key is absent. A repository whose findings are numbered by their issues from the first one sets it to 0.

## The findings list

`findings.html` holds the 50 most recently changed findings as HTML. `findings/index.json` holds one compact array per finding, in the same order; the script loads it on first use of the search, a filter, a sort or "Show more" and draws rows from it. The state is in the address and can be linked: `findings.html?q=188725&status=filed&release=2026-v1&kind=defect&patch=1&sort=waiting`. A finding number (`F12`) and a six-digit dataset code match exactly; any other word matches anywhere in the row. Addresses of the earlier site (`#stage-…`, `#F12`) keep working.

Without JavaScript the page shows the 50 rows; a status link still filters them (the stylesheet hides the other rows), and a note leads to the complete table (`ledger.md`), `api/v1/findings.json` and the release pages.

`findings/index.json` serves the page and is not part of `api/v1`; tools read `api/v1/findings.json`.

## Interface for page builders

Everything a page needs comes from two modules. Neither is specific to a template.

`scripts/community.py` (records, standard library only):

| Call | Gives |
|---|---|
| `problems(root)` | `(errors, notes, summary)`: every error in the records. The build refuses on any. |
| `load_config(root)` | `provider`, `repository`, `site_url`, `releases`, `stale_after_days`, `older_numbering_until` |
| `load_findings(root)` | every finding record in number order; `record.path` is its file in the repository |
| `load_contributions(root)` | every contribution record; `record.path` likewise |
| `load_patches(root)` | `community/patches.json`: the community patches with the findings they answer, as the patch registry has them |
| `stage(record)` | the status key of a finding |
| `STATUSES`, `statuses(provider)` | the vocabulary in path order: `key`, `label`, `description` (one sentence, true of every finding with that status) |
| `status_label(key, provider)`, `status_description(key, provider)` | the words for one key |
| `KINDS`, `OUTCOMES`, `DATASET_ROLES` | kind of a finding, outcome of BAFU's answer, role of a listed dataset, each with its words |
| `CONTRIBUTION_CLASSES`, `CONTRIBUTION_GROUPS` | class of a contribution; the group says whether it can enter the patched release or stands beside BAFU's numbers |
| `evidence(record)` | the dated evidence of a record, oldest first: `(date, name, block)` |
| `last_change(record)` | date of the newest evidence: when the finding changed, not when its issue did |
| `waiting_since(record)` | that date while the finding is still on the path; `None` once it is resolved or closed |
| `changes(findings)` | every dated event of every finding, newest first: the changes page and the feed |
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
| `assemble(findings, repository, issues, patches)` | `findings`: every record as a dict plus `stage`, `path`, `tracker` (the issue's data or `None`), `steps`, `patches`, `related`, `changed`, `waiting_since`; `counts` by status key; `unlisted`: finding issues without a record; `without_issue`; `label_differences` |
| `steps(record)` | the five steps of the path as `{key, state, block}`; `state` is `done`, `now`, `help`, `unrecorded` or `todo` |
| `expected_labels(stage)` | the labels a record's issue should carry |

`label_differences` is for maintainers and for a job that writes labels from records. The housekeeping page names the issues; the build log names the labels to add and to remove.

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
| `feed.xml` | the 100 newest dated steps as an Atom feed |
| `sitemap.xml` | every page |
| `findings.json`, `status.json` | at the root, in their earlier shape, for readers that have not moved to `api/v1` |

Inside `api/v1` a field is never renamed or removed; fields may be added. A change that breaks a reader gets `api/v2` beside it.
