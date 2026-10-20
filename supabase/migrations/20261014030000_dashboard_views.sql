-- daily-work: the dashboard's queries as views, so dashboard/build.py can read the Usage and
-- Observability tabs over the REST API with the service (secret) key, for the standalone page.
-- Each view is the query in dashboard/queries/<name>.sql, unchanged (tests/test_dashboard.py
-- checks they match). security_invoker: a view reads with the rights of whoever asks, so the
-- tables' own grants and row level security hold. Only service_role may read them; the public
-- (anon / publishable) key gets nothing. Safe to run more than once.


create or replace view public.dashboard_kpis with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111') select count(distinct install_id) as installs, count(distinct task_id) filter (where event = 'brief') as tasks_started, count(distinct task_id) filter (where event = 'record') as tasks_recorded, round(count(distinct task_id) filter (where event = 'record')::numeric / nullif(count(distinct task_id) filter (where event = 'brief'), 0), 3) as record_rate, count(*) filter (where rating is not null) as ratings, round(avg(rating), 2) as avg_rating, (select plugin_version from e order by string_to_array(plugin_version, '.')::int[] desc limit 1) as latest_version, to_char(max(ts) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as last_event from e;

create or replace view public.dashboard_funnel with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111') select s.step, coalesce(c.tasks, 0) as tasks from (values (1, 'brief'), (2, 'grill'), (3, 'record')) as s(ord, step) left join (select event, count(distinct task_id) as tasks from e group by event) c on c.event = s.step order by s.ord;

create or replace view public.dashboard_daily with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111') select to_char((ts at time zone 'Europe/Stockholm')::date, 'YYYY-MM-DD') as day, count(*) filter (where event = 'brief') as brief, count(*) filter (where event = 'grill') as grill, count(*) filter (where event = 'record') as record from e group by 1 order by 1;

create or replace view public.dashboard_tasks with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111') select left(task_id::text, 8) as task, to_char(min(ts) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as started, (array_agg(plugin_version order by ts desc))[1] as version, bool_or(event = 'grill') as grilled, bool_or(event = 'record') as recorded, round(extract(epoch from max(ts) - min(ts)) / 60)::int as minutes, max(rating) as rating from e where task_id is not null group by task_id order by min(ts) desc;

create or replace view public.dashboard_versions with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, install_id, (array_agg(plugin_version order by ts) filter (where event = 'brief'))[1] as version, min(ts) filter (where event = 'brief') as briefed, min(ts) filter (where event = 'record') as recorded, max(rating) as rating, bool_or(event = 'grill') as grilled, bool_or(event = 'grill' and outcome = 'aborted') as grill_aborted from e where task_id is not null group by task_id, install_id), fv as (select plugin_version, to_char(min(ts) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as first_seen, count(distinct install_id) as installs from e group by plugin_version) select fv.plugin_version as version, fv.first_seen, fv.installs, count(t.task_id) as started, count(t.recorded) as recorded, round(count(t.recorded)::numeric / nullif(count(t.task_id), 0), 3) as completion, round(count(*) filter (where t.grill_aborted)::numeric / nullif(count(*) filter (where t.grilled), 0), 3) as grill_aborted, round((percentile_cont(0.5) within group (order by extract(epoch from t.recorded - t.briefed) / 60))::numeric, 1) as cycle_p50_min, round(avg(t.rating), 2) as rating from fv left join t on t.version = fv.plugin_version group by fv.plugin_version, fv.first_seen, fv.installs order by string_to_array(fv.plugin_version, '.')::int[];

create or replace view public.dashboard_cycle with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, min(ts) filter (where event = 'brief') as b, min(ts) filter (where event = 'record') as r from e where task_id is not null group by task_id) select count(*) filter (where b is not null) as started, count(*) filter (where b is not null and r is not null) as closed, round((percentile_cont(0.5) within group (order by extract(epoch from r - b) / 60))::numeric, 1) as p50_min, round((percentile_cont(0.75) within group (order by extract(epoch from r - b) / 60))::numeric, 1) as p75_min from t;

