# Release preparation — fixed application commit 1a5a6d6

**Not deployed; no SQL, grants, Azure resource changes, or chargeable operations executed.** These tools prepare/audit the existing application commit `1a5a6d6ab9a5c098c46d54601a677eec18323143`. No batch-4 search/map work is included. The original rebuild branch is retained; preparation is on `foodsave-release-prep-20261006`.

## Validation database, not production

Use the existing **empty** `foodsave-validation-20261006` only. Do not use the old `owner_migrate.py`: it hardcodes `foodsave`. Never use the unavailable historical migration013 ZIP.

1. Review `source-hashes.json` and the unchanged `backend/migrations/001–014` from the pinned application commit. 013 here only adapts two procedures for consumer store owners; it does not rewrite owners, users or sessions. 014 adds location columns/defaults; no grants.
2. `python release/20261006/validate_sql.py` is a no-connect plan. It checks every pinned backend/migration hash before considering a connection. Review the exact target and adapted hashes.
3. Only in the authorized existing SQL-capable environment, privately inject `FOODSAVE_VALIDATION_ODBC_CONNECTION` for the already-authorized validation owner (existing installed ODBC driver, `Encrypt=yes;TrustServerCertificate=no`). Never put the connection value in this repository, command history, output, Library or chat.
4. After reviewing the script, run `python release/20261006/validate_sql.py --run-rollback`. It refuses every other actual DB name, requires existing CONTROL and a completely empty user-object catalog, creates no resource or user, and grants nothing. All DDL, schema markers and synthetic data are inside one transaction, always rolled back. It rechecks an empty catalog through a new connection on success. Failure reports rollback as **unverified**; privately confirm cleanup before retrying. Do not infer rollback verified from an exception or process termination.

SQL execution deliberately keeps each whole migration in a separate batch. CREATE PROCEDURE files 005/008/009/010/011 cannot have SET or guards prepended. There are no GO delimiter lines; the script refuses them instead of implementing an unsafe text splitter. It sets filtered-index ANSI options, XACT_ABORT and lock timeout separately, takes a transaction-owned applock, records markers in the same transaction, then repeats the migration loop and requires 0 reapplied files. Rerunning the command after successful rollback starts from the same empty DB.

012's **single exact database guard** is adapted in memory only after all source hashes pass. The original file stays unchanged. No global string replacement. 006 creates `ux_stores_single_owner` once; 013 only checks it. The runner independently verifies unique/enabled/nonhypothetical/nonclustered, exact owner_id key and non-null filter. Existing partial schemas, missing-marker/nonempty states or alternative indexes are refused, not “repaired” or marked applied.

The prepared SQL checks cover DDL compilation, marker rerun, index shape, unpublished store creation, one-store ownership, location revision/idempotency, cross-store denial, self reservation denial, snapshot, waiting/expired blocking, settlement/move, actual T-SQL 305-product pagination/distance filtering and both 013 procedure paths. They are **not yet executed**. CONTROL-owner success would not prove restricted-runtime rights, parallel two-connection races, performance, deployed HTTP/CORS, old-session preservation on a populated production migration, or Android. Do not run this empty-DB harness on production. Production upgrades need a separately reviewed schema diff and preserved-data rehearsal; markers alone are not proof of schema equivalence.

## Runtime identity and exact permission delta

The actual runtime SQL principal/SID is **not known in this workspace**. The App Service display name is not a verified principal. Retrieve and compare the existing managed identity's object/application IDs and contained SQL principal privately in the authorized environment; do not create a replacement principal or grant a role.

`runtime-preflight.readonly.sql` is an owner-run metadata-only template, stopped by placeholders until the exact existing principal and SID are verified. Review existing role memberships, direct grants/DENYs and schema before any change. Relative to the already-complete, verified 001–012 runtime permission set:

| Need | Exact scope | Change |
| --- | --- | --- |
| Explicit store position save | `UPDATE(latitude, longitude, location_confirmed, location_revision)` on `dbo.stores` | Only proposed new grant |
| Read/create own store | Existing `SELECT, INSERT` on `dbo.stores` | Verify, do not blindly regrant |
| Self-service account reads and mutation lock | Existing SELECT on users/stores; existing request_results SELECT/INSERT and audit INSERT | Verify |
| 013 procedures | Existing EXECUTE on `dbo.close_vendor_business`, `dbo.report_stock_loss`; same dbo ownership chain | Verify; no additional base-table DELETE/UPDATE grant |
| New schema readiness | Existing SELECT(version) on `dbo.schema_migrations` | Verify |

`runtime-location-grant.review.sql` is **not authorized for execution by this preparation task**. It stops with Approved=0, placeholder principal and null SID. Any future authorization must cover the exact existing identity and four columns. No owner_id UPDATE, table-wide UPDATE, CREATE USER, role, CONTROL, ALTER, IMPERSONATE or GRANT OPTION is proposed. No attempt was made to modify actual permissions. Do not run the initial broad runtime-grants template against an existing principal.

