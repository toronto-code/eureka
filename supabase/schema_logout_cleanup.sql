-- ============================================================
-- MYCELIUM — logout cleanup policies
-- Run this once in Supabase SQL Editor.
--
-- Why: the original schema only granted SELECT and INSERT on
-- agent_actions; without a DELETE policy, RLS silently rejects
-- the cleanup we run on signOut. Same for observer_events.
-- After this runs, signing out wipes the user's own rows from
-- chat_history, agent_actions, chat_conversations, observer_events.
-- ============================================================

-- agent_actions: allow user to delete their own
drop policy if exists "agent_actions own delete" on public.agent_actions;
create policy "agent_actions own delete" on public.agent_actions
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- observer_events: allow user to delete their own (optional — keeping
-- observer events lets the dashboard show historical git activity even
-- after logout. Comment the policy out if you want them preserved.)
drop policy if exists "observer_events own delete" on public.observer_events;
create policy "observer_events own delete" on public.observer_events
  for delete to authenticated
  using ((select auth.uid()) = user_id);
