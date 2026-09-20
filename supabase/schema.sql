-- Course Copilot: tables the API needs in Supabase.
--
-- Paste this whole file into the Supabase SQL editor (Database → SQL Editor → New query)
-- and run it once. Safe to run again: every statement is idempotent.
--
-- Row Level Security is ON for every table and no policies are created on purpose.
-- The API talks to these tables with the service-role key, which bypasses RLS; the
-- browser (anon key) can therefore read nothing here. Identity itself is Supabase Auth,
-- which has its own tables.

-- Who may use the copilot. Empty table = every signed-in account is allowed (bootstrap
-- mode, so the first login works before anyone has been added). One row = only listed
-- emails, or listed domains, get in.
create table if not exists public.allowlist (
  email      text primary key,            -- "ana@client.com", or "@client.com" for a whole domain
  client     text not null default '',    -- which client/course this person belongs to
  note       text not null default '',
  added_at   timestamptz not null default now()
);
alter table public.allowlist enable row level security;

-- One row per conversation. `state` is ConversationState.to_dict() from api/sessions.py:
-- the turns and the source log, nothing else. A Copilot is rebuilt from it on demand.
create table if not exists public.sessions (
  id          text primary key,
  user_id     text not null default 'anonymous',
  course      text not null default '',
  state       jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists sessions_user_updated on public.sessions (user_id, updated_at desc);
alter table public.sessions enable row level security;

-- One row per turn: who asked, what it cost, how long it took. The budget model and the
-- per-client usage report read from here.
create table if not exists public.turns (
  id                bigint generated always as identity primary key,
  ts                timestamptz not null default now(),
  user_id           text not null default 'anonymous',
  user_email        text not null default '',
  course            text not null default '',
  session_id        text,
  request_id        text,
  question_chars    integer,
  tools             text,
  prompt_tokens     integer,
  completion_tokens integer,
  llm_calls         integer,
  cost_usd          double precision,
  latency_s         double precision,
  error             text
);
create index if not exists turns_user_ts on public.turns (user_email, ts desc);
create index if not exists turns_course_ts on public.turns (course, ts desc);
alter table public.turns enable row level security;

-- Per-user totals, for a quick look in the dashboard: select * from usage_by_user;
create or replace view public.usage_by_user as
select user_email,
       course,
       count(*)                          as turns,
       count(error)                      as errors,
       round(sum(cost_usd)::numeric, 4)  as cost_usd,
       round(avg(latency_s)::numeric, 2) as avg_latency_s,
       min(ts)                           as first_turn,
       max(ts)                           as last_turn
from public.turns
group by user_email, course
order by turns desc;

-- Grants. On this project the service role had no privileges on tables created from the
-- SQL editor (PostgREST answered "permission denied for table allowlist" with the secret
-- key), so they are granted explicitly. RLS stays on; service_role bypasses it by design.
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;
-- And make sure the public key can read nothing here, whatever the defaults were.
revoke all on public.allowlist, public.sessions, public.turns, public.usage_by_user from anon, authenticated;
