# Frozen records, for tests

The finding records, the contribution records, the patch snapshot and the release list as they
were on 13 November 2026.

Tests of rules read these, never the records of the repository. A real finding has a life: it
gets a second measurement, is reported, answered, corrected or closed, and new findings arrive.
None of that may break a test, or every step would need someone to edit tests.

Do not update these files when a record changes. `community/tests/lifecycle_steps.py` checks
that the tests pass whatever happens to the real records. Only a change of the record format
changes these files, together with the records themselves.
