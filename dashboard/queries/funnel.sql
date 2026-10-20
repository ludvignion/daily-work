-- funnel: Tasks per step
-- Distinct tasks that reached brief, grill and record. Reads public.events.
with e as (select * from public.events where install_id <> '11111111-1111-4111-8111-111111111111') select s.step, coalesce(c.tasks, 0) as tasks from (values (1, 'brief'), (2, 'grill'), (3, 'record')) as s(ord, step) left join (select event, count(distinct task_id) as tasks from e group by event) c on c.event = s.step order by s.ord;
