-- daily: Skill runs per day
-- Brief, grill and record events per day in Stockholm time. Reads public.events.
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111') select to_char((ts at time zone 'Europe/Stockholm')::date, 'YYYY-MM-DD') as day, count(*) filter (where event = 'brief') as brief, count(*) filter (where event = 'grill') as grill, count(*) filter (where event = 'record') as record from e group by 1 order by 1;
