-- ============================================================
-- MYCELIUM SCHEMA FOR SUPABASE
-- Run once in Supabase SQL Editor. Idempotent — safe to re-run.
-- Project: https://kltppzruzvrxfqqngaax.supabase.co
-- ============================================================


-- ------------------------------------------------------------
-- 1. TABLES
-- ------------------------------------------------------------

-- Chat history per logged-in user
create table if not exists public.chat_history (
  id          bigserial primary key,
  user_id     uuid references auth.users(id) on delete cascade,
  role        text not null check (role in ('user','assistant','system')),
  content     text not null,
  created_at  timestamptz default now()
);
create index if not exists chat_history_user_idx on public.chat_history (user_id, id desc);


-- Every tool call the agent makes (audit log)
create table if not exists public.agent_actions (
  id              bigserial primary key,
  user_id         uuid references auth.users(id) on delete cascade,
  tool            text not null,
  args            jsonb,
  result_summary  text,
  status          text check (status in ('running','ok','error','blocked','awaiting_confirm')),
  created_at      timestamptz default now()
);
create index if not exists agent_actions_user_idx on public.agent_actions (user_id, id desc);
create index if not exists agent_actions_tool_idx on public.agent_actions (tool);


-- Whisper transcripts for Slack audio/video files (cached forever)
create table if not exists public.mycelium_transcripts (
  file_id         text primary key,
  name            text,
  mimetype        text,
  text            text,
  transcribed_at  timestamptz default now()
);


-- Observer events (git activity from local laptop daemons)
create table if not exists public.observer_events (
  id          bigserial primary key,
  user_id     uuid references auth.users(id) on delete set null,
  type        text not null,
  source      text,
  actor       jsonb,
  object      jsonb,
  occurred_at timestamptz,
  created_at  timestamptz default now()
);
create index if not exists observer_events_user_idx on public.observer_events (user_id, id desc);
create index if not exists observer_events_type_idx on public.observer_events (type);


-- Lightweight integration sync tracking
create table if not exists public.integration_syncs (
  connector       text primary key,
  last_sync_at    timestamptz,
  status          text check (status in ('ok','error')),
  error_message   text,
  updated_at      timestamptz default now()
);


-- Profiles table — extra data per user beyond auth.users
create table if not exists public.profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  display_name  text,
  github_login  text,
  slack_user_id text,
  jira_email    text,
  created_at    timestamptz default now(),
  updated_at    timestamptz default now()
);


-- ------------------------------------------------------------
-- 2. AUTO-CREATE PROFILE ON SIGNUP
-- ------------------------------------------------------------

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();


-- ------------------------------------------------------------
-- 3. ROW-LEVEL SECURITY
-- ------------------------------------------------------------

alter table public.chat_history          enable row level security;
alter table public.agent_actions         enable row level security;
alter table public.observer_events       enable row level security;
alter table public.profiles              enable row level security;
alter table public.mycelium_transcripts  enable row level security;
alter table public.integration_syncs     enable row level security;


-- chat_history: users see/insert/delete only their own rows
drop policy if exists "chat_history own select" on public.chat_history;
create policy "chat_history own select" on public.chat_history
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "chat_history own insert" on public.chat_history;
create policy "chat_history own insert" on public.chat_history
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "chat_history own delete" on public.chat_history;
create policy "chat_history own delete" on public.chat_history
  for delete to authenticated
  using ((select auth.uid()) = user_id);


-- agent_actions: users see/insert only their own rows
drop policy if exists "agent_actions own select" on public.agent_actions;
create policy "agent_actions own select" on public.agent_actions
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "agent_actions own insert" on public.agent_actions;
create policy "agent_actions own insert" on public.agent_actions
  for insert to authenticated
  with check ((select auth.uid()) = user_id);


