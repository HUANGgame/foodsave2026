# Batch 3: frontend contract integration (2026-10-06)

This is a reconstruction on the available Git source, not recovery of the old executor or the unpublished 0.4.10 source. Parent commit: `8558ca5b6a82de46764206c72de6c88059b6c918`. Branch: `foodsave-rebuild-20261006`. No production deployment or database mutation occurred.

## Source/contract audit and changes

| Area | Available old frontend | Rebuilt behavior |
| --- | --- | --- |
| Merchant entry | Logs out and requires a separate vendor login | Same-account `我要上架`; consumer with a store opens workbench, consumer without a store creates one; administrator entry retained |
| Creation | Waits for administrator assignment | `POST /vendor/store`, same permanent identity, one store per account enforced by backend; no registration call |
| Location | No owner location editor | GPS draft, draggable Leaflet marker/map selection, explicit create then public-location confirmation; GET/PUT location contract with `expected_revision` and `SAVE_LOCATION` |
| Move restrictions | No location revision/pending-order UI | Pending or expired unsettled orders block movement; conflict requires reload; server remains authoritative |
| Nearby | Global arrays plus local distance/radius filtering | Fixed 1km backend query and all cursor pages for both stores and products; publish complete pair atomically; no 200-row cap |
| Refresh | Timer captured old center; overlapping reads possible | Current center, cancellation on changed center/account/background; foreground 30s timer skips an in-flight read, including slow page chains |
| Consumer actions | Vendor role excluded | Merchant can use consumer actions; own product reservation and own-store favorite disabled; backend independently rejects self pickup/replay |
| Historical navigation | Navigation only on waiting pickup cards | Completed/cancelled/expired order navigation reads valid snapshot coordinates, never current store coordinates |
| Unknown mutation reply | Only persisted intent fingerprint | Memory-only original body allows same-key retry across closing/reopening; after app restart explicit reconciliation reads current same-account state before clearing only guarded store intent |

Reconciliation is limited to store creation (database owner uniqueness) and store location (revision compare-and-swap). A late original location write conflicts with a new write using the same fetched revision; the client never automatically reloads a newer revision and repeats a write. Successful account-bound read and unchanged intent are required before clearing the old intent. GPS/body/token are not written to localStorage. Ordinary reward, reservation and stock retry handling is unchanged.

## Backup and recovery

Before source changes:

- `/workspace/foodsave-rebuild/backups/batch3-before.bundle`
- SHA256 `db9fd05a756359859f486b7ebe07d6b27d01be92c199432bb0d661746a04cd1a`
- Manifest `/workspace/foodsave-rebuild/backups/batch3-before-files.json`
- Restore clone `/workspace/foodsave-rebuild/batch3-restore`: bundle verify and `git fsck` successful; all 261 tracked files matched the recorded hashes.
- Existing tracked source/test overwrites were made through `safe_edit.py`, which copies the prior file under `backups/edits/<timestamp>/...` and verifies equal SHA256 before writing.

Recover in a separate directory with `git clone /workspace/foodsave-rebuild/backups/batch3-before.bundle <new-directory>` and check out the parent commit above. Do not reset existing user work or force-push old branches. These are local source backups, not production SQL, deployed asset, or APK backups.

Independent reviewer `/root/baseline_review` verified the backup/restore and identified two blockers: restart recovery and starvation of slow page chains. Both were corrected and reviewed again. Final review checked this report and the test evidence and approved commit/push to the new branch; production deployment remains unapproved and blocked. Repeated clicks on the reconciliation read can produce a guarded conflict notice; they cannot issue writes or clear a changed intent.

## Verification in this environment

- Dependency install: first attempt failed because `/home/agent/.npm/_cacache` was unavailable; retry with `--cache /workspace/foodsave-rebuild/npm-cache` succeeded. No lockfile/dependency changes.
- `npx --no-install tsc --noEmit`: passed, including new tests.
- `NEXT_PUBLIC_APP_MODE=live NEXT_PUBLIC_API_BASE_URL=https://api.foodsave.test npm run build`: passed. This output targets a synthetic API, not production.
- `npm test`: 24 passed, 0 failed. Includes 300-row pagination, cursor-loop/partial-failure rejection, cancelled/session-superseded reads, snapshot navigation, unknown committed reply followed by restart/reconciliation.
- Live browser suite: 51/52 passed on the complete rerun with the project Python venv. The remaining new pending-order test selected both the application alert and Next route alert. After narrowing that selector, the entire seven-test location/nearby file passed, including the revised **background** 45-second page-chain case. Thus all 52 distinct tests have passing evidence; this was a full run plus targeted corrective rerun, not a single all-green run.
- Browser coverage includes same-account creation and first product, real Leaflet pointer drag in Chromium, explicit save/double-click lock, pending orders, 409/reload, lost reply/same-key retry after closing, restart/reconciliation, 201 visible products/own-item disabled, 30s refresh and historical snapshot link. Existing account-switch late success/401/network tests pass.
- Browser tests use intercepted synthetic API data, a synthetic local demo-prize backend where applicable, mocked GPS/camera, and desktop Chromium at 390×844. They are **not Azure SQL integration tests or physical Android tests**.
- `npm run lint`: cannot run: `Missing script: "lint"`. The repository has no ESLint configuration/dependency. Next's build message “Linting and checking validity of types” is not evidence of a configured standalone lint pass.
- `git diff --check`: passed. Backend source is unchanged in this batch; its prior 359 unit tests are recorded in batch 2 and are not represented as rerun here.

Local logs: `/workspace/foodsave-rebuild/batch3-unit-final.log`, `batch3-type-final.log`, `batch3-build-final.log`, `batch3-browser-final.log`, `batch3-browser-location-final.log`, `batch3-lint.log`.

## Boundaries and outstanding work

The available source retains its basic Leaflet map, header frog artwork, Google walking navigation and existing FamilyMart component. The 0.4.10 map search, frog location marker, follow mode, clustering, PWA/assets and exact visual behavior have **not** been recovered or shown equivalent. No changes were made to the navigation project, FamilyMart favorites or 7-11 functionality. A full 0.4.10-compatible production replacement is not ready.

Library materialization and Azure access blockers remain as recorded in the baseline; no bypass/retry was attempted in this batch. Migration 014 has not run on validation or production, location column permissions are not granted, and no real SQL integration/rollback validation has passed. No Azure website or backend version was changed. No paid resource or PAYG account was created; production PITR is not claimed as a free recovery plan. APK build/signature/versionCode/physical-device parity remains outstanding.
