---
status: proposed
---
# Preserve the community pipeline in the consolidated repository

Consolidate the two repositories into one shared repository, preserving both
Git histories. Chris and Laurenz will choose the final name in
[#25](https://github.com/sentier-dev/sentier-bafu/issues/25). On 13 October 2026 Manuel Klarmann chose `bafu-community-fixes`
as authoritative where implementation or interpretation conflicts. Its package,
CLI/TUI, import fixes, patches, tests and report remain the executable
foundation; the existing findings and contribution history remain the review
record. This avoids maintaining two competing patch engines.

Keep `bafu-community-fixes`, `bafu_community_fixes`, `bafu-fixes`,
`bafu-fixes-tui` and `urn:bafu-community-fixes:extensions:1` stable through the
repository rename. A repository's display name is not a reason to break these
interfaces. Preserve author and confirmer metadata without synthesizing new
approvals. The old repository remains active until its maintainers accept the
migration and resolve its two existing assignments.

The initial history-preserving merge is behavior-preserving. New review
capabilities arrive in separate changes after parity. The migration matrix
records every file and every deliberate reconciliation.

Laurenz Bougan agreed with the content on 14 October 2026. It stands as
accepted once Chris Mutel confirms it in
[#18](https://github.com/sentier-dev/sentier-bafu/issues/18).
