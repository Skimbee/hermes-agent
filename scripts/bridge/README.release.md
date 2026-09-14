# Bridge release integration (v2)

## State

Publication requires `BRIDGE_RELEASE_ENABLED` to be explicitly `true` before the publisher job receives a token. The current repository variable and exact-head acceptance determine live state; this document is not an activation receipt. Landing this package does not change the production Hermes remote, client installation or Hindsight retention.

## Flow

`external hourly workflow_dispatch` → `candidate + bounded lock metadata reconciliation` → `frozen SDK/tests` → `isolated Dashboard E2E` → `bridge-release.yml`

The GitHub schedule is intentionally absent: one external scheduler owns the hourly trigger. The external scheduler never installs or publishes a candidate itself.

Release jobs are separate runners:

1. `verify`: read-only; authenticated GitHub run/workflow metadata, both archive digests, original receipts, bundle and Git ancestry, controller/attempt identity and external snapshot count. Produces immutable proof artifact.
2. `stage`: repository-scoped Contents/PR App token (conditional Workflows permission, below); re-verifies evidence, uploads the unchanged candidate and creates/reuses one App-authored PR.
3. `attest`: Checks-only App token; requires the completed verifier and stage jobs, re-verifies evidence, issues an exact-SHA check bound to run, attempt, proof artifact ID and canonical proof hash.
4. `publish`: Contents App token (conditional Workflows permission, below); re-verifies proof and completed predecessor jobs, validates App check, unchanged base and exact PR. Protected paths require Skimbee's current exact-head approval. Updates main with `force:false` and reads the exact target back. No merge API, rewritten commit or bypass.

The candidate/Dashboard source workflows must be completed successfully before verification. The release workflow itself necessarily remains in progress while it publishes; trust is attached to its **already completed verifier job**, not a falsely anticipated final workflow conclusion.

No-change candidate runs produce an original `no-change.json` receipt. After authenticated ancestry/identity verification, expensive E2E steps and all App jobs are skipped. No-change proofs cannot authorize publication.

## Bounded lock metadata reconciliation

A conflict-free Git merge can add an explicit `false` entry in
`tool.uv.exclude-newer-package` without adding its counterpart in
`options.exclude-newer-package` in `uv.lock`. The separate preparation step
reconciles **only missing explicit false entries for already locked packages**.
It does not infer exemptions, remove/change existing entries, regenerate a lock,
resolve dependencies, install packages, or change package versions/hashes.

- The helper is copied from the exact trusted `GITHUB_SHA` before the incoming
  merge, then run with Python isolation (`-I`). Incoming helper changes are not
  executed by the preparation step.
- Ambiguous package aliases, changed/removed exemptions, unrecorded packages,
  unsupported lock schemas/formatting and linked input files fail closed before
  mutation. The complete parsed lock outside the added options must stay equal.
- A repair is committed on the disposable candidate before `uv lock --check`,
  frozen installation and all regression gates. The original candidate receipt
  includes the reconciliation hashes/options and names the final tested commit.
- A consistent lock remains byte-identical. A no-change run skips this step and
  keeps its successful no-op receipt; a still-pending failed candidate is not a
  no-op just because the previous hourly attempt saw the same upstream.
- `uv lock --check`, tests, provenance checks and review policy remain mandatory.
  Unsupported inconsistencies are real errors, not silently green results.

The helper prevents this narrowly supported metadata omission from repeatedly
blocking otherwise valid incoming candidates. It cannot guarantee that new
upstream code or other dependency changes pass all gates.

## Review policy

Protected fork-owned paths: `.github/workflows/bridge-*`, `scripts/bridge/**`,
all three recognized `CODEOWNERS` locations, and
`tests/plugins/memory/test_hindsight_pin_contract.py`. The pin regression gate
and all existing candidate/SDK/isolated Dashboard checks remain mandatory.

For other changed `.github/**` and `scripts/**` files, the trusted verifier
compares Git mode/type/blob identities against both the official upstream and
the merge base. Only changes identical to upstream **and** replacing a base
file identical to the common ancestor are routine. New upstream files and
upstream deletions are supported; fork-only edits/deletions or overwritten
fork customizations still require exact-head owner review. Renames cannot
hide a protected deletion. This classification comes from the verified Git
trees, not a path list supplied by the candidate.

Before granting an upstream exemption, the verifier fetches the official
`NousResearch/hermes-agent` main and proves that the receipt's upstream commit
is on that history. It never checks out or executes candidate code. Existing
customizations in ordinary runtime files remain subject to the focused
regression gates; this policy does not freeze whole upstream runtime files.

Target protection: App 4931424's `Bridge release / exact-candidate`, strict checks, admin enforcement, code-owner reviews, stale review dismissal, no force-push/deletion; general approval count 0 and last-push-global-approval false. The earlier broad-path combination was proven on `lab-selective-review` (not live acceptance of this selective policy): routine changes published exactly without a review; protected changes were rejected by GitHub with `Waiting on code owner review from Skimbee.`

