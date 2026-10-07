# Validation preparation — application candidate 3b6435b

**No SQL, grants, deployment or chargeable operations executed.** This validation runner and `source-hashes.json` now pin the exact application candidate `3b6435beb834c161a17a879430119f5c53ea45a0`. Its API ZIP SHA256 is `7c99dc6c200332402e7bbc9fbe2caa90249fdb12bdb7d2481d9431cdf60b90f9`.

Use this preparation commit's complete checkout (backend plus release tooling), not the old 6fc637d validation ZIP. The application pin intentionally remains 3b6435b even though the preparation-only commit has a newer SHA. Each pinned source byte must match before a connection is considered. The backend runtime/migration path set is unchanged; only account_mail.py's digest differs from the old manifest. Requirements and migrations are unchanged.

Historical source-hashes and README are preserved byte-for-byte under `history/`; the old runner is preserved in Git commit `6fc637d18e9430ebf98c2ead27dc8aaab755429c`. Historical manifests are not selectable overrides. No hash checks or SQL protections were removed. The runner change is only its SOURCE constant.

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

## Candidate and remaining blockers

Use `build_backend_candidate.py --source 3b6435beb834c161a17a879430119f5c53ea45a0 --output <new-private-directory>` for the current backend candidate. The historical `build_candidates.py` still pins 1a5a6d6 and must not build the current release. The current backend includes the verified 805-byte public fictional demo fallback and approved continuous-mail semantics; no production persistent store is created. The coordinator privately backed up the production runtime archive; it is not a SQL/config backup and was not imported into this executor.

The separately built frontend candidate remains pinned to ae4c6bb070a9bfd20dc09f3321cf4330e0c7d7e0. It passed the demo-catalog scan; no frontend rebuild or data insertion is part of this preparation update. Its release gate still requires verified application ID and approved frontend privacy completion. Policy amendment remains pending; no completion flag is changed. Verify the actual existing APK identity/signature, never infer it from the repository's tw.foodsave.demo default.

Preparation tests verify the new pin against Git bytes, no-connect plan, exact migration guard handling, hash rejection and connection-string validation. Passing these does not mean SQL integration passed. The existing empty validation database remains the only allowed SQL target, and this task does not execute SQL.

Before editing, source backup `validation-repin-20261006-before.bundle` was verified/restored/fsck checked with 287 matching files; SHA256 `5e255963e5e4b3b4a29b4126370a17d86ceebdbe6c2a0c8987271aae2958cb72`. Changed existing files also have separately verified overwrite copies. Independent review precedes commit. Production SQL/config recovery, runtime identity/permissions and an authorized deployment route remain separate prerequisites.
