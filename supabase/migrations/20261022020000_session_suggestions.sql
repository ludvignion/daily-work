-- daily-work: suggested changes to the plugin, a third part of each session analysis next to
-- topics and confusion (evals/sessions.py). Same shape: [{name, runs, bullets: [3 sentences]}],
-- the name being the change and the bullets what to change, where, and which confusion or low
-- score it answers. Analyses made before this have none. The dashboard view gets the part too.
-- Safe to run more than once.

alter table live.session_analysis add column if not exists suggestions jsonb not null default '[]'::jsonb
  check (jsonb_typeof(suggestions) = 'array' and pg_column_size(suggestions) <= 50000);
alter table test.session_analysis add column if not exists suggestions jsonb not null default '[]'::jsonb
  check (jsonb_typeof(suggestions) = 'array' and pg_column_size(suggestions) <= 50000);

create or replace view live.dashboard_session_analysis with (security_invoker = true) as
with a as (select * from live.session_analysis order by made_at desc limit 1) select p.part, g->>'name' as name, jsonb_array_length(g->'runs') as run_count, a.runs as runs_total, g->'bullets' as bullets, g->'runs' as runs from a, lateral (values ('topics', a.topics), ('confusion', a.confusion), ('suggestions', a.suggestions)) as p(part, groups), jsonb_array_elements(p.groups) as g;

create or replace view test.dashboard_session_analysis with (security_invoker = true) as
with a as (select * from test.session_analysis order by made_at desc limit 1) select p.part, g->>'name' as name, jsonb_array_length(g->'runs') as run_count, a.runs as runs_total, g->'bullets' as bullets, g->'runs' as runs from a, lateral (values ('topics', a.topics), ('confusion', a.confusion), ('suggestions', a.suggestions)) as p(part, groups), jsonb_array_elements(p.groups) as g;

revoke all on live.dashboard_session_analysis from anon, authenticated;
grant select on live.dashboard_session_analysis to service_role;
revoke all on test.dashboard_session_analysis from anon, authenticated;
grant select on test.dashboard_session_analysis to service_role;

notify pgrst, 'reload schema';
