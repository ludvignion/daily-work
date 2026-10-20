-- daily-work offline eval: one row per run, scenario, run number and step, with what went into
-- the step, what came out, the conversation, and the scores with the judge's reasons
-- (evals/README.md). Simulated data only: invented scenarios and a simulated user.
-- The public (anon / publishable) key can insert and do nothing else. Only the service key reads.
-- Safe to run more than once.

create table if not exists public.eval_steps (
  id             bigint generated always as identity primary key,
  received_at    timestamptz not null default now(),
  run_id         text        not null check (char_length(run_id) <= 64),
  run_date       date        not null,
  plugin_version text        not null check (plugin_version ~ '^\d+\.\d+\.\d+$'),
  grill          text        not null check (char_length(grill) <= 64),
  model          text        not null check (char_length(model) <= 64),
  scenario       text        not null check (char_length(scenario) <= 100),
  run            smallint    not null check (run between 1 and 50),
  step           text        not null check (step in ('brief', 'grill', 'work', 'record', 'end_to_end')),
  completed      boolean     not null,
  input          text        not null check (char_length(input) <= 100000),
  output         text        not null check (char_length(output) <= 100000),
  -- [{role: user | assistant, text}]; empty for end_to_end
  transcript     jsonb       not null check (jsonb_typeof(transcript) = 'array' and pg_column_size(transcript) <= 200000),
  -- {metric: number}, {check: bool}, {criterion: reason}
  metrics        jsonb       not null check (jsonb_typeof(metrics) = 'object' and pg_column_size(metrics) <= 20000),
  checks         jsonb       not null check (jsonb_typeof(checks) = 'object' and pg_column_size(checks) <= 20000),
  reasons        jsonb       not null check (jsonb_typeof(reasons) = 'object' and pg_column_size(reasons) <= 50000),
  unique (run_id, grill, scenario, run, step)
);

create index if not exists eval_steps_run_id on public.eval_steps (run_id);

alter table public.eval_steps enable row level security;

revoke all on public.eval_steps from anon, authenticated;

grant insert (run_id, run_date, plugin_version, grill, model, scenario, run, step, completed,
              input, output, transcript, metrics, checks, reasons)
  on public.eval_steps to anon;

drop policy if exists "anon can insert eval_steps" on public.eval_steps;
create policy "anon can insert eval_steps" on public.eval_steps for insert to anon with check (true);

notify pgrst, 'reload schema';
