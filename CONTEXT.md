# sentier-bafu

A community space for using, testing and improving BAFU/UVEK inventories and
returning evidenced recommendations to the dataset provider.

## Language

**Provider release**: The unchanged dataset distributed by BAFU, identified by
release and source fingerprint. _Avoid_: calling patched output the original.

**Import fix**: A recorded preparation applied while reading the release. It
may repair schema compliance or apply a documented convention; its reason
determines which, rather than its position in the pipeline.

**Community patch**: An identified, ordered correction applied to the imported
dataset with author, rationale and provenance.

**Patched copy**: Output of a named provider release and selected community
patches. Its processing history accompanies its use. _Avoid_: release, patched
release, publication: a release is the provider's.

**Build**: One run of the whole path on a provider release, and what it makes:
the patched copy, its checks and its files for LCA tools. A build claims
nothing beyond its own record.

**Tagged build**: The build a maintainer marks with a tag as the one others
should use. Its manifest is kept under the tag. _Avoid_: release, version.

**Finding**: A reproducible observation, including an unresolved question or a
withdrawn interpretation. A finding can exist without a patch.

**Contribution**: A proposed correction, model or application scenario with
evidence and validation requirements. Some contributions never become patches.

**Run**: One recorded execution with inputs, options, software identity, outcomes
and validation scope. A fixture run describes only the fixture.

**Source observation**: An exchange as originally declared, retaining its
release, locator, name, context and unit even when corrected attributes differ.

**Consensus flow**: The versioned elementary-flow identity supplied by Brightway
Flows. Correspondence strength alone does not establish a quantity conversion.
_Avoid_: "Consensus Flows" as the project's name; the project is Brightway Flows.

**Community authorisation**: A named person's recorded approval to include a
patch in the patched copy. _Avoid_: provider approval, scientific consensus.

**Provider confirmation**: An attributed statement from BAFU about a finding or
correction, with its evidence and date. It does not establish release adoption.

**Reviewed consensus**: A revision-specific decision with the required reviews,
validation evidence and disposition of objections.

**Provider adoption**: Verification that a named official BAFU release contains
the correction. _Avoid_: treating a merged community patch as upstream-fixed.

**Recommendation**: An evidence-backed proposal addressed to the project that
owns the decision; delivery and response are recorded separately.