-- observer_events: users see/insert only their own rows
drop policy if exists "observer_events own select" on public.observer_events;
create policy "observer_events own select" on public.observer_events
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "observer_events own insert" on public.observer_events;
create policy "observer_events own insert" on public.observer_events
  for insert to authenticated
  with check ((select auth.uid()) = user_id);


-- profiles: any authenticated user can read all profiles (so the UI can show "Yuvaansh did X");
-- users may update only their own row
drop policy if exists "profiles read all" on public.profiles;
create policy "profiles read all" on public.profiles
  for select to authenticated
  using (true);

drop policy if exists "profiles own update" on public.profiles;
create policy "profiles own update" on public.profiles
  for update to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);


-- transcripts and integration_syncs: shared across the team — any authenticated user can read/write
drop policy if exists "transcripts shared" on public.mycelium_transcripts;
create policy "transcripts shared" on public.mycelium_transcripts
  for all to authenticated
  using (true)
  with check (true);

drop policy if exists "syncs shared" on public.integration_syncs;
create policy "syncs shared" on public.integration_syncs
  for all to authenticated
  using (true)
  with check (true);


-- ------------------------------------------------------------
-- 4. CONVENIENCE VIEWS — "who is doing what?"
-- ------------------------------------------------------------

create or replace view public.activity_by_user as
select
  a.id,
  a.created_at,
  a.tool,
  a.status,
  a.result_summary,
  p.display_name,
  p.github_login,
  p.slack_user_id,
  a.user_id
from public.agent_actions a
left join public.profiles p on p.id = a.user_id;


-- Unified activity stream: agent tool calls AND observer git events, joined to profiles
create or replace view public.unified_activity as
  select
    'agent_action'                                     as kind,
    a.created_at                                       as at,
    p.display_name,
    p.github_login,
    a.user_id,
    a.tool                                             as label,
    a.result_summary                                   as detail,
    a.status
  from public.agent_actions a
  left join public.profiles p on p.id = a.user_id
union all
  select
    'observer_event'                                   as kind,
    coalesce(e.occurred_at, e.created_at)              as at,
    p.display_name,
    p.github_login,
    e.user_id,
    e.type                                             as label,
    coalesce(e.object->>'repo', e.object->>'id', '')   as detail,
    'ok'                                               as status
  from public.observer_events e
  left join public.profiles p on p.id = e.user_id
order by at desc;


-- ------------------------------------------------------------
-- 5. NEXT STEPS (do these in the Supabase dashboard, not SQL)
-- ------------------------------------------------------------
--
-- Supabase deprecated the legacy JWT-based "anon" and "service_role" keys.
-- New projects use:
--   - sb_publishable_xxx  (replaces anon — safe for browser/frontend)
--   - sb_secret_xxx       (replaces service_role — backend only, never expose)
-- These are NOT JWTs and must NOT be sent in the Authorization header.
-- User JWTs (from auth.signInWithPassword) still go in Authorization: Bearer ...
--
-- a) Authentication → Providers → Email
--    → uncheck "Confirm email" so signups go through immediately
--    → click Save
--
-- b) Project Settings → API Keys → copy:
--    - Project URL: https://kltppzruzvrxfqqngaax.supabase.co
--    - Publishable key:  sb_publishable_xxxxxxxxxxxxxxxx   (used by frontend + backend)
--    - Secret key:       sb_secret_xxxxxxxxxxxxxxxx        (backend only — bypasses RLS)
--    If you don't see the new keys, click "Opt in to new API keys" first.
--
-- c) Add to .env at the project root:
--    SUPABASE_URL=https://kltppzruzvrxfqqngaax.supabase.co
--    SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
--    SUPABASE_SECRET_KEY=sb_secret_...
--    VITE_SUPABASE_URL=https://kltppzruzvrxfqqngaax.supabase.co
--    VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
--
-- d) Tell the assistant the keys are in place — the API + frontend will be migrated
--    from local Postgres to Supabase, and a Login screen will be added.
-- ============================================================
