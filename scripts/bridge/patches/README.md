# Candidate-only compatibility patch

`legacy-file-signature.patch` is the exact binary-capable Git diff of production
fix `d44af15402957b31c13574a73de35741b825e579` against its parent
`ac36de1d2a675c11ff67bacef6df30c2b60ce016`.

The Bridge base predates the upstream signature helper, so the fix cannot be
applied directly to that base. The hourly workflow freezes this patch from its
own workflow SHA before merging incoming sources, applies it with `git apply
--check --index` after the merge, and commits it before lock reconciliation,
regression tests and exact-candidate bundle/receipt creation. The patch moves
the existing stat-signature implementation unchanged into a dependency-free
module and changes its consumers. It includes the legacy cached-utils import
and receipt-persistence regressions, which run in the hourly gate.

Patch drift fails closed: do not ignore failures, automatically reverse the
patch, or alter the installed old base. If upstream adopts or changes this fix,
review and remove/update the patch and assembly step together.

The Dashboard client base remains
`d131988d53c3b8389801f6cee03b990bd51ac49a`, with no bootstrap or monkey-patch.
The inherited 900-second polling deadline, diagnostic sanitization, main-only
trusted evidence and exact-candidate release gates are unchanged.

A feature-branch hourly run is an assembly/CI rehearsal, not publishable
Dashboard evidence. The authenticated Dashboard consumer requires candidate
runs from current `main`; control changes require review and explicit merge
authorization before the real E2E can accept a newly assembled candidate.
