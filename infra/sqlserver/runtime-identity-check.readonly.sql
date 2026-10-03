-- Read-only; connect directly to foodsave. Replace approved name/Application ID.
IF DB_NAME()<>N'foodsave' THROW 51000, 'Wrong database', 1;
SELECT name,type_desc,authentication_type_desc,DATALENGTH(sid) AS sid_bytes,
 CONVERT(varchar(130),sid,1) AS sid_hex,
 CASE WHEN DATALENGTH(sid)=16 THEN CONVERT(uniqueidentifier,sid) END AS sid_guid
FROM sys.database_principals WHERE name=N'REPLACE_WITH_APPROVED_RUNTIME';
SELECT CONVERT(varchar(34),CONVERT(binary(16),CONVERT(uniqueidentifier,'REPLACE_WITH_APPROVED_APP_ID')),1)
 AS expected_application_sid_hex;
-- No row after rollback is expected: it means CREATE USER was not committed.
-- Match a service principal against Application ID, not the Object ID used to resolve it.
