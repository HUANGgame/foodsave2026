CREATE TABLE dbo.ranking_rules (
 start_rank int NOT NULL PRIMARY KEY CHECK(start_rank>0),
 end_rank int NOT NULL CHECK(end_rank>=start_rank),
 spins int NOT NULL CHECK(spins BETWEEN 1 AND 100)
);
INSERT INTO dbo.ranking_rules(start_rank,end_rank,spins) VALUES (1,1,3),(2,10,2),(11,50,1);
CREATE TABLE dbo.weekly_settlements (
 week_key char(10) NOT NULL PRIMARY KEY,
 starts_at datetime2 NOT NULL,
 ends_at datetime2 NOT NULL,
 completed_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.weekly_rankings (
 week_key char(10) NOT NULL REFERENCES dbo.weekly_settlements(week_key),
 user_id varchar(36) NOT NULL REFERENCES dbo.users(id),
 rank int NOT NULL CHECK(rank>0),
 exp bigint NOT NULL CHECK(exp>0),
 spins int NOT NULL CHECK(spins>=0),
 PRIMARY KEY(week_key,user_id),
 UNIQUE(week_key,rank)
);
