-- daily-work: drop the old groups, public (real use, with test rows mixed in) and sim, now that
-- 20261022000000_live_and_test.sql has copied their rows into test. Run only once no released
-- plugin version writes to public: a version that still does would lose its rows silently.
-- public itself stays, empty, as Postgres needs it. Afterwards remove sim from the API's
-- exposed schemas: Project Settings, Data API, Exposed schemas. Safe to run more than once.

select cron.unschedule(jobname) from cron.job
  where jobname in ('daily-work-content-30-days', 'daily-work-session-judging-30-days', 'daily-work-sim-30-days');

drop schema if exists sim cascade;

drop view if exists public.dashboard_kpis, public.dashboard_funnel, public.dashboard_daily,
  public.dashboard_tasks, public.dashboard_versions, public.dashboard_cycle, public.dashboard_hourly,
  public.dashboard_traces, public.dashboard_judge, public.dashboard_session_analysis;

drop table if exists public.events, public.content, public.feedback, public.session_scores,
  public.session_analysis, public.eval_runs, public.eval_steps;

notify pgrst, 'reload schema';
