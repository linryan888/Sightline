begin;

create table public.chunks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  date date not null,
  storage_path text not null,
  duration_seconds double precision,
  status text not null default 'uploaded',
  created_at timestamptz not null default now()
);

create table public.windows (
  id uuid primary key default gen_random_uuid(),
  chunk_id uuid not null references public.chunks(id),
  start_seconds double precision not null,
  end_seconds double precision not null,
  score double precision
);

create table public.recaps (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  date date not null,
  storage_path text not null,
  created_at timestamptz not null default now()
);

create index chunks_user_date_idx
  on public.chunks (user_id, date);

create index windows_chunk_id_idx
  on public.windows (chunk_id);

create index recaps_user_date_idx
  on public.recaps (user_id, date);

alter table public.chunks enable row level security;
alter table public.windows enable row level security;
alter table public.recaps enable row level security;

commit;

-- Storage buckets created through the Supabase Dashboard:
-- footage (private)
-- recaps (private)