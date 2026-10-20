-- daily-work: the test group. Schema sim holds the same tables as public, for test sessions:
-- the offline eval's simulated sessions and your own tries (DAILY_WORK_TARGET=test), so public
-- holds real use only. The plugin picks the schema with the REST API's Content-Profile header.
-- Same rights as in public: the public (anon / publishable) key can insert into events, content
-- and feedback and do nothing else; only the service (secret) key reads; session_scores and
-- session_analysis are service key only. Same 30-day cleanup. The dashboard views are here too.
-- The eval's own tables, eval_runs and eval_steps, stay in public: they hold nothing real.
-- Needs the schema sim exposed to the API: Project Settings, Data API, Exposed schemas.
-- Run after every migration before it. Safe to run more than once.

create schema if not exists sim;
grant usage on schema sim to anon, service_role;

-- Same columns, defaults, checks and indexes as public; rows of their own.
create table if not exists sim.events           (like public.events           including all);
create table if not exists sim.content          (like public.content          including all);
create table if not exists sim.feedback         (like public.feedback         including all);
create table if not exists sim.session_scores   (like public.session_scores   including all);
create table if not exists sim.session_analysis (like public.session_analysis including all);

alter table sim.events           enable row level security;
alter table sim.content          enable row level security;
alter table sim.feedback         enable row level security;
alter table sim.session_scores   enable row level security;
alter table sim.session_analysis enable row level security;

revoke all on sim.events, sim.content, sim.feedback, sim.session_scores, sim.session_analysis
  from anon, authenticated;
grant select, insert, update, delete
  on sim.events, sim.content, sim.feedback, sim.session_scores, sim.session_analysis to service_role;

grant insert (event, ts, plugin_version, install_id, task_id, outcome, rating) on sim.events to anon;
grant insert (kind, ts, plugin_version, content_id, skill, turns, files, outcome, rating, grill_completed)
  on sim.content to anon;
grant insert (ts, plugin_version, install_id, task_id, comment, content) on sim.feedback to anon;

drop policy if exists "anon can insert events"   on sim.events;
drop policy if exists "anon can insert content"  on sim.content;
drop policy if exists "anon can insert feedback" on sim.feedback;
create policy "anon can insert events"   on sim.events   for insert to anon with check (true);
create policy "anon can insert content"  on sim.content  for insert to anon with check (true);
create policy "anon can insert feedback" on sim.feedback for insert to anon with check (true);

-- The 30-day cleanup, as for public, at 03:37 UTC.
create extension if not exists pg_cron;
select cron.unschedule('daily-work-sim-30-days')
  where exists (select 1 from cron.job where jobname = 'daily-work-sim-30-days');
select cron.schedule(
  'daily-work-sim-30-days',
  '37 3 * * *',
  $$delete from sim.content where received_at < now() - interval '30 days';
    update sim.session_scores set reasons = null where reasons is not null and judged_at < now() - interval '30 days';
    delete from sim.session_analysis where made_at < now() - interval '30 days'$$
);

-- The dashboard views over sim: each the query in dashboard/queries/<name>.sql with public. read
-- as sim. (tests/test_dashboard.py checks they match).

create or replace view sim.dashboard_kpis with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111') select count(distinct install_id) as installs, count(distinct task_id) filter (where event = 'brief') as tasks_started, count(distinct task_id) filter (where event = 'record') as tasks_recorded, round(count(distinct task_id) filter (where event = 'record')::numeric / nullif(count(distinct task_id) filter (where event = 'brief'), 0), 3) as record_rate, count(*) filter (where rating is not null) as ratings, round(avg(rating), 2) as avg_rating, (select plugin_version from e order by string_to_array(plugin_version, '.')::int[] desc limit 1) as latest_version, to_char(max(ts) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as last_event from e;

create or replace view sim.dashboard_funnel with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111') select s.step, coalesce(c.tasks, 0) as tasks from (values (1, 'brief'), (2, 'grill'), (3, 'record')) as s(ord, step) left join (select event, count(distinct task_id) as tasks from e group by event) c on c.event = s.step order by s.ord;

create or replace view sim.dashboard_daily with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111') select to_char((ts at time zone 'Europe/Stockholm')::date, 'YYYY-MM-DD') as day, count(*) filter (where event = 'brief') as brief, count(*) filter (where event = 'grill') as grill, count(*) filter (where event = 'record') as record from e group by 1 order by 1;

create or replace view sim.dashboard_tasks with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111') select left(task_id::text, 8) as task, to_char(min(ts) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as started, (array_agg(plugin_version order by ts desc))[1] as version, bool_or(event = 'grill') as grilled, bool_or(event = 'record') as recorded, round(extract(epoch from max(ts) - min(ts)) / 60)::int as minutes, max(rating) as rating from e where task_id is not null group by task_id order by min(ts) desc;

