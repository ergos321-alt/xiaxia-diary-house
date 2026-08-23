-- Xiaxia Diary House V1 -> V1.1 migration
-- Run once in Supabase SQL Editor before deploying the V1.1 application.

alter table public.diary_entries
    add column if not exists deleted_at timestamptz null;

alter table public.diary_entries
    add column if not exists deleted_by text null;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'diary_entries_deleted_by_check'
          and conrelid = 'public.diary_entries'::regclass
    ) then
        alter table public.diary_entries
            add constraint diary_entries_deleted_by_check
            check (deleted_by in ('user', 'xiaxia'));
    end if;
end
$$;

create table if not exists public.diary_marks (
    id uuid primary key default gen_random_uuid(),
    entry_id uuid not null references public.diary_entries(id) on delete cascade,
    author text not null check (author in ('user', 'xiaxia')),
    mark_type text not null check (mark_type in ('leaf')),
    created_at timestamptz not null default now(),
    unique (entry_id, author, mark_type)
);

create index if not exists diary_entries_deleted_idx
    on public.diary_entries (deleted_at desc) where deleted_at is not null;

create index if not exists diary_marks_entry_created_idx
    on public.diary_marks (entry_id, created_at asc);

alter table public.diary_marks enable row level security;
revoke all on table public.diary_marks from anon, authenticated;
