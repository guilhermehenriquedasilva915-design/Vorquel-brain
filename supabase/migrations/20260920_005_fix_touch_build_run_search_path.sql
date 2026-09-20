-- 20260920_005: fix trigger-function search_path
--
-- n8n_brain.touch_build_run() is a trigger function, not SECURITY DEFINER, but
-- it should still use an explicit search_path so object resolution is stable
-- and the Supabase security advisor remains clean.

begin;

alter function n8n_brain.touch_build_run()
  set search_path = pg_catalog, n8n_brain;

commit;
