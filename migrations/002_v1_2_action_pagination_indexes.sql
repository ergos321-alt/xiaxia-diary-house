-- Xiaxia Diary House V1.1 -> V1.2 migration
-- Run once in Supabase SQL Editor before deploying V1.2.
-- These partial indexes support stable active-entry pagination and filtered counts.

create index if not exists diary_entries_active_date_created_id_idx
    on public.diary_entries (entry_date desc, created_at desc, id desc)
    where deleted_at is null;

create index if not exists diary_entries_active_author_date_created_id_idx
    on public.diary_entries (author, entry_date desc, created_at desc, id desc)
    where deleted_at is null;
