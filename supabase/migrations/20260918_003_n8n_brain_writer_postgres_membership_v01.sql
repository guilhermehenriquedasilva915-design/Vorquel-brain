begin;

grant n8n_brain_writer to postgres
  with admin true, inherit false, set true;

commit;
