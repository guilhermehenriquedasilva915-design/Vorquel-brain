begin;

grant n8n_brain_writer to postgres
  with inherit false, set true;

commit;