**This repository's live rules have not been changed by the code package.** The integration rollout must separately compare the entire protection before/after and preserve everything except the explicitly intended two review settings.


## Protection trade-off and regression contract

Outside the explicit CODEOWNERS entries, detected fork control overrides are
protected by the trusted verifier, not independently by GitHub CODEOWNERS.
This is deliberate: upstream files must remain updatable. Ordinary upstream
regression tests may evolve; their immutability is not promised. The fork-owned
Hindsight pin test, bridge controller and its hard SDK check remain protected.
Changes to those contracts require owner review. Candidate regression success
alone is not proof that upstream code or its tests are benign.

## App permission boundary

Workflow-write activation is an explicit deployment gate, **off when unset**.
The controller reports `workflow_write_required` from its verified proof.
Only `stage` and `publish` request repository-scoped Workflows write, only
when that output is true and the repository variable
`BRIDGE_WORKFLOW_WRITES_ENABLED` is exactly `true`. `attest` remains Checks-only;
no Administration permission is requested. Expanding the App's installation
permission and enabling the variable require a separate owner decision.

With activation enabled, stage may upload workflow changes automatically only
when **every** changed workflow is an unchanged upstream import and none is
protected. Protected or fork-modified workflows keep the exact-bundle owner
upload path. Existing exact branches are reused, never rewritten. Publication
still requires owner approval whenever any protected path changed, and retains
the exact App check, fresh-base checks and `force:false` readback.

Workflows write is also conditionally requested for publication: staging a Git
object is not evidence that a Contents-only token can advance main to a changed
workflow tree. Missing activation fails explicitly before a workflow write;
no retry, fallback credential or permission escalation occurs.

### Deployment and rollback

This code does not grant GitHub permissions or activate repository variables.
Before merge, independently review this policy change and verify exact-head CI.
Record the current CODEOWNERS, App installation permissions, activation-variable
presence/value and complete branch protection. Keep branch protection unchanged.
Under separate owner approval, grant this App Workflows write for this repository
and activate `BRIDGE_WORKFLOW_WRITES_ENABLED=true`. Then exercise a fresh complete
candidate/Dashboard/release chain. Local/synthetic tests do not replace that live
acceptance. Never reuse a proof bound to a previous main.

Rollback first disables workflow writes (restore the previous variable state);
then removes the added App permission under the approved rollback contract.
Restore the prior reviewed policy through a normal protected change if needed,
not a force-push or protection bypass. An in-flight run needs an explicit decision:
do not revoke credentials mid-write or assume changing a variable cancels a run.

Upstream workflows can execute already when the candidate branch is staged
or its same-repository PR opens, BEFORE publication or owner review. Provenance
is not a guarantee of benign code. Keep App keys in the main-only publisher
environment, default GITHUB_TOKEN read-only, and review repository-secret
exposure before enabling workflow writes. Adopted actions may use mutable tags;
only our bridge workflows are SHA-pinned by the local contract checker.

## Resume after a manual gate

After the exact branch has been uploaded by the owner, or after the owner approved the exact PR head, start a **new complete workflow dispatch**:

```bash
gh workflow run bridge-release.yml --repo Skimbee/hermes-agent --ref main -f dashboard_run=THE_ORIGINAL_DASHBOARD_RUN_ID
```

Do not choose **Re-run failed jobs**: that creates an attempt without its own completed verifier job/proof. A review event does not automatically trigger publication. Reuse the original Dashboard run only while main still equals its recorded base; otherwise run a fresh hourly candidate plus Dashboard E2E. Never carry old attempt proofs forward or reinterpret a stale review.

## Acceptance boundaries

- Policy, provenance, snapshot and stateful synthetic API integration tests are not a full live fork release.
- The existing container E2E was live verified in the separate lab. The adapted fork workflow and its complete release chain still require acceptance after the reviewed bootstrap.
- New fork-owned or unverified control files require owner review. Exact, unchanged upstream imports follow the provenance policy above.
- Automated releases retain their exact candidate/App evidence requirements; owner maintenance uses the separate documented PR-only route in README.maintenance.md, never a fabricated release check.
- Candidate-controlled UI/receipt observations plus a trusted tracked-tree snapshot do not prove benign runtime code or every unversioned dependency.

## Tests

```bash
python3 -m unittest discover -s scripts/bridge -p 'test_*.py' -v
uv run --no-project --with PyYAML==6.0.3 python3 scripts/bridge/check_workflows.py
```

`bridge-release-ci.yml` runs these checks without App/environment access on the integration branch and relevant PRs. The downstream preparation interoperability test requires the trusted hosted runner's `git check-attr --source`; absence is a failure there. The older Git inside the candidate sandbox is not that controller's execution target, so only this separate interoperability test may skip there. The core reconciliation/commit/receipt test always runs, and the required exact-head hosted CI covers the controller test.
