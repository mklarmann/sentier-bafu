---
status: proposed
---
# Keep elementary-flow decisions in Brightway Flows

The community pipeline already consumes Brightway Flows corrections, pinned
to commit `19d6cc6`, and a crosswalk from release 1.0.0
([10.5281/zenodo.22857950](https://doi.org/10.5281/zenodo.22857950)). Release
1.1.0 followed on 21 October 2026
([10.5281/zenodo.23554066](https://doi.org/10.5281/zenodo.23554066)); moving
to it is a reviewed upstream refresh. Keep that as the common identity authority and contribute
reusable elementary-flow corrections upstream. BAFU-specific inventory patches
stay here; consumer method policy stays with its consumer. A second local
identity matcher would recreate the disagreements this work is meant to resolve.

Preserve original and corrected source tuples, upstream revision, correspondence
strength and evidence. Quantity conversion, direction and method factors remain
separate claims: patch 0010 adds identity links and does not convert amounts.
The 53 included corrections and 26 exclusions in the pinned community data
remain intact until a reviewed upstream refresh changes them.

Local triangulation knowledge is migrated as evidence and reproductions, then
focused module PRs. It becomes active behavior only through a verified containing
release and consumer validation. Unknown conversions stay unknown.

Laurenz Bougan agreed with the content on 14 October 2026. It stands as
accepted once Chris Mutel confirms it in
[#18](https://github.com/sentier-dev/sentier-bafu/issues/18).