create or replace view sim.dashboard_versions with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, install_id, (array_agg(plugin_version order by ts) filter (where event = 'brief'))[1] as version, min(ts) filter (where event = 'brief') as briefed, min(ts) filter (where event = 'record') as recorded, max(rating) as rating, bool_or(event = 'grill') as grilled, bool_or(event = 'grill' and outcome = 'aborted') as grill_aborted from e where task_id is not null group by task_id, install_id), fv as (select plugin_version, to_char(min(ts) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as first_seen, count(distinct install_id) as installs from e group by plugin_version) select fv.plugin_version as version, fv.first_seen, fv.installs, count(t.task_id) as started, count(t.recorded) as recorded, round(count(t.recorded)::numeric / nullif(count(t.task_id), 0), 3) as completion, round(count(*) filter (where t.grill_aborted)::numeric / nullif(count(*) filter (where t.grilled), 0), 3) as grill_aborted, round((percentile_cont(0.5) within group (order by extract(epoch from t.recorded - t.briefed) / 60))::numeric, 1) as cycle_p50_min, round(avg(t.rating), 2) as rating from fv left join t on t.version = fv.plugin_version group by fv.plugin_version, fv.first_seen, fv.installs order by string_to_array(fv.plugin_version, '.')::int[];

create or replace view sim.dashboard_cycle with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, min(ts) filter (where event = 'brief') as b, min(ts) filter (where event = 'record') as r from e where task_id is not null group by task_id) select count(*) filter (where b is not null) as started, count(*) filter (where b is not null and r is not null) as closed, round((percentile_cont(0.5) within group (order by extract(epoch from r - b) / 60))::numeric, 1) as p50_min, round((percentile_cont(0.75) within group (order by extract(epoch from r - b) / 60))::numeric, 1) as p75_min from t;

create or replace view sim.dashboard_hourly with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, min(ts) filter (where event = 'brief') as b, bool_or(event = 'record') as rec from e where task_id is not null group by task_id) select to_char(date_trunc('hour', b at time zone 'UTC'), 'YYYY-MM-DD"T"HH24:00:00"Z"') as hour, count(*) as started, count(*) filter (where rec) as recorded, round(count(*) filter (where rec)::numeric / count(*), 3) as completion from t where b is not null and b >= now() - interval '7 days' group by 1 order by 1;

create or replace view sim.dashboard_traces with (security_invoker = true) as
with e as (select * from sim.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, (array_agg(plugin_version order by ts))[1] as version, min(ts) filter (where event = 'brief') as b, min(ts) filter (where event = 'grill') as g, min(ts) filter (where event = 'record') as r, max(ts) as last_at, max(rating) as rating, (array_agg(outcome order by ts) filter (where event = 'grill'))[1] as grill_outcome from e where task_id is not null group by task_id) select left(task_id::text, 8) as task, version, to_char(b at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as briefed_at, to_char(g at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as grilled_at, to_char(r at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as recorded_at, round((extract(epoch from g - b) / 60)::numeric, 1) as brief_to_grill_min, round((extract(epoch from r - coalesce(g, b)) / 60)::numeric, 1) as grill_to_record_min, round((extract(epoch from coalesce(r, last_at) - b) / 60)::numeric, 1) as total_min, rating, grill_outcome, case when r is not null then 'Done' when grill_outcome = 'aborted' then 'Aborted' else 'Open' end as status from t order by b desc nulls last limit 50;

create or replace view sim.dashboard_judge with (security_invoker = true) as
with s as (select content_row, content_id, skill, run_ts, scores, reasons, (select round(avg(value::numeric), 1) from jsonb_each_text(scores)) as overall from sim.session_scores) select content_row::text as run, left(content_id::text, 8) as task, skill, to_char(run_ts at time zone 'UTC', 'YYYY-MM-DD"T"HH24:00:00"Z"') as run_hour, overall, (select string_agg(key || ' ' || value || '/5', ' · ' order by key) from jsonb_each_text(scores)) as scores, case when overall >= 4 then 'Pass' when overall >= 3 then 'Watch' else 'Fail' end as verdict, coalesce((select string_agg(value, ' ' order by key) from jsonb_each_text(reasons)), 'Reasons cleared after 30 days.') as reasoning from s order by run_ts desc, content_row desc limit 100;

create or replace view sim.dashboard_session_analysis with (security_invoker = true) as
with a as (select * from sim.session_analysis order by made_at desc limit 1) select p.part, g->>'name' as name, jsonb_array_length(g->'runs') as run_count, a.runs as runs_total, g->'bullets' as bullets, g->'runs' as runs from a, lateral (values ('topics', a.topics), ('confusion', a.confusion)) as p(part, groups), jsonb_array_elements(p.groups) as g;

revoke all on sim.dashboard_kpis from anon, authenticated;
grant select on sim.dashboard_kpis to service_role;
revoke all on sim.dashboard_funnel from anon, authenticated;
grant select on sim.dashboard_funnel to service_role;
revoke all on sim.dashboard_daily from anon, authenticated;
grant select on sim.dashboard_daily to service_role;
revoke all on sim.dashboard_tasks from anon, authenticated;
grant select on sim.dashboard_tasks to service_role;
revoke all on sim.dashboard_versions from anon, authenticated;
grant select on sim.dashboard_versions to service_role;
revoke all on sim.dashboard_cycle from anon, authenticated;
grant select on sim.dashboard_cycle to service_role;
revoke all on sim.dashboard_hourly from anon, authenticated;
grant select on sim.dashboard_hourly to service_role;
revoke all on sim.dashboard_traces from anon, authenticated;
grant select on sim.dashboard_traces to service_role;
revoke all on sim.dashboard_judge from anon, authenticated;
grant select on sim.dashboard_judge to service_role;
revoke all on sim.dashboard_session_analysis from anon, authenticated;
grant select on sim.dashboard_session_analysis to service_role;

notify pgrst, 'reload schema';
