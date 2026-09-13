# Bridge release integration (v2)

## State

Implementation candidate. Publication is default-off; `BRIDGE_RELEASE_ENABLED` must be explicitly `true` before the publisher job receives a token. Landing this package does not change the production Hermes remote, client installation or Hindsight retention.

## Flow

`hourly candidate (17 * * * *)` → `isolated Dashboard E2E` → `bridge-release.yml`

Release jobs are separate runners:

1. `verify`: read-only; authenticated GitHub run/workflow metadata, both archive digests, original receipts, bundle and Git ancestry, controller/attempt identity and external snapshot count. Produces immutable proof artifact.
2. `stage`: repository-scoped Contents/PR App token; re-verifies evidence, uploads the unchanged candidate and creates/reuses one App-authored PR.
3. `attest`: Checks-only App token; requires the completed verifier and stage jobs, re-verifies evidence, issues an exact-SHA check bound to run, attempt, proof artifact ID and canonical proof hash.
4. `publish`: Contents-only App token; re-verifies proof and completed predecessor jobs, validates App check, unchanged base and exact PR. Protected paths require Skimbee's current exact-head approval. Updates main with `force:false` and reads the exact target back. No merge API, rewritten commit or bypass.

The candidate/Dashboard source workflows must be completed successfully before verification. The release workflow itself necessarily remains in progress while it publishes; trust is attached to its **already completed verifier job**, not a falsely anticipated final workflow conclusion.

No-change candidate runs produce an original `no-change.json` receipt. After authenticated ancestry/identity verification, expensive E2E steps and all App jobs are skipped. No-change proofs cannot authorize publication.

## Review policy

Protected paths: `.github/**`, `scripts/**`, root `CODEOWNERS`, `docs/CODEOWNERS`.

Target protection: App 4931424's `Bridge release / exact-candidate`, strict checks, admin enforcement, code-owner reviews, stale review dismissal, no force-push/deletion; general approval count 0 and last-push-global-approval false. This combination was proven on `lab-selective-review`: routine changes published exactly without a review; protected changes were rejected by GitHub with `Waiting on code owner review from Skimbee.`

**This repository's live rules have not been changed by the code package.** The integration rollout must separately compare the entire protection before/after and preserve everything except the explicitly intended two review settings.

## App permission boundary

No Workflows or Administration permissions are introduced. An App token with Contents write cannot upload a changed `.github/workflows/` tree. For such candidates, the authorized owner uploads the exact verified bundle to `bridge/candidate/<SHA>` without changing main. The App can then reuse the exact branch and create the review PR. The code refuses an automatic upload in this case; it never silently requests a broader token.

## Resume after a manual gate

After the exact branch has been uploaded by the owner, or after the owner approved the exact PR head, start a **new complete workflow dispatch**:

```bash
gh workflow run bridge-release.yml --repo Skimbee/hermes-agent --ref main -f dashboard_run=THE_ORIGINAL_DASHBOARD_RUN_ID
```

Do not choose **Re-run failed jobs**: that creates an attempt without its own completed verifier job/proof. A review event does not automatically trigger publication. Reuse the original Dashboard run only while main still equals its recorded base; otherwise run a fresh hourly candidate plus Dashboard E2E. Never carry old attempt proofs forward or reinterpret a stale review.

## Acceptance boundaries

- Policy, provenance, snapshot and stateful synthetic API integration tests are not a full live fork release.
- The existing container E2E was live verified in the separate lab. The adapted fork workflow and its complete release chain still require acceptance after the reviewed bootstrap.
- New control files must receive human codeowner review before they become trusted main code. No further Admin exception is permitted.
- Bootstrap requires an App-authored PR, exact-head independent evidence, owner approval and the existing App-issued required check. A regular squash/rebase/merge that changes the tested SHA is not a substitute.
- Candidate-controlled UI/receipt observations plus a trusted tracked-tree snapshot do not prove benign runtime code or every unversioned dependency.

## Tests

```bash
python3 -m unittest discover -s scripts/bridge -p 'test_*.py' -v
uv run --no-project --with PyYAML==6.0.3 python3 scripts/bridge/check_workflows.py
```

`bridge-release-ci.yml` runs these checks without App/environment access on the integration branch and relevant PRs.
