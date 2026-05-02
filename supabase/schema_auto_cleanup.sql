-- ============================================================
-- MYCELIUM — auto-delete agent_actions + observer_events older than 20 minutes
-- Run this ONCE in Supabase SQL Editor → New query → Run.
-- Uses pg_cron (enabled by default on Supabase).
-- ============================================================

-- 1. Make sure the pg_cron extension is enabled
create extension if not exists pg_cron;


-- 2. Cleanup function — deletes rows older than the cutoff
create or replace function public.mycelium_cleanup_old_activity()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.agent_actions
   where created_at < now() - interval '20 minutes';

  delete from public.observer_events
   where created_at < now() - interval '20 minutes';
end;
$$;


-- 3. Schedule it every 5 minutes (granularity is minute-level)
--    First unschedule any existing job by name so re-running is idempotent.
do $$
declare
  job_id bigint;
begin
  for job_id in select jobid from cron.job where jobname = 'mycelium-cleanup-old-activity' loop
    perform cron.unschedule(job_id);
  end loop;
end $$;

select cron.schedule(
  'mycelium-cleanup-old-activity',  -- job name (used to find/replace)
  '*/5 * * * *',                    -- every 5 minutes
  $$ select public.mycelium_cleanup_old_activity(); $$
);


-- 4. Run it once now so existing old rows go right away
select public.mycelium_cleanup_old_activity();


-- 5. Show current row counts so you can verify
select
  (select count(*) from public.agent_actions)   as agent_actions_remaining,
  (select count(*) from public.observer_events) as observer_events_remaining;
