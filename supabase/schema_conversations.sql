-- ============================================================
-- MYCELIUM — multi-conversation chat history (ChatGPT-style)
-- Run after schema.sql.  Idempotent — safe to re-run.
-- ============================================================

-- 1.  chat_conversations: one per "thread" the user starts
create table if not exists public.chat_conversations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  title       text not null default 'New chat',
  mode        text not null default 'agent' check (mode in ('agent','intel')),
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);
create index if not exists chat_conversations_user_idx
  on public.chat_conversations (user_id, updated_at desc);


-- 2.  Backfill chat_history with conversation_id FK
alter table public.chat_history
  add column if not exists conversation_id uuid references public.chat_conversations(id) on delete cascade;

create index if not exists chat_history_conv_idx
  on public.chat_history (conversation_id, id asc);


-- 3.  Trigger: bump conversations.updated_at whenever a new message is added,
--     and auto-derive the title from the first user message
create or replace function public.touch_conversation()
returns trigger language plpgsql as $$
begin
  if new.conversation_id is not null then
    update public.chat_conversations
       set updated_at = now(),
           title = case
             when title = 'New chat' and new.role = 'user'
               then left(new.content, 60)
             else title
           end
     where id = new.conversation_id;
  end if;
  return new;
end;
$$;

drop trigger if exists chat_history_touch on public.chat_history;
create trigger chat_history_touch
  after insert on public.chat_history
  for each row execute function public.touch_conversation();


-- 4.  RLS — users only see their own conversations
alter table public.chat_conversations enable row level security;

drop policy if exists "conversations own select" on public.chat_conversations;
create policy "conversations own select" on public.chat_conversations
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "conversations own insert" on public.chat_conversations;
create policy "conversations own insert" on public.chat_conversations
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "conversations own update" on public.chat_conversations;
create policy "conversations own update" on public.chat_conversations
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "conversations own delete" on public.chat_conversations;
create policy "conversations own delete" on public.chat_conversations
  for delete to authenticated
  using ((select auth.uid()) = user_id);


-- 5.  View: conversations with last message preview
create or replace view public.chat_conversations_with_preview as
select
  c.id,
  c.user_id,
  c.title,
  c.mode,
  c.created_at,
  c.updated_at,
  (select content from public.chat_history h
    where h.conversation_id = c.id
    order by h.id desc limit 1) as last_message,
  (select count(*) from public.chat_history h
    where h.conversation_id = c.id) as message_count
from public.chat_conversations c;
