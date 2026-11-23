# Data (JSON)

The findings, the contributions and their statuses are also published as JSON files, for tools and for other projects. The files hold what the site shows: dataset codes and names, the text of the records, statuses, dates and links. They hold no inventory files.

Addresses are relative to `https://sentier-dev.github.io/sentier-bafu/`. Inside `api/v1/` a field is never renamed or removed, and fields may be added. A change that would break a reader gets a new folder, `api/v2/`, beside the old one.

<!-- generated: data-files -->

The two files under `schema/` are the JSON Schema of a finding record and of a contribution record. They are the rules that the records in the repository are checked against.

The examples below are from the build of <time datetime="2026-11-13">13 November 2026</time>, shortened where marked with `…`. Read the files for current values.

**Is a dataset affected?** Look up its code in `api/v1/datasets.json`. The `role` says whether the finding is about this dataset (`subject`), whether a result of this dataset changes because it uses such a dataset (`affected`), or whether the finding only names it (`named`).

```json
"196588": {"name": "Disposal, rectangular straw bale", "location": "CH",
  "findings": [{"id": "F8", "role": "named"}, {"id": "F10", "role": "subject"}], "patches": []}
```

**All findings.** One entry of `findings` in `api/v1/findings.json`. Dates are those of the evidence in the record; `null` means that the record holds none.

```json
{"id": "F13", "issue": 28, "title": "Electricity from natural gas (FI) labelled MJ but modelled per kWh",
  "kind": "defect", "status": "confirmed", "status_label": "Repeated, not yet reported",
  "datasets": [401085, 316743], "scope": "", "releases": ["2026-v1"], "patches": [], "answer_outcome": null,
  "reported": "2026-10-14", "repeated": "2026-10-21", "sent": null, "answered": null, "fixed": null,
  "closed": null, "changed": "2026-10-21", "waiting_since": "2026-10-21",
  "url": "https://sentier-dev.github.io/sentier-bafu/findings/F13.html",
  "json": "https://sentier-dev.github.io/sentier-bafu/api/v1/findings/F13.json"}
```

**One finding.** `api/v1/findings/F13.json` holds the record as it is in the repository, and what is derived from it. `discussion` is the state of the finding's GitHub issue when the site was built; it is `null` when the finding has no issue in this repository or the issue could not be read.

```json
{"schema": "sentier-bafu/finding/1", "generated": "2026-11-13", "revision": "9666c2e", "site": "…",
  "record": {"schema": 2, "id": "F13", "issue": 28, "title": "…", "observation": "…", "…": "…"},
  "status": "confirmed", "status_label": "Repeated, not yet reported", "patches": [], "related": [],
  "changed": "2026-10-21", "waiting_since": "2026-10-21",
  "discussion": {"number": 28, "state": "open", "comments": 3, "updated": "2026-10-21", "…": "…"},
  "url": "…/findings/F13.html", "source": "…/community/findings/0/F13.json"}
```

**Contributions.** One entry of `contributions` in `api/v1/contributions.json`. The file also lists the kinds under `classes`.

```json
{"id": "C002", "issue": null, "title": "…", "class": "mapping", "status": "proposed",
  "url": "https://sentier-dev.github.io/sentier-bafu/contributions/C002.html"}
```

**Counts.** `api/v1/status.json`. The keys of `findings_by_status` are explained in the `statuses` list of `api/v1/findings.json`.

```json
{"schema": "sentier-bafu/status/1", "findings": 23,
  "findings_by_status": {"filed": 11, "confirmed": 4, "sent": 0, "answered": 3, "fixed": 1,
    "not-a-defect": 3, "withdrawn": 1},
  "contributions": 2, "accepted": 0, "patches": 11, "revision": "9666c2e", "built": "2026-11-13", "…": "…"}
```

The older files `findings.json` and `status.json` stay at the top level for tools that already read them. New tools should read `api/v1/`.
