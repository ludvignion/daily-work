-- daily: Skill runs per day
-- Brief, grill and record events per day in Stockholm time. Reads live.events.
with e as (select * from live.events) select to_char((ts at time zone 'Europe/Stockholm')::date, 'YYYY-MM-DD') as day, count(*) filter (where event = 'brief') as brief, count(*) filter (where event = 'grill') as grill, count(*) filter (where event = 'record') as record from e group by 1 order by 1;
