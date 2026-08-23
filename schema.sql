-- Xiaxia Diary House V1.1 full schema for a fresh installation.
-- Existing V1 deployments must use migrations/001_v1_1_marks_and_trash.sql instead.

create extension if not exists pgcrypto;

create table if not exists public.diary_entries (
    id uuid primary key default gen_random_uuid(),
    author text not null check (author in ('user', 'xiaxia')),
    title text null check (char_length(title) <= 200),
    content text not null check (char_length(btrim(content)) > 0 and char_length(content) <= 100000),
    entry_date date not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz null,
    deleted_by text null check (deleted_by in ('user', 'xiaxia'))
);

create table if not exists public.diary_replies (
    id uuid primary key default gen_random_uuid(),
    entry_id uuid not null references public.diary_entries(id) on delete cascade,
    author text not null check (author in ('user', 'xiaxia')),
    content text not null check (char_length(btrim(content)) > 0 and char_length(content) <= 100000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.diary_marks (
    id uuid primary key default gen_random_uuid(),
    entry_id uuid not null references public.diary_entries(id) on delete cascade,
    author text not null check (author in ('user', 'xiaxia')),
    mark_type text not null check (mark_type in ('leaf')),
    created_at timestamptz not null default now(),
    unique (entry_id, author, mark_type)
);

create index if not exists diary_entries_date_created_idx
    on public.diary_entries (entry_date desc, created_at desc);
create index if not exists diary_entries_author_date_idx
    on public.diary_entries (author, entry_date desc);
create index if not exists diary_replies_entry_created_idx
    on public.diary_replies (entry_id, created_at asc);
create index if not exists diary_replies_created_idx
    on public.diary_replies (created_at desc);
create index if not exists diary_entries_deleted_idx
    on public.diary_entries (deleted_at desc) where deleted_at is not null;
create index if not exists diary_marks_entry_created_idx
    on public.diary_marks (entry_id, created_at asc);

alter table public.diary_entries enable row level security;
alter table public.diary_replies enable row level security;
alter table public.diary_marks enable row level security;

-- No anon/authenticated policies are created. The Flask server connects directly
-- to PostgreSQL with its private DATABASE_URL, so browser clients cannot query
-- these tables through Supabase Data API.
revoke all on table public.diary_entries from anon, authenticated;
revoke all on table public.diary_replies from anon, authenticated;
revoke all on table public.diary_marks from anon, authenticated;
