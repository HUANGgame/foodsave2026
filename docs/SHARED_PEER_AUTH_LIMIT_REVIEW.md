# Approved shared-peer auth admission update

The user approved changing the shared socket-peer guard from10 operations/15min to20/min for password-processing entry points, accepting low-volume availability limits. Login, verify/reset finish, and public deletion credentials now use20/60; sender IP guard remains10/900. Existing email/user limits and global password20 operations/min across all seven entries remain unchanged. One operation can perform more than one hash. Mail5/min10/hour30/day1000/month remains unchanged.

`--no-proxy-headers` remains. The peer is an aggregate guard, not a proven end-user IP; no XFF trust, new Azure resource, DB grant, schema, cleanup or counter reset. Attackers can still exhaust the shared global quota and delay legitimate users. This is a consciously approved low-volume admission model, not per-client isolation or full DoS protection.

Backend239 tests passed: distinct emails behind one TestClient peer can reach20, then429; rotating fake XFF does not split peer identity; same-email10/15min still rejects11th; exact finish/mail/deletion windows checked; prior seven-entry exhausted-global tests remain. No true Azure/load/concurrency proof is implied.

Android test build is versionCode6/versionName0.4.0-auth-test with existing package ID. No closed-pilot code is included. Real server auth remains controlled by existing flags, mail deadline and privacy checks; backend deployment and opening registration are separate Azure-worker steps. User must privately perform email verification/password choice/login/reset in the delivered APK. Existing SQL rollback and confirmed notice delivery do not prove that complete workflow.
