# Contributions

A contribution is a proposal with evidence and a validation plan: a correction that is not yet a patch, a mapping, a model, a rebuilt inventory or a method variant. Some become community patches. A variant or a rebuilt inventory stays beside the patched release under its own name and never replaces BAFU's numbers.

<!-- contributions-list -->

## What kind of change is it?

Name what a change does to BAFU's release. Its class decides where it ends up. The classes are shared with lci-bafu-catalog.

| Class | What it changes | Where it ends up |
|---|---|---|
| **A** import fix | what every reader has to do: encoding, unit names, exchange numbers | in the import, recorded |
| **B** linking repair | a declared supplier that does not resolve (F3: location `ENTSO` for datasets registered as `ENTSO-E`) | a community patch; the original declaration is kept |
| **C** re-declaration | a unit or label that BAFU's own change log corrects (2026 v1: year → hour on 156 datasets) | applied, with the change log as evidence |
| **D** value change or variant | an amount BAFU has not confirmed, a rebuilt or disaggregated inventory, a method variant such as residual electricity mixes | a separate database under its own name, **never under BAFU's**; it says what it replaces, how, and how well |
| **E** downstream workaround | a fix in a user's own inventory | not in this repository |

Classes A to C go into the patched release; B and C answer a [finding](findings/README.md). Class D stays beside it. It can be excellent and still not be BAFU's number, so users choose it knowingly.

## How a contribution moves

Status: proposed → testing → reviewing → accepted, rejected or superseded.

1. **Propose.** Add a record from the [template](templates/contribution.json): the release it builds on, the pinned implementation, the checks it must pass and who reviews it.
2. **Build beside.** Build the baseline and the candidate separately, from the same pinned inputs. Never change the baseline in place.
3. **Test.** Run the checks the record names and attach each result. A missing or failed check stays visible. See [evidence](build-validation.md) and [apply and test](application-and-testing.md).
4. **Review.** The named reviewers approve the exact revision that was tested. Objections are recorded with their answer.
5. **Decide.** An accepted contribution may become a recommendation to BAFU. Sending it needs an authorised sender, and the delivery and the answer are recorded.

## What review means here

- People approve. An automated check verifies the record, not the science.
- An approval names the baseline and the revision it covers. Approving an earlier revision does not carry over.
- No reviewer or contact is named without their agreement. Silence is not consent.
- A merged pull request is not BAFU's endorsement.

## Assessments

Longer notes on single contributions: [C001, the Brightcon copied-process contribution](hackathon-assessment.md), and [C002, the mapping import](mutel-mapping-review.md).
