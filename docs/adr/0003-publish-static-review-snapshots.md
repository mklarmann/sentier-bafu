---
status: proposed
---
# Publish review snapshots through the existing static site

Use the existing community pipeline and its run records to produce a versioned,
reviewed public snapshot for GitHub Pages. Adapt the navigation, evidence
disclosure and decision-queue concepts of Brightway Flows in the Sentier site.
Keep local runs and the self-contained report available independently.

This trades a live database browser for a small deployable surface that does
not need a server, vendor archives or write credentials in the browser. Pages
shows the snapshot identity and age; GitHub retains discussion and review.
An authenticated live application can be considered later if actual user needs
exceed the snapshot contract.

Render from a public allowlist, never by copying arbitrary local reports.
The current RunLog keeps detailed changes for only ten example datasets per
step and caps transition summaries; the UI must expose that sampling. A full
dataset history requires a separately designed complete change stream, not
inference from these samples.

Reuse design concepts with an independent implementation under the existing
MIT project. Brightway Flows code is AGPL-3.0-or-later and data ODbL-1.0.
Copying its implementation requires an explicit licensing decision; its data
may be redistributed under the ODbL with its notices. The community repo
records the author's permission for the pipeline's output to follow the BAFU
Terms of Use instead of ODbL share-alike; confirm that it applies to this
repository before publishing output from it.

It awaits the decision of Chris Mutel and Laurenz Bougan in
[#18](https://github.com/sentier-dev/sentier-bafu/issues/18).
