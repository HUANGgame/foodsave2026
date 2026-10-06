# Live bundle release blocker fix

Parent preparation commit: `6fc637d18e9430ebf98c2ead27dc8aaab755429c`; application ancestor: `1a5a6d6ab9a5c098c46d54601a677eec18323143`. Branch: `foodsave-live-bundle-fix-20261006`. No deployment, SQL, permissions, registration flags, package identity or signing changes. Paused batch-4 work remains separate.

## Exact cause and minimal change

`components/AppEntry.tsx` statically imported the client component `FoodApp`. That module imports `lib/demo.ts`, `VendorProducts` and the demo `Map`. Returning null for live mode did not remove that static client reference from Next's emitted client graph. The previous formal-URL build contained the three seed store names and five product names in `out/_next/static/chunks/342-4fda2f58035f41cf.js`.

The static import is replaced by a require inside the **direct build-time** `NEXT_PUBLIC_APP_MODE==='demo' || !NEXT_PUBLIC_APP_MODE` branch. Webpack omits that dependency for live builds. Explicit demo and the existing unset-mode fallback remain functional. ConvenienceApp, LiveShell and all live API behavior are unchanged. No framework replacement, generated-chunk deletion, backend seed edits or new product features.

`scripts/check-live-bundle.cjs` scans every emitted output file for all eight known demo catalog names, Unicode-escaped equivalents, selected fixture markers, test/config paths, the expected HTTPS API and an accidentally retained fixture API. It has negative unit tests and is now the final step of `npm run build:release`, after the existing release gate and build. It does not contact any API and is not a general secret detector or proof of all possible data absence. The artifact contains no demo catalog/fixture data found by the audited source graph and byte scans; the live `/demo-prizes` feature remains intentionally present and obtains its real configured data from its API.

## Validation completed in this workspace

- Live build at fixture API: full browser suite **52/52** passed in one run, 26 frontend unit tests passed, TypeScript passed.
- Demo build: full original browser suite **6/6** passed, retaining existing demo-only behavior.
- Formal API build (`https://foodsave-web-tku-aqhxdnhpe8fdhfee.eastasia-01.azurewebsites.net`): build passed, all **52 output files** passed the live bundle scan. Existing public privacy template values were retained, including privacy-complete=false.
- Formal-URL artifact smoke: real Chromium with every remote request intercepted locally; login and same-account merchant entry passed without registering/logging out, no page errors. This never contacted Azure and does not prove HTTP/CORS/SQL/real credentials.
- Complete backend suite rerun: **359 passed**, one existing Starlette/httpx deprecation warning. Preparation checks: **17 passed**. Neither is a new real-SQL validation result.
- `git diff --check` passed. There remains no configured standalone lint command; no lint-pass claim.

Logs are under `/workspace/foodsave-rebuild/`: `live-bundle-fix-browser.log`, `live-bundle-demo-browser.log`, `live-bundle-fix-unit-final.log`, `live-bundle-fix-type-final.log`, `live-bundle-formal-browser.log`, `live-bundle-fix-backend.log`, `live-bundle-fix-preparation.log`. Formal candidate build evidence/scan are in `live-bundle-fixed-formal/`. A final ZIP must be rebuilt/pinned to the new fix commit; the old `release/20261006/build_candidates.py` still intentionally pins 1a5a6d6 and **must not** be used unchanged to package this fix.

## Exact remaining release-gate fields

`scripts/check-release-config.cjs` is the existing gate invoked by `package.json`'s `build:release`. With the already tracked public operator/contact/retention template and formal API, it reports exactly:

- `FOODSAVE_APPLICATION_ID` missing. `capacitor.config.ts` defaults to `tw.foodsave.demo`; `android/app/build.gradle` namespace is `tw.foodsave.demo` and applicationId takes the `foodsaveApplicationId` Gradle property, also defaulting to `tw.foodsave.demo`. The gate explicitly rejects that demo value. The tracked Android version is code 7 / `0.4.1-policy-test`, release signing is not configured. This does **not** establish the actual installed 0.4.11 APK applicationId or signing certificate. No value was invented; package name, version and signing remain unchanged. The gate currently shares this Android requirement with the web release command; it was not weakened here.
- `NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE` must be `true`. The tracked `infra/privacy-public-settings.example.json` keeps both frontend and backend completion flags `false`. The existing policy file says HUANG finalized a low-traffic public-test policy; that statement does not prove the current Azure settings or a new release's data flows. The operator `HUANG`, contact `413637629@o365.tku.edu.tw` and retention summary already exist and were reused, not fabricated.

The policy's location paragraph currently says device-side nearby filtering. The rebuilt live app sends coordinates to FoodSave's nearby API, and merchant-confirmed store coordinates/order snapshots persist in SQL. This wording/flag mismatch needs verification against the accepted current policy and actual service behavior. No new policy, promise about logs/retention, or completion=true flag was fabricated. Current backend registration/privacy flags must be read in the authorized Azure environment; they were not changed here.

## External checks still required

1. Verify the actual existing Android applicationId and signing certificate from an authorized existing APK/build configuration if an Android release is intended; do not substitute a new ID/key. Determine how the shared gate should apply to a web-only release before changing it.
2. Verify effective public policy/settings and approve any needed location-data correction. No secret export should enter Git or deliverables.
3. Historical principal name `foodsave-web-tku` and MI object ID `f21960ec-e0d2-4264-9433-24da3db73fe4` are **unverified lookup hints only**. They are not the current SQL principal/SID or proof of effective rights. No grant template was filled from them and no grant was executed.
4. Real isolated SQL validation, exact runtime rights, production program/settings/database recovery plan and existing Azure deployment/transfer path remain external work.
5. The earlier backend candidate excludes its default demo-prizes seed JSON. If the existing formal demo feature is enabled, verify and privately back up its actual configured persistent pool before any replacement. This fix leaves the feature enabled/disabled exactly as before and does not remove its frontend API calls. Do not silently turn it off to hide that compatibility issue.

No Library/403 transfer retry, alternative upload route or deployment was attempted. Preparation and source can continue locally, but those external facts cannot be inferred from a passing bundle scan.

## Backup

Before any source overwrite: `/workspace/foodsave-rebuild/backups/live-bundle-fix-before.bundle`, SHA256 `a20f86a42216f4694a8b671c7dce265df5fa129a21345f5fca5dff4aa7b63fc5`. Bundle verify, independent clone/fsck and 276 tracked-file hashes matched. Existing changed files were separately copied and SHA256-verified before edits through `safe_edit.py`. These are source backups, not production website or SQL backups. Independent reviewer verified the backup and initial implementation; final review covers the completed test/build evidence before commit.
