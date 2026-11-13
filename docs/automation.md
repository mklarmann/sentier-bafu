# Automation: from a filed issue to a patched release

This page describes every workflow of the repository, what each may write, and the path of a
finding from the issue form to BAFU's answer and to a patched release. It also holds the threat
model of the workflows that read what strangers write, and the checklist for the first run.

**The rule.** No step exists only to keep two copies of a fact in agreement. People do the steps
that need judgement, and each of those is one review or one command. Everything else is computed
when the site is built, or done by a workflow.

| What needs a person | How |
|---|---|
| Accept a report as a finding | merge the pull request the intake opened |
| Repeat a measurement | measure, then comment `/repeated reproduced` or `/repeated not-reproduced` |
| Accept a second measurement | merge the pull request the intake opened for the comment |
| Write a community patch | `python3 scripts/new_patch.py NAME --finding F48`, then a pull request |
| Authorise a community patch | review the pull request; the patch names the authoriser |
| Report findings to BAFU | send them; then `python3 scripts/community.py send --batch … F48 F51` |
| Record BAFU's answer | `python3 scripts/community.py answer F48 --outcome … --summary "…"` |
| Tag a patched release | push a tag `patched-…` on a commit of `main` |
| Register a new release of BAFU | one entry in `site/config.json`, then `python3 scripts/intake.py form` |
| Confirm a correction by BAFU | `python3 scripts/community.py fixed F48 --release …` |
| Withdraw a finding | `python3 scripts/community.py close F48 --as withdrawn --reason "…"` |

Nobody assigns a number (it is the number of the issue), sets a label, writes a status, copies a
patch into a record, updates a list of findings, or edits a test because a record changed.

## 1. The path of a finding

| # | What happens | Who | What is written, and where |
|---|---|---|---|
| 1 | An issue is filed with the finding form. The form sets the labels `bafu-finding` and `needs-triage`. | reporter | the issue |
| 2 | `intake.yml` reads the form and opens a pull request `intake/F<issue>` that adds one file, `community/findings/<n // 1000>/F<n>.json`. It comments on the issue: "This report is finding F48 … proposed in #…". If the form is incomplete it says what is missing and sets `needs-info`; an edit of the issue runs the intake again. | workflow | a branch, a pull request, one comment |
| 3 | The checks run on the proposed commit, and their result is reported on it. | workflow | commit statuses |
| 4 | **A maintainer reads the record and merges it.** Is it a finding? No text pasted from BAFU's reports? Are the dataset numbers right? | **maintainer** | the record on `main` |
| 5 | `sync.yml` sees the record: it sets `status: needs a second measurement` and `help wanted`, takes `needs-triage` off, and comments once with how to repeat the measurement. `pages.yml` rebuilds the site. | workflow | labels, one comment; the site |
| 6 | **A second person repeats the measurement** on BAFU's release files and comments, beginning with `/repeated reproduced` or `/repeated not-reproduced`. | **second person** | a comment |
| 7 | `intake.yml` opens a pull request `repeat/F<n>` that sets `repeated` in the record: who, when, the comment's address, the result. The reporter's own login is refused with a polite comment. | workflow | a branch, a pull request, one comment |
| 8 | **A maintainer reads the comment and merges.** | **maintainer** | the record |
| 9 | `sync.yml`: `status: repeated not yet reported`, `help wanted` off, one comment. | workflow | labels, one comment |
| 10 | **Someone writes a community patch** if the finding needs one now. The patch names its finding; a second person authorises it in review. `full-release.yml` runs it on BAFU's full release. The site shows the patch beside the finding. | **author, authoriser** | the patch |
| 11 | **Someone reports the findings to BAFU**, then records it for all of them with one command and one pull request. | **maintainer** | `sent` in each record |
| 12 | `sync.yml`: `status: reported to BAFU`, one comment. | workflow | labels, one comment |
| 13 | **Someone records BAFU's answer** in our own words. | **maintainer** | `answer` in the record |
| 14 | `sync.yml`: `status: answered by BAFU`, one comment that quotes the summary. | workflow | labels, one comment |
| 15 | **A maintainer pushes a tag** `patched-…`. `release.yml` runs every patch on BAFU's full release and publishes `manifest.json`. The site reads it. | **maintainer** | a GitHub Release with one file |
| 16 | BAFU publishes a release. **A maintainer registers it** (section 6). The run on the new release says per patch whether it is still needed. | **maintainer** | one entry in `site/config.json` |
| 17 | **A maintainer confirms the correction** with `community.py fixed`. | **maintainer** | `fixed_in` in the record |
| 18 | `sync.yml`: `status: corrected by BAFU`, one comment, and the issue is closed. | workflow | labels, one comment, the issue's state |

