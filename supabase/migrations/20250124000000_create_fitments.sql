-- Enable pgvector extension
create extension if not exists vector;

-- Create fitments table
create table if not exists fitments (
  id bigserial primary key,
  year int not null,
  make text not null,
  model text not null,
  front_diameter float,
  front_width float,
  front_offset int,
  front_backspacing float,
  front_spacer float,
  rear_diameter float,
  rear_width float,
  rear_offset int,
  rear_backspacing float,
  rear_spacer float,
  tire_front text,
  tire_rear text,
  fitment_setup text,  -- 'square' or 'staggered'
  fitment_style text,  -- 'aggressive', 'flush', 'tucked', 'poke'
  has_poke boolean default false,
  needs_mods boolean default false,
  notes text,
  document text not null,  -- searchable text content
  created_at timestamptz default now()
);

-- Create indexes for common queries
create index if not exists idx_fitments_year on fitments(year);
create index if not exists idx_fitments_make on fitments(make);
create index if not exists idx_fitments_model on fitments(model);
create index if not exists idx_fitments_style on fitments(fitment_style);

-- Create full-text search index
alter table fitments add column if not exists fts tsvector
  generated always as (to_tsvector('english', document)) stored;
create index if not exists idx_fitments_fts on fitments using gin(fts);

-- Function to search fitments
create or replace function search_fitments(
  search_query text,
  filter_year int default null,
  filter_make text default null,
  filter_model text default null,
  filter_style text default null,
  result_limit int default 10
)
returns table (
  id bigint,
  year int,
  make text,
  model text,
  document text,
  front_diameter float,
  front_width float,
  front_offset int,
  rear_diameter float,
  rear_width float,
  rear_offset int,
  fitment_setup text,
  fitment_style text,
  has_poke boolean,
  needs_mods boolean,
  rank real
)
language plpgsql
as $$
begin
  return query
  select
    f.id,
    f.year,
    f.make,
    f.model,
    f.document,
    f.front_diameter,
    f.front_width,
    f.front_offset,
    f.rear_diameter,
    f.rear_width,
    f.rear_offset,
    f.fitment_setup,
    f.fitment_style,
    f.has_poke,
    f.needs_mods,
    ts_rank(f.fts, websearch_to_tsquery('english', search_query)) as rank
  from fitments f
  where
    (search_query is null or search_query = '' or f.fts @@ websearch_to_tsquery('english', search_query))
    and (filter_year is null or f.year = filter_year)
    and (filter_make is null or lower(f.make) = lower(filter_make))
    and (filter_model is null or lower(f.model) = lower(filter_model))
    and (filter_style is null or lower(f.fitment_style) = lower(filter_style))
  order by rank desc
  limit result_limit;
end;
$$;

-- Get unique makes
create or replace function get_makes()
returns table (make text)
language sql
as $$
  select distinct make from fitments order by make;
$$;

-- Get models for a make
create or replace function get_models(filter_make text)
returns table (model text)
language sql
as $$
  select distinct model from fitments where lower(make) = lower(filter_make) order by model;
$$;

-- Get years
create or replace function get_years()
returns table (year int)
language sql
as $$
  select distinct year from fitments order by year desc;
$$;
