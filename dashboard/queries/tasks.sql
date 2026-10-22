-- tasks: Tasks list
-- One row per task with steps reached, duration and rating. Reads live.events.
with e as (select * from live.events) select left(task_id::text, 8) as task, to_char(min(ts) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as started, (array_agg(plugin_version order by ts desc))[1] as version, bool_or(event = 'grill') as grilled, bool_or(event = 'record') as recorded, round(extract(epoch from max(ts) - min(ts)) / 60)::int as minutes, max(rating) as rating from e where task_id is not null group by task_id order by min(ts) desc;
