# Preserve the verified backend fallback

Branch: `foodsave-fallback-compat-20261006`; parent: `360fe02bc934b862832b7f8634555d20e8b68a93`.

The release coordinator reported an official Kudu private backup of the production output.tar.zst: 41,351,729 bytes; SHA256 `18814098df968d574c75ebdb3aac8c895e6027b3e4f7148fd57f51b73f8e356c`; zstd/tar integrity and 3,762 entries checked. That full private archive was not downloaded, accessed or republished in this executor. It is not a SQL/config backup.

The extracted public, fictional demonstration fallback was separately verified by the coordinator as 805 UTF-8 bytes, no BOM, one trailing LF and no CRLF; SHA256 `7d6e4ec10d7bf5ed99d3868d9077e3831ba16b407a7ad100fa092f45285f5013`. The existing tracked `backend/foodsave/static/demo-prizes.json` matches those bytes/hash exactly. No prize or runtime source modification is needed.

The previous candidate packaging excluded this file. With the reported empty production `/home/data/foodsave/` directory and enabled demo-prizes flag, that packaging would break the original fallback behavior. The new **backend-only** builder `release/20261006/build_backend_candidate.py` includes the hash-locked original fallback. It requires a full Git commit, preserves the prior runtime allowlist, checks fallback length/hash, emits a separate candidate/manifest and validates all ZIP entries. Historical fixed-source builders/candidates remain preserved; use the new builder for this backend candidate.

`demo_prizes.read()` remains unchanged: prefer the existing configured persistent file; otherwise read the bundled fallback. Reading/drawing does not create a store; only the existing authorized edit path writes a store. No production store, flags, prizes, mail behavior, SQL, rights or frontend assets changed. In particular, the backend fallback does not enter the live frontend artifact. The previous continuous-mail repair is inherited unchanged.

A delivery-level test extracts the actual candidate ZIP to temporary storage, verifies exclusions, exercises missing-file fallback and drawing without creating a store, and checks existing persistent data takes precedence without modifying either file. Complete backend test result is recorded in `/workspace/foodsave-rebuild/fallback-compat-backend.log`. Final candidate integrity and source pin receive independent QA.

Before the batch, `/workspace/foodsave-rebuild/backups/fallback-compat-20261006-before.bundle` was verified/restored/fsck checked with 284 matching tracked-file hashes; SHA256 `f339ed9b4a749c1e17049bacdb1a4425d90dbc80970318e85e3ea24a59fef55f`. This batch adds files only, without overwriting runtime or historical build scripts.

Still not release approval: policy amendment/synchronization and frontend privacy completion, verified application ID/signing where applicable, runtime identity/SID/rights, isolated real SQL validation, production SQL/config backup and deployment/recovery route remain unresolved. Existing SQL validation tooling is pinned to 1a5a6d6 and does not establish validation of this candidate. No real mail or deployment performed.
