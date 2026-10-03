-- Azure SQL / SQL Server 2022. Run only on a NEW dedicated FoodSave database.
CREATE TABLE dbo.users (
 id varchar(36) NOT NULL PRIMARY KEY,
 email nvarchar(254) NOT NULL UNIQUE,
 password_hash varchar(256) NOT NULL,
 role varchar(16) NOT NULL CHECK(role IN ('consumer','vendor','admin')),
 active bit NOT NULL DEFAULT 1,
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.sessions (
 token_hash char(64) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 expires_at datetime2 NOT NULL,
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX ix_sessions_user ON dbo.sessions(user_id);
CREATE TABLE dbo.rate_limits (
 bucket char(64) NOT NULL PRIMARY KEY,
 window_start datetime2 NOT NULL,
 attempts int NOT NULL CHECK(attempts >= 0)
);
CREATE TABLE dbo.stores (
 id varchar(36) NOT NULL PRIMARY KEY,
 owner_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 name nvarchar(100) NOT NULL,
 latitude decimal(9,6) NOT NULL CHECK(latitude BETWEEN -90 AND 90),
 longitude decimal(9,6) NOT NULL CHECK(longitude BETWEEN -180 AND 180)
);
CREATE TABLE dbo.products (
 id varchar(36) NOT NULL PRIMARY KEY,
 store_id varchar(36) NOT NULL REFERENCES dbo.stores(id),
 name nvarchar(160) NOT NULL,
 photo_url nvarchar(2048) NOT NULL,
 original_price_minor int NOT NULL CHECK(original_price_minor >= 0),
 sale_price_minor int NOT NULL CHECK(sale_price_minor >= 0),
 available_quantity int NOT NULL CHECK(available_quantity >= 0),
 pickup_deadline datetime2 NOT NULL,
 active bit NOT NULL DEFAULT 1,
 revision int NOT NULL DEFAULT 1,
 CHECK(sale_price_minor <= original_price_minor)
);
CREATE INDEX ix_products_store ON dbo.products(store_id);
CREATE TABLE dbo.reservations (
 id varchar(36) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 product_id varchar(36) NOT NULL REFERENCES dbo.products(id),
 state varchar(12) NOT NULL CHECK(state IN ('waiting','completed','cancelled','expired')),
 quantity int NOT NULL CHECK(quantity BETWEEN 1 AND 10),
 snapshot nvarchar(max) NOT NULL CHECK(ISJSON(snapshot)=1),
 pickup_code_hash char(64) NOT NULL,
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 expires_at datetime2 NOT NULL,
 completed_at datetime2 NULL
);
CREATE INDEX ix_reservations_user ON dbo.reservations(user_id, created_at);
CREATE INDEX ix_reservations_expiry ON dbo.reservations(state, expires_at);
CREATE TABLE dbo.request_results (
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 operation varchar(40) NOT NULL,
 request_key varchar(80) NOT NULL,
 fingerprint char(64) NOT NULL,
 response nvarchar(max) NOT NULL CHECK(ISJSON(response)=1),
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 PRIMARY KEY(user_id,operation,request_key)
);
CREATE TABLE dbo.exp_rules (
 event varchar(24) NOT NULL PRIMARY KEY CHECK(event IN ('pickup','review','favorite')),
 amount int NOT NULL CHECK(amount BETWEEN 0 AND 100000),
 enabled bit NOT NULL DEFAULT 0
);
-- Business values are NOT approved. No EXP is issued until admin enables a rule.
INSERT INTO dbo.exp_rules(event,amount,enabled) VALUES ('pickup',0,0),('review',0,0),('favorite',0,0);
CREATE TABLE dbo.exp_events (
 id varchar(36) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 event_key varchar(100) NOT NULL UNIQUE,
 amount int NOT NULL CHECK(amount >= 0),
 occurred_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.favorites (
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 store_id varchar(36) NOT NULL REFERENCES dbo.stores(id),
 PRIMARY KEY(user_id,store_id)
);
CREATE TABLE dbo.reviews (
 reservation_id varchar(36) NOT NULL PRIMARY KEY REFERENCES dbo.reservations(id),
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 rating int NOT NULL CHECK(rating BETWEEN 1 AND 5),
 body nvarchar(1000) NOT NULL,
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.spin_grants (
 id varchar(36) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 source_key varchar(120) NOT NULL UNIQUE,
 remaining int NOT NULL CHECK(remaining >= 0),
 expires_at datetime2 NOT NULL,
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.prizes (
 id varchar(36) NOT NULL PRIMARY KEY,
 name nvarchar(120) NOT NULL,
 kind varchar(16) NOT NULL CHECK(kind IN ('coupon','physical')),
 weight int NOT NULL CHECK(weight BETWEEN 1 AND 1000000),
 remaining int NOT NULL CHECK(remaining >= 0),
 enabled bit NOT NULL DEFAULT 0,
 expires_at datetime2 NOT NULL,
 terms nvarchar(2000) NOT NULL,
 discount_percent int NULL,
 CHECK((kind='coupon' AND discount_percent IS NOT NULL AND discount_percent=20) OR (kind='physical' AND discount_percent IS NULL))
);
CREATE TABLE dbo.draws (
 id varchar(36) NOT NULL PRIMARY KEY,
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 grant_id varchar(36) NOT NULL REFERENCES dbo.spin_grants(id),
 prize_id varchar(36) NOT NULL REFERENCES dbo.prizes(id),
 prize_snapshot nvarchar(max) NOT NULL CHECK(ISJSON(prize_snapshot)=1),
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.coupons (
 id varchar(36) NOT NULL PRIMARY KEY,
 draw_id varchar(36) NOT NULL UNIQUE REFERENCES dbo.draws(id),
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 code varchar(64) NOT NULL UNIQUE,
 state varchar(12) NOT NULL CHECK(state IN ('available','redeemed')),
 expires_at datetime2 NOT NULL
);
CREATE TABLE dbo.audit_logs (
 id varchar(36) NOT NULL PRIMARY KEY,
 actor_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 action varchar(64) NOT NULL,
 target_id varchar(120) NOT NULL,
 created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
