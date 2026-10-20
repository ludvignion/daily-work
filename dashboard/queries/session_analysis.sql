-- session_analysis: Topics and confusion in real sessions
-- The latest analysis by evals/sessions.py: one row per kind, with its three bullets and how many judged runs it covers. Reads public.session_analysis.
with a as (select * from public.session_analysis order by made_at desc limit 1) select p.part, g->>'name' as name, jsonb_array_length(g->'runs') as run_count, a.runs as runs_total, g->'bullets' as bullets, g->'runs' as runs from a, lateral (values ('topics', a.topics), ('confusion', a.confusion)) as p(part, groups), jsonb_array_elements(p.groups) as g;
