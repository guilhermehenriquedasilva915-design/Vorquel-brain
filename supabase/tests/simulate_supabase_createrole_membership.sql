\set ON_ERROR_STOP on

create role supabase_createrole_simulator superuser nologin;

set role supabase_createrole_simulator;

grant n8n_brain_writer to postgres
  with admin true, inherit false, set false;

reset role;
