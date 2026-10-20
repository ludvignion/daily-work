-- daily-work: real sessions judged afterwards (evals/sessions.py). One score row per skill run
-- in public.content, and one analysis row per batch: topics and confusion over the runs judged.
-- Written and read with the service (secret) key only, by whoever runs the batch; the public
-- (anon / publishable) key can do nothing here.
-- The judge's words can echo what people wrote, so they follow content's 30 days: reasons are
-- cleared and analyses deleted after 30 days. The scores stay. Safe to run more than once.

create table if not exists public.session_scores (
  id             bigint generated always as identity primary key,
  judged_at      timestamptz not null default now(),
  content_row    bigint      not null unique,   -- public.content.id of the run judged
  content_id     uuid        not null,
  skill          text        not null check (skill in ('brief', 'grill', 'record')),
  run_ts         timestamptz not null,          -- the run's hour, as in public.content
  plugin_version text        not null check (plugin_version ~ '^\d+\.\d+\.\d+$'),
  judge_model    text        not null check (char_length(judge_model) <= 64),
  -- {criterion: 1..5}
  scores         jsonb       not null check (jsonb_typeof(scores) = 'object' and pg_column_size(scores) <= 4000),
  -- {criterion: one sentence}; null after 30 days
  reasons        jsonb       check (reasons is null or (jsonb_typeof(reasons) = 'object' and pg_column_size(reasons) <= 20000))
);

create index if not exists session_scores_run_ts on public.session_scores (run_ts);

create table if not exists public.session_analysis (
  id             bigint generated always as identity primary key,
  made_at        timestamptz not null default now(),
  period_start   timestamptz not null,
  period_end     timestamptz not null,
  runs           integer     not null check (runs >= 0),
  judge_model    text        not null check (char_length(judge_model) <= 64),
  -- [{name, runs, bullets: [3 sentences]}]
  topics         jsonb       not null check (jsonb_typeof(topics) = 'array' and pg_column_size(topics) <= 50000),
  confusion      jsonb       not null check (jsonb_typeof(confusion) = 'array' and pg_column_size(confusion) <= 50000)
);

alter table public.session_scores   enable row level security;
alter table public.session_analysis enable row level security;

revoke all on public.session_scores   from anon, authenticated;
revoke all on public.session_analysis from anon, authenticated;
grant select, insert, update, delete on public.session_scores   to service_role;
grant select, insert, update, delete on public.session_analysis to service_role;

-- Clear the judge's words after 30 days, every night at 03:27 UTC, ten minutes after content's own.
create extension if not exists pg_cron;
select cron.unschedule('daily-work-session-judging-30-days')
  where exists (select 1 from cron.job where jobname = 'daily-work-session-judging-30-days');
select cron.schedule(
  'daily-work-session-judging-30-days',
  '27 3 * * *',
  $$update public.session_scores set reasons = null where reasons is not null and judged_at < now() - interval '30 days';
    delete from public.session_analysis where made_at < now() - interval '30 days'$$
);

notify pgrst, 'reload schema';
