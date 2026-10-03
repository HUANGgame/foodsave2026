-- PROPOSED ONLY. Requires owner approval for persistent role/permission changes.
-- Run on the new FoodSave database only, after migrations.
-- Create a dedicated contained user by an approved secure identity procedure,
-- then add that user to this role. No username/password is embedded here.
CREATE ROLE foodsave_viewer;
GRANT SELECT (id,role,active,created_at) ON OBJECT::dbo.users TO foodsave_viewer;
GRANT SELECT (id,owner_id,name,latitude,longitude) ON OBJECT::dbo.stores TO foodsave_viewer;
GRANT SELECT (id,store_id,name,available_quantity,revision) ON OBJECT::dbo.products TO foodsave_viewer;
GRANT SELECT (id,user_id,product_id,state,quantity,expires_at) ON OBJECT::dbo.reservations TO foodsave_viewer;
GRANT SELECT (id,user_id,prize_id,created_at) ON OBJECT::dbo.draws TO foodsave_viewer;
GRANT SELECT (id,name,kind,weight,remaining,enabled,expires_at) ON OBJECT::dbo.prizes TO foodsave_viewer;
GRANT SELECT (id,user_id,source_key,remaining,expires_at) ON OBJECT::dbo.spin_grants TO foodsave_viewer;
GRANT SELECT (id,actor_id,action,target_id,created_at) ON OBJECT::dbo.audit_logs TO foodsave_viewer;
-- Do not add this user to db_datareader/db_datawriter/db_owner or any broad role.
-- Verify the identity cannot SELECT password_hash/email or INSERT/UPDATE/DELETE.
