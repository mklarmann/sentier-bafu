# Findings

A finding is a measured observation about BAFU's data: an amount that looks wrong, a supplier link that leads nowhere, a unit that does not fit. Each finding has a number, a record of what was observed, and a public place where it is discussed.

Findings are feedback to BAFU, the Swiss Federal Office for the Environment (FOEN), which publishes the BAFU/UVEK life-cycle inventory database. A second person is asked to repeat each measurement before the finding is reported to BAFU. BAFU decides what it changes.

<!-- findings-list -->

## How to read the list

- **A row is one finding.** It shows the number, the title, what the finding concerns, its status and where it is discussed. You can search by dataset code, by finding number or by word, and you can show one status at a time.
- **What a finding concerns.** Datasets are named by code, name and location. A finding about a group of datasets, an elementary flow or a published file says so in words.
- **The status is computed from the record.** A record holds dated evidence: who reported the finding, who repeated the measurement, when it was reported to BAFU, what BAFU answered, and which BAFU release covers the point. Nobody sets a status by hand. A step that the record does not hold is shown as "not recorded", never as done.

## What a status means

A status says how far a finding has come on its way to BAFU. Each finding's page explains its status in one sentence.

<!-- generated: status-vocabulary -->

- **"Answered by BAFU" is not "Resolved".** An answer says what BAFU said. A finding is resolved once a BAFU release or file that the record names covers the point.
- **A community patch is not a status.** It can change a copy of BAFU's release for users who need the change now. It is not BAFU's correction, and it does not change the status of a finding. The [patched copy](patch-and-build.md) page lists the patches.

## About this list

- **What counts as a finding.** Something measured on files that BAFU published, in a way that a second person can repeat. A mapping, a model, a rebuilt inventory or a method variant is a [contribution](contributions.md), not a finding.
- **What is quoted.** Dataset codes, names and single values. Text from BAFU's LCI reports is not reproduced (BAFU's Terms of Use, clause 4; see [data and terms](../docs/terms-of-use.md)).
- **Numbers.** A finding keeps its number. From F48 on, the number of a finding is the number of its GitHub issue. Lower numbers follow an older numbering shared with lci-bafu-catalog, a separate public project that imports the same release. Some findings were first discussed there, and their pages link to that discussion.

Found something in the data, or want to repeat a measurement? [Take part](take-part.md) explains how.
