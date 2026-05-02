-- ============================================================
-- MYCELIUM — team-wide activity fix
-- Run this ONCE in Supabase SQL Editor → New query → Run.
-- Idempotent (safe to re-run).
--
-- Fixes:
--  1. Foreign-key on agent_actions.user_id was blocking inserts when
--     DEV_USER fallback fired (FK to auth.users).  Drops the FK so
--     every insert succeeds.  Real user_ids still resolve to profiles
--     via the unified_activity LEFT JOIN.
--  2. RLS only let users see their OWN actions/observer events, so the
--     Team Web tab couldn't show other team members.  Loosens the
--     SELECT policy to "any authenticated user can read team activity".
--  3. Adds DELETE policies for the logout cleanup we run on signOut.
-- ============================================================


-- 1. DROP FK CONSTRAINTS (so DEV_USER fallback inserts don't break)
alter table public.agent_actions
  drop constraint if exists agent_actions_user_id_fkey;
alter table public.observer_events
  drop constraint if exists observer_events_user_id_fkey;
alter table public.chat_history
  drop constraint if exists chat_history_user_id_fkey;
alter table public.chat_conversations
  drop constraint if exists chat_conversations_user_id_fkey;


-- 2. RELAX SELECT RLS — authenticated users can read team-wide activity
--    (so Team Web can count actions across all team members)

-- agent_actions: any authenticated user can READ all rows
drop policy if exists "agent_actions own select" on public.agent_actions;
drop policy if exists "agent_actions team select" on public.agent_actions;
create policy "agent_actions team select" on public.agent_actions
  for select to authenticated using (true);

-- observer_events: any authenticated user can READ all rows
drop policy if exists "observer_events own select" on public.observer_events;
drop policy if exists "observer_events team select" on public.observer_events;
create policy "observer_events team select" on public.observer_events
  for select to authenticated using (true);

-- chat_history and chat_conversations stay strictly per-user (private chats).


-- 3. DELETE policies for logout cleanup

-- agent_actions: delete only your own
drop policy if exists "agent_actions own delete" on public.agent_actions;
create policy "agent_actions own delete" on public.agent_actions
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- observer_events: delete only your own
drop policy if exists "observer_events own delete" on public.observer_events;
create policy "observer_events own delete" on public.observer_events
  for delete to authenticated
  using ((select auth.uid()) = user_id);


-- 4. Confirm by counting (will be visible in the SQL Editor result pane)
select
  (select count(*) from public.profiles)        as profiles,
  (select count(*) from public.agent_actions)   as agent_actions,
  (select count(*) from public.observer_events) as observer_events,
  (select count(*) from public.chat_history)    as chat_history;
