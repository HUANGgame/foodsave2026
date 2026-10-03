# Auth012 owner erasure increment

No runtime/DDL/grant/resource/scheduler change. Owner migration prerequisite becomes012. Exact-email applock precedes UPDLOCK on the user, matching account mutation order; the erasure lock remains outermost. Challenge deletion and verified_at clearing share the account's existing PII transaction, so failure rolls back the phase.

Only4 known email rate buckets can be deleted: login:email, auth:mail:email, auth:finish:email, deletion-public-account, and only when window_start is at least900seconds old. Active email counters, user/peer/global/monthly budgets and the once-only probe remain untouched. This removes the previous unconditional deletion-public-account reset. A delete request cannot buy fresh active auth/email/global cost quota.

PII phase response explicitly says active_auth_counters_not_reset=true. For any retained active email identifiers, operator must follow up under the same approved request after the window expires using `owner_erase.py --auth-counter-cleanup` with email-only JSON via stdin (not shell args or logs), existing owner connection arguments and policy. Default is dry-run; `--apply` requires approved enabled policy. This mode deletes no users/challenges/business rows and outputs no email. No automatic retry/reset. Do not declare all identity traces cleared before follow-up. Existing support/request handling remains responsible for associating the original email; this patch creates no new tracking store.

Owner run's existing bounded housekeeping adds at most100 expired challenges per apply invocation. API cleanup remains best-effort. Fifteen-minute code validity does not promise immediate physical deletion; no schedule is added.

`qa/auth_erasure_rollback.py` is PLAN ONLY without --run-rollback. With explicit server/installed driver and existing human-owner login, it verifies foodsave/schema012/CONTROL, inserts2 random synthetic disabled users,2 tickets,8 quota fixtures, invokes actual helper methods, checks rollback restoration, target-only erasure, active counters retained, later expired counters removed, unrelated/probe sentinels intact, then always rolls back and asserts zero residual. Global sentinels are synthetic keys, never real live global buckets. Driver timeout30s/lock timeout5s; worker should add total timeout60s and close process/connection. No mail or new grant. It does not prove whole-business erasure, concurrency, provider logs or backups.

The owner ZIP contains the helper and QA. Runtime ZIP/API behavior is unchanged by this increment. No real SQL or account deletion has been run locally. TEST_PRIVACY_DRAFT.md is a review draft; policy flags remain off and APK copy is not yet changed.

### QA recovery manifest (2026-10-03)

The tracked `backend/qa/auth_erasure_rollback.py` now requires
`--recovery-manifest /private/new-name.json` alongside existing execution arguments.
It exclusively creates/fsyncs a mode-0600 file before any fixture SQL, containing
only the random marker, synthetic user UUIDs, challenge hashes and derived counter
hashes. Keep it private for exact recovery checks; do not upload it to this repo.
Existing files/symlinks are refused. No real email or password is recorded.

After the fixture connection is rolled back and closed (including failure paths),
all three residual tables are checked separately through fresh connections, with
30-second command and 5-second lock timeouts. Each table reports its residual count
or a safe exception class/SQLSTATE; a failed check never counts as zero. Fixture and
rollback errors are reported without driver messages or SQL parameters. No COMMIT,
new grants, business-erasure changes, or automatic cleanup are introduced.

Local recovery tests: 3 passed. This is not a live SQL acceptance result. A worker
hard timeout/process kill can prevent automatic rollback verification: retain the
manifest for independent exact-key SELECTs and do not claim acceptance until all
three counts are independently verified as zero.
