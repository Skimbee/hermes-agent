# Owner maintenance, without a second release pipeline

## Two distinct paths

- **Automated upstream release:** unchanged exact candidate, Dashboard evidence,
  App 4931424 check, provenance and protected-path owner approval. The bot does
  not receive an exception or Administration permission.
- **Owner maintenance PR:** same-repository Skimbee-authored PR, current main,
  green exact-head `contracts` from GitHub Actions, independent Opus high review
  assessed by Karl, and Sven's change authorization. Use a normal merge commit
  and verify its parents/tree. Do not pretend this is a Dashboard release.

The GitHub ruleset proposal carries the existing App check and owner review
rules, with a **repository admin PR-only bypass**. At initial preflight Skimbee
is the only administrator. This is an explicit exception, NOT a new hard
GitHub-enforced Opus/CI approval. Owner discipline enforces those extra gates;
GitHub cannot validate a local Opus assessment. New admins would inherit the
exception and therefore require access review. This is the standing human PR
route, not a one-time exception. Owner account tokens must not be handed to
untrusted automation; protect the account with strong authentication. Non-admin automation cannot use
it. CODEOWNERS remains useful for the automated path and review routing.

Classic protection retains enforce-admins, no force pushes, no deletions,
conversation resolution, and the previous non-review settings. Only its
required checks/review rules move to the ruleset. No exception applies to the
classic force-push/deletion restrictions. No direct main push is authorized.

## Initial installation: before / after / rollback

1. Save the full live protection, rulesets and administrator list. Verify main,
   PR head, no active publisher, exact-head CI, and reviewed source hashes.
2. Create the equivalent ruleset with its PR-only admin exception FIRST.
   Read it back and verify its full semantics. Existing classic checks remain
   active during this step; this cannot unblock the PR yet.
3. Only after verified laboratory probes (bot routine accepted, owned path
   rejected without approval, owner direct push rejected), remove duplicate required-check/review clauses
   from classic protection, preserving all other fields. Read back both layers.
4. Verify the maintenance PR can merge through the PR-only exception. Merge the
   reviewed head with expected-head protection; never force push. Read back PR,
   resulting main, parent commits, and tree equality to the reviewed candidate.
5. Keep workflow-write activation OFF. Separately validate that automatic
   publication still satisfies the ruleset before enabling a fresh live run.
   Neither local tests nor a maintenance merge prove the automated publisher
   is accepted by GitHub after this migration.

Rollback before merge: restore the original classic protection FIRST, read it
back, then remove only the newly created ruleset by its recorded ID. Never
remove the ruleset before the old check/review barrier is restored. Partial
failures stop; use the saved original payload, not the changed live state.
A completed merge is reverted by a reviewed revert PR, not by resetting main.

## Exact classic target payload

The full PUT payload is explicit; omitted fields must not reset protection:

```json
{
  "required_status_checks": null,
  "required_pull_request_reviews": null,
  "enforce_admins": true,
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
```

GitHub may add conservative defaults to the ruleset response. Compare every
requested field, record the returned defaults, and verify the actor is admin
with `current_user_can_bypass: pull_requests_only`. Do not widen bypass actors.

## Minimal operator procedure

Inspect PR head/base and all checks fresh. Resolve all review conversations:
classic conversation resolution remains enforced even for the administrator. Run `maintenance_policy.validate`
with the independently assessed review's exact head. This is a preflight helper,
not an autonomous approval or merger. Ensure `main` is contained in the head;
if base or head moved, re-test and review the changed delta. Record the review
artifact and assessment, then perform the PR merge and verify parent/tree
identity. Do not automatically retry a failed merge or change branch rules to
make a failing test pass.

`bridge-release-ci.yml` now runs on every PR and explicitly checks out the PR
head, not GitHub's synthetic merge ref. There is no paths-filter deadlock when
a future maintenance PR touches another file. This small CI tests the bridge
contracts; apply task-specific tests as well. CI alone does not establish the
independent review or benignness of arbitrary candidate-controlled tests.
