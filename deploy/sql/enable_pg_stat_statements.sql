-- Activer le suivi des requetes lentes (Postgres prod / node6).
-- A lancer une fois en superuser, puis redemarrer Postgres si besoin.

-- postgresql.conf :
--   shared_preload_libraries = 'pg_stat_statements'
--   pg_stat_statements.max = 10000
--   pg_stat_statements.track = all

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Top requetes couteuses (a relancer apres charge reelle) :
-- SELECT substring(query, 1, 80) AS q,
--        calls, round(total_exec_time::numeric, 1) AS total_ms,
--        round(mean_exec_time::numeric, 2) AS mean_ms,
--        rows
-- FROM pg_stat_statements
-- ORDER BY total_exec_time DESC
-- LIMIT 20;
