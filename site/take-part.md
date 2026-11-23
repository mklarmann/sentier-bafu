# Contribute

You can verify an issue, report a finding or propose a contribution. Reports and comments are written on GitHub, in public. Reading needs no account. Writing needs a free GitHub account.

[Submit material for review](sources.md#submit-material) · [Feedback to BAFU](feedback.md)

## Verify an issue

This is the most useful help. Before a finding is reported to BAFU, a second person is asked to verify it. The findings below still need verifying.

<!-- generated: second-measurement-list -->

1. Choose a finding with the status "Needs verifying", from the list above or from the [case register](cases.md). Its page says what was observed and links to the place where the finding is discussed. This is usually a GitHub issue.
2. Check the issue in BAFU's release files, as you received them. Do not check it in a database that the files were imported into, or on a patched copy: an import or a patch can change the data.
3. Write what you got as a comment in that discussion: the value with its unit, the file and the release you looked at, and how you got the value. A different result is as useful as the same one.
4. A maintainer then adds your check to the finding's record. The record is public. It holds your GitHub user name, the date and a link to your comment.

The check must come from someone other than the person who reported the finding. Some checks need a script. For others a text editor is enough: you open one dataset file and read a value.

## Report a finding

You found something in BAFU's data that looks wrong, or that you cannot explain.

1. [Open a finding](https://github.com/sentier-dev/sentier-bafu/issues/new?template=bafu-data-finding.yml) and fill in the form: the dataset code, the release, where you looked, what you found and how, and why it looks wrong. Give numbers with their units.
2. A maintainer reads the report and adds a record. The finding gets a number, which is the number of its issue with an F in front.
3. The finding has the status "Needs verifying" until a second person has checked it.
4. Then the finding is reported to BAFU. BAFU decides what it changes. BAFU's answer is recorded. The finding is resolved once a new BAFU release addresses it.

A finding that does not hold when it is checked again stays listed as "Withdrawn", so that nobody reports it a second time.

## Propose a contribution

A contribution is a mapping, a model, a rebuilt inventory or a method variant. [Open a contribution](https://github.com/sentier-dev/sentier-bafu/issues/new?template=community-contribution.yml) and describe what you propose and the evidence for it. The [contributions](contributions.md) page explains the kinds of contribution, the steps and what review means.

Not sure where something belongs? [Start a discussion](https://github.com/sentier-dev/sentier-bafu/issues/new?template=discussion.yml).

## Ground rules

- Work on BAFU's release files. Say what you checked and what you did not.
- Quote dataset codes, names and single values. Do not paste text from BAFU's LCI reports.
- Share nothing confidential: no restricted exports, no private correspondence.
- People review and decide. Work done with an AI agent says so.
- Nothing here implies BAFU's endorsement.

Do you want to work on the repository itself? The commands for checking a change are in [CONTRIBUTING.md](../CONTRIBUTING.md).