## Build and artifacts

`build_candidates.py --output <new-private-directory>` extracts application files using `git archive` of the exact commit, uses installed pinned npm dependencies, and builds in isolation. It sets:

- `NEXT_PUBLIC_APP_MODE=live`
- `NEXT_PUBLIC_API_BASE_URL=https://foodsave-web-tku-aqhxdnhpe8fdhfee.eastasia-01.azurewebsites.net`
- Existing tracked public privacy/operator/contact settings, including `NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE=false` (unchanged).

The current `npm run build:release` gate fails for unconfirmed application ID and incomplete privacy flag. Preparation does **not** fake those values: ordinary `npm run build` produces a **candidate**, not a gate-approved release. No Android package ID/signature is invented. The tracked privacy text also predates server-side nearby-coordinate querying; do not mark it complete without reviewing that accuracy.

The frontend static export built successfully against the formal API and contains no `api.foodsave.test`. However, unchanged AppEntry statically imports FoodApp, so Next still bundles the old demo store/product sample data (`lib/demo.ts`). Thus the fixed-commit frontend cannot satisfy “no test data”: its ZIP is **quarantined, not a compliant deliverable**, and must not be uploaded to production. Removing that data needs a small reviewed packaging/source change and fresh full tests, not hand-deleting a referenced JS chunk. No such application change was made here.

The backend ZIP is a root `foodsave/` package plus `requirements.txt`, without tests/QA, migrations, owner/erasure/diagnosis/CLI tools, secrets, environments, dependencies or credentials. The default demo-prizes seed file is omitted to satisfy the no-test-data requirement. If the current formal service has the optional demo feature enabled, its **actual separately stored configuration must first be backed up and verified**; otherwise omitting its fallback can break that feature. Do not silently disable it or substitute new sample values. This remains a deployment check/blocker.

Backend candidate import and `/health/live` pass locally without DB. It is not a self-contained App Service binary: verify existing Python/ODBC runtime, startup command, persistent configuration and the existing deployment/build behavior before uploading. Suggested command from the pinned source is `python -m uvicorn foodsave.api:app --host 0.0.0.0 --port 8000 --no-proxy-headers`; do not replace the actual configured command without comparing it. A ZIP upload may replace/remove existing wwwroot files; do not upload until the backup is verified.

## Existing production backups and handoff

The parent conversation reports Azure Portal's existing login, SWA SwaCli/productionReady and App Service F1 Running/manual ZIP UI. This does not give this executor Azure connectivity or prove the UI can access these local files. Git push/pull is the only already-verified source transfer here. Library delivery, if successful, supplies downloadable files, not proof of Azure upload/deployment.

Before any overwrite, in that authorized environment:

1. Download the current App Service deployed wwwroot through its **existing authorized** Kudu/SCM file/download facility or known previous deployment artifact, if available. Include actual persistent demo configuration separately. Verify archive contents and SHA256 locally; if that facility is unavailable, stop rather than assume a backup exists.
2. Privately export/record current app settings, connection strings, startup/runtime/ODBC, identity and deployment/build flags. These may contain secrets: keep owner-only encrypted/private storage; **never** put the settings export in this repository, Library deliverables or public Git. Verify it can be read back privately.
3. Recover the currently deployed SWA static artifact from the existing trusted SwaCli/CI artifact source, or a supported export if available, with all assets and manifest/hash. SWA “productionReady” and the visible homepage are not a verified whole-site backup. In this environment that artifact is still unavailable.
4. Separately establish a database recovery plan and scope. Git/runtime ZIP backups contain **no SQL data**. Existing PITR may cost money to restore; no free restore is assumed. The blank free validation DB is a test target, not a production backup. No BACPAC export, restore/new database or paid resource has been started.
5. After SQL/runtime authorization and real validation, deploy compatible backend first, verify `/health/ready` and real login/nearby/create/location behavior, then a gate-approved frontend. Do not copy this frontend over 0.4.10: feature equivalence and sample-data removal remain unresolved. Old-backend rollback can expose new location drafts; Git rollback alone is unsafe.

## Evidence and stop point

- Application commit full browser suite: **52/52** in `/workspace/foodsave-rebuild/batch3-browser-full-commit.log`; still mock/synthetic API evidence.
- Preparation source hashes, no-connect plan and batch/guard tests pass locally. No new Azure call, SQL execution, permission change, paid resource, production ZIP upload or deployment occurred.
- Before preparation: bundle `release-prep-before.bundle`, SHA256 `2971062248251b35d803c7af1099565eb85232713a9671700ac7d03aaec17ef8`; independent restore/fsck and 269 tracked-file hashes matched.
- Paused batch-4 files remain archived outside the repository and are not packaged.

The requested endpoint remains: only finish the necessary approved release work, verify the deployed result, then stop. Do not restart feature reconstruction.