BAFU decides what it changes. Nothing above promises that it adopts anything: a finding can stay
"Answered by BAFU" for ever, and a community patch is never a correction by BAFU.

## 2. The workflows

After the branches of November 2026 are merged the repository has these workflows. The first
five are described here in full; the next three belong to the patch tool and the build and are
described in their own documents.

| Workflow | Starts on | Token | Writes |
|---|---|---|---|
| `checks.yml` | every pull request; push to `main`; called by `intake.yml` | `contents: read` | nothing |
| `pages.yml` | push to `main`; daily; an issue opened, closed or reopened; on request | build: `contents: read`, `issues: read`. deploy: `pages: write`, `id-token: write` | the site on GitHub Pages |
| `intake.yml` | an issue opened or edited that carries `bafu-finding`; a comment on an issue that begins with `/repeated` or `/record` | record: `contents: write`, `pull-requests: write`, `issues: write`. checks: `contents: read`. status: `contents: read`, `statuses: write` | a branch `intake/F<n>` or `repeat/F<n>` with one file; one pull request; one comment; the label `needs-info`; commit statuses |
| `sync.yml` | push to `main` that changes a record, `site/config.json` or the script; nightly; on request | `contents: read`, `issues: write` | labels, one comment per change of status, the state of finding issues; label definitions |
| `release.yml` | a tag `patched-*`; on request (builds, publishes nothing) | build: `contents: read`. publish: `contents: write` | a GitHub Release that holds `manifest.json` |
| `ci.yml` | every pull request; push to `main` | `contents: read` | nothing (the patch tool's own tests on a small fixture) |
| `full-release.yml` | a pull request or a push to `main` that touches the patch tool; on request | `contents: read` | a run summary as an artifact (counts and checksums) |
| `release-build.yml` | a pull request or a push to `main` that touches the patch tool or the build; on request | `contents: read` | audit results as an artifact (codes, names, single scores) |
| `provider-release.yml` | on request, after a release of BAFU was registered | `contents: write`, `pull-requests: write` | one pull request that sets `fixed_in`. **Specified in section 6, not built** |

Rules every workflow keeps (`community/tests/test_workflows.py` checks them on the five workflows
of this page): each action is pinned to a commit; a token that can write is given to the one job
that needs it; no `${{ }}` expression is part of a shell script; no checkout leaves a token on
disk; no workflow uses `pull_request_target` or `workflow_run`; a run that writes is never
cancelled half way.

### checks.yml

Three jobs, none of which writes:

- **Records and unit tests**: `community.py check`, the unit tests, the build audit template.
- **Site build and links**: the site built from the records alone (no network), then
  `check_site.py`, which also refuses data files in the output.
- **Tests hold through a finding's life**: `community/tests/lifecycle_steps.py` takes each
  ordinary step (a new record, a second measurement, a batch sent, an answer, a correction, a
  withdrawal, a new release, a new patch) on a copy of the repository, with the commands people
  use, and runs the unit tests on the copy. A test that reads the repository's own records fails
  here, before it fails on somebody's pull request. Tests of rules read
  `community/tests/fixtures/frozen` instead.

### pages.yml

Builds the site with the issues (comment counts, last activity, issues filed as findings that
have no record yet) and deploys it. If the issues cannot be read the build fails and the last
published site stays. It runs daily so that "waiting since" and the counts stay current. It does
not run on label changes: labels follow records, and a change of a record arrives as a push.

### intake.yml

Three jobs.

1. **Propose the record** holds the token that can write. It checks out the default branch and
   runs `python3 -I scripts/intake.py run`, which reads the event file, decides, and talks to the
   GitHub API. It installs nothing.
2. **Check the proposal** calls `checks.yml` on the proposed commit. A pull request that a
   workflow opens starts no workflow, so without this the proposal would have no checks.
3. **Report the checks** sets one commit status per check on the proposed commit, under the
   names the checks have on any other pull request, so that a rule "these checks must pass"
   holds for proposals too.

What the first job does for each event (`intake.py plan` decides, `intake.py publish` writes):

| Event | Outcome |
|---|---|
| Issue opened or edited, filed with the form, complete | pull request `intake/F<n>` with one new file; one comment; `needs-info` taken off |
| The same event again (a job run twice) | nothing new: no commit, no pull request, no comment |
| Issue edited while the pull request is open | the file on the branch is updated, unless a person changed the proposal by hand; then one comment says so and nothing is overwritten |
| Issue edited after a maintainer closed the pull request | nothing. `/record` by a maintainer proposes it again |
| Issue edited after the record was merged | the record is not changed; one comment, once, says how to change it |
| Form incomplete, a field too long, raw HTML, a heading or an image in a field | no record; one comment that names each problem in the reporter's words and never repeats what the reporter wrote; label `needs-info` |
| Issue with the label but not filed with the form | no record; one comment, once; label `needs-info` |
| Issue number 47 or lower without a record | no record; a maintainer writes it (those numbers follow an older numbering) |
| `/repeated reproduced` or `/repeated not-reproduced` by someone other than the reporter | pull request `repeat/F<n>` that sets `repeated`; one thank-you comment |
| `/repeated …` by the reporter | refused with a polite comment; nothing else is written |
| `/repeated …` when no record is merged yet, a second measurement is recorded already, the finding is closed, or another proposal waits | one comment that says which; nothing else |
| `/repeated` with anything else on the line | one comment with the two lines that work |
| `/repeated reproduced F10` on an issue that holds two findings | the named finding; without a name the comment asks which |
| `/record` by an owner, member or collaborator | the form is read again; on a finding that has a record only the fields that come from the form change, the evidence is kept |
| `/record` by anyone else | one comment; nothing else |
| A comment that is edited or deleted; a comment by a bot; a comment on a pull request | nothing: commands are read when a comment is created |

The form and the record:

| Record field | Comes from |
|---|---|
| `id`, `issue` | the issue's number: issue 48 is `F48` |
| `title` | the issue's title without `[Finding]` |
| `reported` | who filed the issue, the day it was filed, its address |
| `kind` | "What kind of finding is it?" |
| `releases` | "BAFU release it was observed in": a list written from `site/config.json` |
| `datasets` | "Datasets, one per line": `number \| name \| location`. A dataset another record lists takes its name from that record |
| `scope`, `observation`, `method`, `exposure`, `notes` | the fields of the same meaning |
| `next` | "A second person repeats the measurement …" |
| everything else | empty: the status is "Needs a second measurement" |

The headings of the form are a contract with the issues already filed: `scripts/intake.py` holds
them, and a test compares them with `.github/ISSUE_TEMPLATE/bafu-data-finding.yml`. Issues filed
with the form as it was until November 2026 are still read (#47 and #35 are test cases).

### sync.yml

`python3 scripts/sync.py` prints the differences between records and issues; `--apply` writes
them. A push and the nightly run apply; a run on request applies only when "apply" is ticked.

| The record says | The issue gets |
|---|---|
| a finding with this issue | `bafu-finding` and exactly one of `status: needs a second measurement`, `status: repeated not yet reported`, `status: reported to BAFU`, `status: answered by BAFU`, `status: corrected by BAFU`, `status: for information`, `status: withdrawn` |
| … that needs a second measurement | also `help wanted` |
| … whose status changed | one comment, generated from the record. It carries a hidden marker and is never posted twice |
| … whose status is final (corrected, for information, withdrawn) | closed: "completed" when corrected, "not planned" otherwise |
| no record for an open issue that carries `bafu-finding` | `needs-triage`, and no `status:` label |
| two findings in one issue | the earlier status of the two; closed when both are final |

The labels say the status in the words the site shows (`community.status_label`), so a label
never says more than the site does. The job owns every label that begins with `status: `, plus
`help wanted` and `needs-triage` on finding issues, and the labels of the earlier model
(`upstream-reported`, `upstream-fixed`, `informational`, `handled-in-layer`, `withdrawn`), which
it takes off. Any other label on an issue is left alone. A label set by hand is put right at the
next run. It creates the labels it defines when they are missing: the seven status labels,
`needs-triage` and `contribution`.

What it never does: reopen an issue, change a record, or write on an issue that is not a
finding. A closed issue whose finding is still on its way is listed "for a person to decide".

### release.yml

A tag `patched-…` on a commit of `main` builds the patched release and publishes its manifest. A
run on request builds and publishes nothing. The build job refuses a tag that is not on `main`,
runs `bafu-fixes run latest … --strict --summary`, checks the written files against the schema
and the summary, checks the records, and writes the manifest. The publish job, the only one with
a token that can write, checks that the file it received is a manifest and nothing else, and
creates the release with that one file.

The manifest (`scripts/release_manifest.py`, format `sentier-bafu/patched-release/1`):

| Field | Content |
|---|---|
| `tag`, `built` | the tag; when the run finished |
| `provider_release` | BAFU's release: its address, the SHA-256 of the archive, the fingerprint of the files read, the number of files, datasets and exchanges, and its id in `site/config.json` when that list names the archive |
| `tool` | `bafu-community-fixes`, its version, the commit it was run at |
| `options` | schema check, extensions, patches selected or skipped |
| `import_fixes` | per import fix: id, description, result, datasets and values changed |
| `patches` | per community patch: `id`, `description`, `findings`, `author`, `authorised_by`, `result` (`applied`, `not needed`, `failed`), the counts, and `datasets`: the numbers of the datasets it changed |
| `totals` | steps, datasets changed, values changed |
| `output` | the number of files, their size, and the fingerprint of the patched release |

It holds no inventory: no amount, no exchange, no text of a dataset. It names the author and the
authoriser of each patch and nobody else; who reported a finding and who answered for BAFU are
left out. A release holds no failed step, and no patch that changed data without an authoriser:
the script refuses both.

To prove a local build is the release: run the tool at `tool.revision`
(`bafu-fixes run latest OUT --strict --summary S.json`), then
`python3 scripts/release_manifest.py --summary S.json --output OUT --out mine.json`, and compare
`output.fingerprint`.

The site learns from the manifest of the latest release which patches a patched release contains
and which datasets each changed. Reading it at build time, the way the issues are read, is work
for the site build.

A manifest is written in one place. The fields above are the contract with the site and the
records: inside format 1 a field is never renamed or removed, and fields may be added. If the
build tools bring a writer of their own that says more (the Brightway build, the exports), that
writer and its release workflow take over and this script goes, except for its check
(`--verify`), which stays as the gate before anything is published.

## 3. Staleness

Nothing is stored and nothing is sent. `community.staleness(record, today, thresholds)` computes
how long a finding has waited at its status from the date of its newest evidence; the site,
rebuilt daily, shows "waiting since" and can sort by it; `sync.py` lists the findings that wait
longer than the threshold of their status in its report. Thresholds are days per status:

```json
"stale_after_days": {"filed": 30, "confirmed": 30, "sent": 90, "answered": 365}
```

in `site/config.json`; without the key these numbers apply. There are no reminder comments.

One list matters more than the others: a finding BAFU confirmed, no correction recorded, and a
release of BAFU registered after the answer. `community.check_in_release(record, config)` names
those releases. It needs the date of a release in `site/config.json` (`"date": "2027-06-30"` in
the release's entry); a release without a date is never listed.

## 4. Threat model

The intake reads what anyone with a GitHub account writes: the title and the text of an issue,
the text of a comment, and a login. All of it is untrusted.

| Threat | What stops it |
|---|---|
| Text of an issue runs as a shell command | No `${{ }}` expression is part of a shell script in any workflow (tested). `intake.py` reads the event from the event file as JSON. The one expression that names a comment's text is the job's condition (`startsWith(…, '/repeated')`), which GitHub evaluates and no shell sees. |
| Text of an issue runs as code of the workflow | The job with the write token checks out the default branch, never a pull request or a branch named by the event, and runs this repository's script with `python3 -I`. It installs nothing. There is no `pull_request_target`. |
| A package installed for the checks steals the write token | The checks run in a job of their own with `contents: read`. The token that can write never exists in a job that installs anything. |
| Text printed to the job log is read by the runner as a command (`::set-output`, `::add-mask`) | Nothing an issue says is printed. The scripts print fixed words, numbers and ids (tested on a body full of runner commands). |
| Text reaches a commit message, a pull request, a comment | Those texts are written in `intake.py`, word for word. What an issue says goes into the record file and nowhere else. A message to the reporter names the field and the rule, never the reporter's words (tested). |
| Raw HTML or a script address reaches the site | The record must pass `community.validate_finding`: no raw HTML, no image, no heading, links are full https addresses. The site build validates again and escapes what it writes. And the text reaches the site only after a person merged the pull request. |
| A very long field | Each field has a limit; beyond it the field is refused, never cut. A body longer than GitHub accepts is refused whole. |
| Forged identity or number | The login must look like a login, the number must be a positive integer, the date a calendar date; the addresses in the record are built from the repository's own address. |
| A reporter confirms their own finding | `/repeated` by the reporter's login is refused. A second account of the same person is not: the maintainer who merges reads the comment. |
| A stranger floods the repository with proposals | One issue gives one branch and one pull request. The form's label starts the intake, so a flood of issues gives a flood of pull requests: GitHub's own limits and "block user" apply. Nothing merges by itself. |
| A stranger suppresses a comment of the workflow by posting its hidden marker | Possible, and harmless: the comments are information; labels, records and pull requests do not depend on them. |
| A collaborator prepares a branch `intake/F48` with other changes | A branch without an open pull request is set back to `main` before the record is written. On a branch with an open pull request, a change by a person stops the workflow from writing. The maintainer sees the whole difference in the pull request. |
| A changed tag builds a release from unreviewed code | The build refuses a tag that is not on `main`. Protect tags `patched-*` in the repository settings. |
| A release asset that holds inventory | The publish job receives one file, checks that it has exactly the shape of a manifest, and uploads that file and nothing else (tested). |
| The token leaks to another address | `github_api.py` sends it only to an https address or to this machine. |

What the workflows can write at most: with `contents: write`, the intake job could write any
branch. It writes `intake/F<n>` and `repeat/F<n>` only, and `main` should be protected (section
8), which is what keeps a mistake in the script from reaching `main`.

## 5. Cases and limits

| Case | Outcome |
|---|---|
| Two people file at the same moment | Two issues, two numbers, two branches, two files. No generated list is committed, so the two pull requests cannot conflict (tested). |
| Two events for one issue at once | The intake runs one issue at a time, in order (`concurrency: intake-<number>`). |
| A form field is empty | Named in one comment; the record is proposed as soon as an edit fills it. |
| A `/repeated` comment is edited later | Nothing runs: commands are read when a comment is created. **Limit:** the record keeps the address of the comment; GitHub shows that it was edited and keeps its history for maintainers. |
| A `/repeated` comment is deleted after the merge | **Limit:** the record's link then leads to the issue without the comment. Nothing detects this. A maintainer can replace the evidence with `community.py repeat --replace`. |
| A record is deleted | Its issue loses the `status:` label and gets `needs-triage` again at the next sync; a closed issue stays closed. An edit of the issue does not propose the record again; `/record` does. |
| The words of a status change | Every issue is relabelled at the next sync and nobody is notified: labels in other words are replaced without a comment. The old label definitions stay in the repository's label list, unused. |
| A label is set or removed by hand | Put right at the next sync. If the right label was replaced by another status label, the sync reads it as a change and comments once. |
| The rate limit is reached during a sync | The run stops between two issues, says how many are left, and succeeds with a warning. Each issue is finished before the next begins, comment first, so the next run goes on where this one stopped and announces nothing twice (tested). The job also stops while 25 requests are left, for the other workflows. |
| The API fails during an intake | The job fails and names the request. Every step can be repeated: running the job again finishes it. |
| One issue cannot be written during a sync (locked, moved) | The others are written; the job then fails and names the issue, so that a maintainer sees it. An issue that was deleted is listed for a person and is no error. |
| Two proposals name the same new dataset differently | Each passes alone. After both are merged the check on `main` fails and names the two findings; the name is put right in a pull request. **Limit:** only "require branches to be up to date before merging" prevents it. |
| A label exists in another case (`Help Wanted`) | Treated as the same label, as GitHub does. |
| An issue is transferred or its number is reused | **Limit:** not handled. The record names the number. |
| A finding's issue is closed by hand while the finding is on its way | Listed for a person; the sync does not reopen it. |
| Two findings share an issue (#3) | The issue shows the earlier status; a comment is posted when that changes. **Limit:** a change of the later one alone is not announced. From F48 on a finding is its issue, so this concerns #3 only. |
| A contribution is filed | The form sets `contribution`. **Limit:** no record is proposed; a maintainer writes it. |

## 6. A new release of BAFU: specified, not built

Registering a release is one entry in `site/config.json` (`id`, `name`, and for the check below
its `date` and `archive_sha256`), followed by `python3 scripts/intake.py form`, which writes the
form's release list; a test fails while the two differ.

`provider-release.yml` is to do the rest: run on request with the id of the registered release,
run every patch on that release, report per patch "still needed" (the value the patch corrects
is still there) or "corrected value found", and open one pull request that sets `fixed_in` on the
findings whose patches found the corrected value, with a table of the patches still needed and
the patches finished. A person reads and merges.

It is not built, because three pieces are missing in the patch tool:

1. **More than one release.** `download.py` knows one address, one checksum and one fingerprint
   (`LATEST_RELEASE`), and the command line knows `latest` or a folder. The list of releases in
   `site/config.json` has ids and names but no address. Needed: one registry of releases (id,
   address, archive checksum, fingerprint) that the tool and the site share, and
   `bafu-fixes run --release <id>`.
2. **A patch that knows where it applies.** A patch names no release. On a release that carries
   BAFU's correction, a patch with a guard stops the whole run with an error ("expected 126.22,
   found …") and a patch without one passes silently. Needed: `releases=(…)` on a patch, a run
   that skips a patch on a release it does not name, and a guard that reports "corrected value
   found" as a result instead of stopping. The manifest already has the word for it: `not needed`.
3. **A check for findings without a patch.** Only 4 of 23 findings have a patch. For the others
   a correction can only be found by measuring again, unless a record carries a statement that a
   machine can check (a dataset number, an exchange, one value).

Until then: a person runs the tool on the new release, reads which patches stopped, measures the
other reported findings again, and records each correction with `community.py fixed`.

## 7. What only a run on GitHub can show

Checked on a developer machine: `actionlint` 1.7.12 with `shellcheck` 0.11.0 on every workflow;
every `run:` step executed as written against saved event files and a stand-in for the GitHub
API; the unit tests. Not checked, because it needs GitHub:

1. That a pull request opened with the workflow's token starts no workflow (the reason for the
   second and third job of `intake.yml`), and that the commit statuses those jobs set are shown
   on the pull request and satisfy a rule "these checks must pass".
2. That comments and labels written with the workflow's token start no workflow (so `sync.yml`
   cannot start itself or `intake.yml`).
3. How GitHub writes the form into the issue: the headings, `_No response_`, a list field inside
   a code fence, several releases as `a, b`. The parser was written from the bodies of #47 and
   #35 and from GitHub's documentation.
4. That a commit made through the API with the workflow's token is recorded as made by a bot
   (the intake uses this to tell its own commits from a person's).
5. `workflow_call` with an input, `needs.<job>.result`, and the job conditions as GitHub
   evaluates them.
6. The pinned actions at their commits, the concurrency groups, and the run times.
7. The repository settings below.
8. `gh release create` with the workflow's token.

## 8. First run

Before merging:

1. **Settings → Actions → General → Workflow permissions:** tick "Allow GitHub Actions to create
   and approve pull requests". Without it the intake fails when it opens the pull request.
2. **Branch protection for `main`:** require a pull request. If checks are to be required,
   require exactly `Records and unit tests`, `Site build and links` and
   `Tests hold through a finding's life`; the intake reports its proposals under these names.
3. **Tags:** a rule that only maintainers create tags `patched-*`.
4. **Settings → General → Pull Requests:** "Automatically delete head branches", so that merged
   `intake/…` branches go away. The intake copes with a branch that stays.
5. **Labels:** none to create by hand. `bafu-finding`, `needs-triage`, `needs-info` and
   `help wanted` exist; the first sync that applies creates the seven `status: …` labels and
   `contribution` (a form applies a label only if the label exists, so file no contribution
   before that run). The labels of the earlier model can be deleted after the first sync:
   `upstream-reported`, `upstream-fixed`, `informational`, `handled-in-layer`, `withdrawn`.

The first sync:

1. Run "Sync" on request with "apply" unticked and read the job summary. On 13 November 2026 it
   listed all 18 finding issues: each gets its `status:` label, 12 lose a label of the earlier
   model or `needs-triage`, and #32 and #35 would be closed.
2. Decide whether the first run posts its 18 comments (one per issue, saying the status and, for
   9 of them, how to repeat the measurement). To post none, run with "apply" ticked and
   "comments" unticked; later changes of status are announced as usual.
3. Run with "apply" ticked. Then run it once more: it must report 0 differences.

The first intake:

1. File a test issue with the form (a real small finding is best). Watch the "Intake" run: three
   jobs, the second and third only after the first opened a pull request.
2. Look at the pull request: one new file, three checks reported on its commit, the comment on
   the issue. Compare the record with the form: this is where a difference between GitHub's
   rendering and the parser would show.
3. Edit the issue: the same pull request gets a second commit and no second comment.
4. Comment `/repeated reproduced` as the reporter: one polite refusal. Merge the pull request,
   let another account comment `/repeated reproduced`: a second pull request.
5. If the checks do not appear on the pull request: close and reopen it once, which starts
   `checks.yml` in the ordinary way, and report it; the status job is then the part to look at.