create or replace view public.dashboard_hourly with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, min(ts) filter (where event = 'brief') as b, bool_or(event = 'record') as rec from e where task_id is not null group by task_id) select to_char(date_trunc('hour', b at time zone 'UTC'), 'YYYY-MM-DD"T"HH24:00:00"Z"') as hour, count(*) as started, count(*) filter (where rec) as recorded, round(count(*) filter (where rec)::numeric / count(*), 3) as completion from t where b is not null and b >= now() - interval '7 days' group by 1 order by 1;

create or replace view public.dashboard_traces with (security_invoker = true) as
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111'), t as (select task_id, (array_agg(plugin_version order by ts))[1] as version, min(ts) filter (where event = 'brief') as b, min(ts) filter (where event = 'grill') as g, min(ts) filter (where event = 'record') as r, max(ts) as last_at, max(rating) as rating, (array_agg(outcome order by ts) filter (where event = 'grill'))[1] as grill_outcome from e where task_id is not null group by task_id) select left(task_id::text, 8) as task, version, to_char(b at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as briefed_at, to_char(g at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as grilled_at, to_char(r at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as recorded_at, round((extract(epoch from g - b) / 60)::numeric, 1) as brief_to_grill_min, round((extract(epoch from r - coalesce(g, b)) / 60)::numeric, 1) as grill_to_record_min, round((extract(epoch from coalesce(r, last_at) - b) / 60)::numeric, 1) as total_min, rating, grill_outcome, case when r is not null then 'Done' when grill_outcome = 'aborted' then 'Aborted' else 'Open' end as status from t order by b desc nulls last limit 50;

create or replace view public.dashboard_judge with (security_invoker = true) as
with s as (select content_row, content_id, skill, run_ts, scores, reasons, (select round(avg(value::numeric), 1) from jsonb_each_text(scores)) as overall from public.session_scores) select content_row::text as run, left(content_id::text, 8) as task, skill, to_char(run_ts at time zone 'UTC', 'YYYY-MM-DD"T"HH24:00:00"Z"') as run_hour, overall, (select string_agg(key || ' ' || value || '/5', ' · ' order by key) from jsonb_each_text(scores)) as scores, case when overall >= 4 then 'Pass' when overall >= 3 then 'Watch' else 'Fail' end as verdict, coalesce((select string_agg(value, ' ' order by key) from jsonb_each_text(reasons)), 'Reasons cleared after 30 days.') as reasoning from s order by run_ts desc, content_row desc limit 100;

create or replace view public.dashboard_session_analysis with (security_invoker = true) as
with a as (select * from public.session_analysis order by made_at desc limit 1) select p.part, g->>'name' as name, jsonb_array_length(g->'runs') as run_count, a.runs as runs_total, g->'bullets' as bullets, g->'runs' as runs from a, lateral (values ('topics', a.topics), ('confusion', a.confusion)) as p(part, groups), jsonb_array_elements(p.groups) as g;

revoke all on public.dashboard_kpis from anon, authenticated;
grant select on public.dashboard_kpis to service_role;
revoke all on public.dashboard_funnel from anon, authenticated;
grant select on public.dashboard_funnel to service_role;
revoke all on public.dashboard_daily from anon, authenticated;
grant select on public.dashboard_daily to service_role;
revoke all on public.dashboard_tasks from anon, authenticated;
grant select on public.dashboard_tasks to service_role;
revoke all on public.dashboard_versions from anon, authenticated;
grant select on public.dashboard_versions to service_role;
revoke all on public.dashboard_cycle from anon, authenticated;
grant select on public.dashboard_cycle to service_role;
revoke all on public.dashboard_hourly from anon, authenticated;
grant select on public.dashboard_hourly to service_role;
revoke all on public.dashboard_traces from anon, authenticated;
grant select on public.dashboard_traces to service_role;
revoke all on public.dashboard_judge from anon, authenticated;
grant select on public.dashboard_judge to service_role;
revoke all on public.dashboard_session_analysis from anon, authenticated;
grant select on public.dashboard_session_analysis to service_role;

notify pgrst, 'reload schema';
