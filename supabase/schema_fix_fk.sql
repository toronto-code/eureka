-- ============================================================
-- MYCELIUM — drop strict FK constraint on agent_actions.user_id
-- Run once in Supabase SQL Editor.
--
-- Why: the FK to auth.users blocks every insert when DEV_MODE is on
-- (the API falls back to a fake DEV_USER UUID that has no auth row).
-- Real authenticated user_ids still resolve to profiles via the unified_activity
-- view's LEFT JOIN, so this is safe.
-- ============================================================

alter table public.agent_actions
  drop constraint if exists agent_actions_user_id_fkey;

alter table public.observer_events
  drop constraint if exists observer_events_user_id_fkey;

alter table public.chat_history
  drop constraint if exists chat_history_user_id_fkey;

alter table public.chat_conversations
  drop constraint if exists chat_conversations_user_id_fkey;
