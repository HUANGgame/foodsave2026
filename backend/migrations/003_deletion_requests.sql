CREATE TABLE dbo.deletion_requests (
 id varchar(36) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL UNIQUE REFERENCES dbo.users(id),
 state varchar(16) NOT NULL DEFAULT 'requested' CHECK(state IN ('requested','completed')),
 requested_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 completed_at datetime2 NULL
);
-- Request immediately disables the account/revokes sessions. Final erasure and
-- legally required retention must follow the operator-approved retention policy.
