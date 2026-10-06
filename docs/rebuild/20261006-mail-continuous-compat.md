# Continuous mail authorization compatibility repair

Branch: `foodsave-mail-compat-20261006`; parent `ae4c6bb070a9bfd20dc09f3321cf4330e0c7d7e0`.

The release coordinator supplied non-secret Portal observations at 20:26 UTC: mail approved=true, authorization mode=continuous and legacy expiry=2026-10-04T17:51:58Z. The previous candidate ignored the mode and rejected that expired timestamp. This repair implements the explicitly authorized continuous semantics without changing production settings.

- Exact `FOODSAVE_MAIL_APPROVED=true` is mandatory for every mode and is checked on every existing authorization call.
- Exact mode `continuous` ignores the legacy expiry. It does not bypass recipient/purpose/code validation, provider configuration, TLS/managed identity, transport bounds, rate limits, global quotas or abuse controls.
- Missing mode defaults to `timed`, preserving the previous aware-timestamp rule `now < until <= now + 24h`. Explicit `timed` uses the same rule.
- Unknown, empty, case-altered or whitespace-altered modes fail closed.

Only `backend/foodsave/account_mail.py` runtime code changed. No real mail, network delivery probe, SQL, grants, deployment, privacy flag, package ID or signing changes. New authorization tests cover 38 combinations including expired legacy expiry, disapproval, unknown mode, absent default and exact time bounds. Full backend suite: **397 passed**, one existing Starlette/httpx deprecation warning. Evidence: `/workspace/foodsave-rebuild/mail-continuous-backend.log`.

Before overwrite, the source bundle `/workspace/foodsave-rebuild/backups/mail-continuous-20261006-before.bundle` was verified, restored and fsck checked; 281 tracked-file hashes matched. SHA256: `85e9b6ee3b8c9da12447bc158edcc18fe33deec597bac3c60def00eb4f861b19`. The changed runtime file also received a separate SHA-verified overwrite backup through safe_edit.py. Independent QA is required before commit.

The updated API candidate will be built from the final full commit and receive a separate manifest and ZIP; old candidates remain intact. Its allowlist remains the reviewed backend runtime plus requirements; excludes maintenance CLIs, migrations/tests, secrets and default demo-prizes JSON. Existing `/home/data/foodsave/demo-prizes.json` is neither included nor cleared. Actual existence, validity, permissions and a verified private backup remain release prerequisites. Missing persistent pool still cannot fall back to the excluded JSON. No deployment retention assurance is inferred from ZIP contents.

`docs/rebuild/20261006-policy-amendment-DRAFT.md` contains only proposed location-data additions and a note about the obsolete limited-mail-authorization wording. The actual old policy JSON stays unchanged, so policy synchronization/approval is still a release blocker. Backend privacy-complete=true observed in Portal is not proof that the new frontend's build-time flag or expanded data-flow policy is approved.

The repository Android Gradle namespace/default applicationId is `tw.foodsave.demo`; property `foodsaveApplicationId` may override it. This is only a repository candidate/default, explicitly rejected by the existing release gate, not a verified deployed APK ID/signing identity. No fabricated replacement is supplied.

Existing release/20261006 SQL validation tooling remains pinned to 1a5a6d6. Its old source manifest must not be presented as validation of this new candidate; no actual SQL integration validation has been performed. Frontend candidate remains separately pinned to ae4c6bb and was not rebuilt for a backend-only runtime change.
