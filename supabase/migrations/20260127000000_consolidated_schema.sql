-- Consolidated schema for the Wheel Fitment RAG API
-- Tables: fitments, kansei_wheels, vehicle_specs
-- Functions: search_fitments, get_makes, get_models, get_years,
--            find_vehicle_specs, upsert_vehicle_specs

-- =============================================================================
-- 1. Community fitments (54k+ records from CSV)
-- =============================================================================

CREATE TABLE IF NOT EXISTS fitments (
  id BIGSERIAL PRIMARY KEY,
  year INT NOT NULL,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  front_diameter FLOAT,
  front_width FLOAT,
  front_offset INT,
  front_backspacing FLOAT,
  front_spacer FLOAT,
  rear_diameter FLOAT,
  rear_width FLOAT,
  rear_offset INT,
  rear_backspacing FLOAT,
  rear_spacer FLOAT,
  tire_front TEXT,
  tire_rear TEXT,
  fitment_setup TEXT,    -- 'square' or 'staggered'
  fitment_style TEXT,    -- 'aggressive', 'flush', 'tucked', 'poke'
  has_poke BOOLEAN DEFAULT FALSE,
  needs_mods BOOLEAN DEFAULT FALSE,
  notes TEXT,
  document TEXT NOT NULL, -- full-text searchable content
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fitments_year ON fitments(year);
CREATE INDEX IF NOT EXISTS idx_fitments_make ON fitments(make);
CREATE INDEX IF NOT EXISTS idx_fitments_model ON fitments(model);
CREATE INDEX IF NOT EXISTS idx_fitments_style ON fitments(fitment_style);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_fitments_year_make_model ON fitments(year, make, model);
CREATE INDEX IF NOT EXISTS idx_fitments_make_model ON fitments(make, model);

-- Full-text search
ALTER TABLE fitments ADD COLUMN IF NOT EXISTS fts TSVECTOR
  GENERATED ALWAYS AS (to_tsvector('english', document)) STORED;
CREATE INDEX IF NOT EXISTS idx_fitments_fts ON fitments USING GIN(fts);

-- Search fitments via full-text + filters
CREATE OR REPLACE FUNCTION search_fitments(
  search_query TEXT,
  filter_year INT DEFAULT NULL,
  filter_make TEXT DEFAULT NULL,
  filter_model TEXT DEFAULT NULL,
  filter_style TEXT DEFAULT NULL,
  result_limit INT DEFAULT 10
)
RETURNS TABLE (
  id BIGINT,
  year INT,
  make TEXT,
  model TEXT,
  document TEXT,
  front_diameter FLOAT,
  front_width FLOAT,
  front_offset INT,
  rear_diameter FLOAT,
  rear_width FLOAT,
  rear_offset INT,
  fitment_setup TEXT,
  fitment_style TEXT,
  has_poke BOOLEAN,
  needs_mods BOOLEAN,
  rank REAL
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    f.id, f.year, f.make, f.model, f.document,
    f.front_diameter, f.front_width, f.front_offset,
    f.rear_diameter, f.rear_width, f.rear_offset,
    f.fitment_setup, f.fitment_style, f.has_poke, f.needs_mods,
    ts_rank(f.fts, websearch_to_tsquery('english', search_query)) AS rank
  FROM fitments f
  WHERE
    (search_query IS NULL OR search_query = '' OR f.fts @@ websearch_to_tsquery('english', search_query))
    AND (filter_year IS NULL OR f.year = filter_year)
    AND (filter_make IS NULL OR LOWER(f.make) = LOWER(filter_make))
    AND (filter_model IS NULL OR LOWER(f.model) LIKE LOWER(filter_model) || '%')
    AND (filter_style IS NULL OR LOWER(f.fitment_style) = LOWER(filter_style))
  ORDER BY rank DESC
  LIMIT result_limit;
END;
$$;

-- Metadata helpers
CREATE OR REPLACE FUNCTION get_makes()
RETURNS TABLE (make TEXT) LANGUAGE SQL AS $$
  SELECT DISTINCT make FROM fitments ORDER BY make;
$$;

CREATE OR REPLACE FUNCTION get_models(filter_make TEXT)
RETURNS TABLE (model TEXT) LANGUAGE SQL AS $$
  SELECT DISTINCT model FROM fitments WHERE LOWER(make) = LOWER(filter_make) ORDER BY model;
$$;

CREATE OR REPLACE FUNCTION get_years()
RETURNS TABLE (year INT) LANGUAGE SQL AS $$
  SELECT DISTINCT year FROM fitments ORDER BY year DESC;
$$;


-- =============================================================================
-- 2. Kansei wheel catalog
-- =============================================================================

CREATE TABLE IF NOT EXISTS kansei_wheels (
  id SERIAL PRIMARY KEY,
  model TEXT NOT NULL,
  finish TEXT,
  sku TEXT UNIQUE,
  diameter DECIMAL(4,1) NOT NULL,
  width DECIMAL(4,1) NOT NULL,
  bolt_pattern TEXT NOT NULL,
  wheel_offset INTEGER NOT NULL,
  price DECIMAL(8,2),
  category TEXT,
  url TEXT,
  in_stock BOOLEAN DEFAULT TRUE,
  weight DECIMAL(5,2),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kansei_bolt_pattern ON kansei_wheels(bolt_pattern);
CREATE INDEX IF NOT EXISTS idx_kansei_diameter ON kansei_wheels(diameter);
CREATE INDEX IF NOT EXISTS idx_kansei_model ON kansei_wheels(model);
CREATE INDEX IF NOT EXISTS idx_kansei_in_stock ON kansei_wheels(in_stock) WHERE in_stock = TRUE;


-- =============================================================================
-- 3. Vehicle specifications (populated from DB seeds + wheel-size.com scrapes)
-- =============================================================================

CREATE TABLE IF NOT EXISTS vehicle_specs (
  id SERIAL PRIMARY KEY,

  -- Vehicle identification
  year_start INTEGER,
  year_end INTEGER,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  chassis_code TEXT,
  trim TEXT,

  -- Wheel specifications
  bolt_pattern TEXT NOT NULL,
  center_bore DECIMAL(5,2) NOT NULL,
  stud_size TEXT,

  -- Wheel size limits (safe aftermarket ranges)
  oem_diameter DECIMAL(4,1),
  min_diameter INTEGER DEFAULT 15,
  max_diameter INTEGER DEFAULT 20,
  oem_width DECIMAL(4,1),
  min_width DECIMAL(4,1) DEFAULT 6.0,
  max_width DECIMAL(4,1) DEFAULT 10.0,
  oem_offset INTEGER,
  min_offset INTEGER DEFAULT -10,
  max_offset INTEGER DEFAULT 50,

  -- Data provenance
  source TEXT DEFAULT 'manual',           -- 'manual', 'web_search', 'wheel_size_scrape'
  source_url TEXT,
  verified BOOLEAN DEFAULT FALSE,
  confidence DECIMAL(3,2) DEFAULT 1.0,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT valid_year_range CHECK (year_start IS NULL OR year_end IS NULL OR year_start <= year_end),
  CONSTRAINT valid_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS idx_vehicle_specs_make_model ON vehicle_specs(make, model);
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_chassis ON vehicle_specs(chassis_code) WHERE chassis_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_bolt_pattern ON vehicle_specs(bolt_pattern);
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_year ON vehicle_specs(year_start, year_end);

-- Find specs by year/make/model/chassis
CREATE OR REPLACE FUNCTION find_vehicle_specs(
  p_year INTEGER DEFAULT NULL,
  p_make TEXT DEFAULT NULL,
  p_model TEXT DEFAULT NULL,
  p_chassis_code TEXT DEFAULT NULL
)
RETURNS TABLE (
  id INTEGER,
  year_start INTEGER,
  year_end INTEGER,
  make TEXT,
  model TEXT,
  chassis_code TEXT,
  trim TEXT,
  bolt_pattern TEXT,
  center_bore DECIMAL,
  stud_size TEXT,
  oem_diameter DECIMAL,
  min_diameter INTEGER,
  max_diameter INTEGER,
  oem_width DECIMAL,
  min_width DECIMAL,
  max_width DECIMAL,
  oem_offset INTEGER,
  min_offset INTEGER,
  max_offset INTEGER,
  source TEXT,
  verified BOOLEAN,
  confidence DECIMAL
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    vs.id, vs.year_start, vs.year_end, vs.make, vs.model,
    vs.chassis_code, vs.trim, vs.bolt_pattern, vs.center_bore, vs.stud_size,
    vs.oem_diameter, vs.min_diameter, vs.max_diameter,
    vs.oem_width, vs.min_width, vs.max_width,
    vs.oem_offset, vs.min_offset, vs.max_offset,
    vs.source, vs.verified, vs.confidence
  FROM vehicle_specs vs
  WHERE
    (p_chassis_code IS NULL OR UPPER(vs.chassis_code) = UPPER(p_chassis_code))
    AND (p_make IS NULL OR LOWER(vs.make) = LOWER(p_make))
    AND (p_model IS NULL OR LOWER(vs.model) LIKE '%' || LOWER(p_model) || '%')
    AND (p_year IS NULL OR (
      (vs.year_start IS NULL OR vs.year_start <= p_year)
      AND (vs.year_end IS NULL OR vs.year_end >= p_year)
    ))
  ORDER BY
    CASE WHEN p_chassis_code IS NOT NULL AND UPPER(vs.chassis_code) = UPPER(p_chassis_code) THEN 0 ELSE 1 END,
    CASE WHEN vs.verified THEN 0 ELSE 1 END,
    vs.confidence DESC,
    COALESCE(vs.year_end, 2030) - COALESCE(vs.year_start, 1950) ASC
  LIMIT 5;
END;
$$;

-- Upsert vehicle specs (used when scraping wheel-size.com)
CREATE OR REPLACE FUNCTION upsert_vehicle_specs(
  p_year_start INTEGER,
  p_year_end INTEGER,
  p_make TEXT,
  p_model TEXT,
  p_chassis_code TEXT,
  p_bolt_pattern TEXT,
  p_center_bore DECIMAL,
  p_stud_size TEXT DEFAULT NULL,
  p_min_diameter INTEGER DEFAULT 15,
  p_max_diameter INTEGER DEFAULT 20,
  p_min_width DECIMAL DEFAULT 6.0,
  p_max_width DECIMAL DEFAULT 10.0,
  p_min_offset INTEGER DEFAULT -10,
  p_max_offset INTEGER DEFAULT 50,
  p_source TEXT DEFAULT 'web_search',
  p_source_url TEXT DEFAULT NULL,
  p_confidence DECIMAL DEFAULT 0.8
)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
  v_id INTEGER;
BEGIN
  SELECT id INTO v_id
  FROM vehicle_specs
  WHERE LOWER(make) = LOWER(p_make)
    AND LOWER(model) = LOWER(p_model)
    AND (chassis_code IS NULL AND p_chassis_code IS NULL
         OR UPPER(chassis_code) = UPPER(p_chassis_code))
    AND (year_start = p_year_start OR (year_start IS NULL AND p_year_start IS NULL));

  IF v_id IS NOT NULL THEN
    UPDATE vehicle_specs SET
      year_end = COALESCE(p_year_end, year_end),
      bolt_pattern = p_bolt_pattern,
      center_bore = p_center_bore,
      stud_size = COALESCE(p_stud_size, stud_size),
      min_diameter = p_min_diameter,
      max_diameter = p_max_diameter,
      min_width = p_min_width,
      max_width = p_max_width,
      min_offset = p_min_offset,
      max_offset = p_max_offset,
      source = p_source,
      source_url = p_source_url,
      confidence = GREATEST(confidence, p_confidence),
      updated_at = NOW()
    WHERE id = v_id;
    RETURN v_id;
  ELSE
    INSERT INTO vehicle_specs (
      year_start, year_end, make, model, chassis_code,
      bolt_pattern, center_bore, stud_size,
      min_diameter, max_diameter, min_width, max_width, min_offset, max_offset,
      source, source_url, confidence
    ) VALUES (
      p_year_start, p_year_end, p_make, p_model, p_chassis_code,
      p_bolt_pattern, p_center_bore, p_stud_size,
      p_min_diameter, p_max_diameter, p_min_width, p_max_width, p_min_offset, p_max_offset,
      p_source, p_source_url, p_confidence
    )
    RETURNING id INTO v_id;
    RETURN v_id;
  END IF;
END;
$$;

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_vehicle_specs_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS vehicle_specs_updated_at ON vehicle_specs;
CREATE TRIGGER vehicle_specs_updated_at
  BEFORE UPDATE ON vehicle_specs
  FOR EACH ROW
  EXECUTE FUNCTION update_vehicle_specs_timestamp();


-- =============================================================================
-- 4. Seed data: verified vehicle specs
-- =============================================================================

INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, min_diameter, max_diameter, oem_width, min_width, max_width, oem_offset, min_offset, max_offset, source, verified, confidence)
VALUES
  -- BMW E30 (4x100 for base models)
  (1982, 1994, 'BMW', '318i',  'E30', '4x100', 57.1, 'M12x1.5', 14, 13, 17, 6.0, 6.0, 8.5, 35, 15, 42, 'manual', TRUE, 1.0),
  (1982, 1994, 'BMW', '325i',  'E30', '4x100', 57.1, 'M12x1.5', 14, 13, 17, 6.5, 6.0, 8.5, 35, 15, 42, 'manual', TRUE, 1.0),
  -- BMW E30 M3 uses 5x120 (different hubs/brakes from base E30)
  (1986, 1991, 'BMW', 'M3',    'E30', '5x120', 72.6, 'M12x1.5', 15, 14, 17, 7.0, 7.0, 9.0, 25, 10, 35, 'manual', TRUE, 1.0),

  -- BMW E36 (5x120)
  (1992, 1999, 'BMW', '318i',  'E36', '5x120', 72.6, 'M12x1.5', 15, 15, 18, 7.0, 7.0, 9.0, 35, 20, 45, 'manual', TRUE, 1.0),
  (1992, 1999, 'BMW', '325i',  'E36', '5x120', 72.6, 'M12x1.5', 15, 15, 18, 7.0, 7.0, 9.5, 35, 15, 45, 'manual', TRUE, 1.0),
  (1992, 1999, 'BMW', '328i',  'E36', '5x120', 72.6, 'M12x1.5', 16, 15, 18, 7.5, 7.0, 9.5, 35, 15, 45, 'manual', TRUE, 1.0),
  (1995, 1999, 'BMW', 'M3',    'E36', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 7.5, 7.5, 10.0, 41, 15, 45, 'manual', TRUE, 1.0),

  -- BMW E39 (5x120)
  (1996, 2003, 'BMW', '525i',  'E39', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 20, 10, 35, 'manual', TRUE, 1.0),
  (1996, 2003, 'BMW', '528i',  'E39', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 20, 10, 35, 'manual', TRUE, 1.0),
  (1996, 2003, 'BMW', '530i',  'E39', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 8.0, 7.5, 10.0, 20, 5, 35, 'manual', TRUE, 1.0),
  (1996, 2003, 'BMW', '540i',  'E39', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 8.0, 7.5, 10.0, 20, 5, 35, 'manual', TRUE, 1.0),
  (1998, 2003, 'BMW', 'M5',    'E39', '5x120', 72.6, 'M12x1.5', 18, 17, 20, 8.0, 8.0, 10.5, 20, 5, 35, 'manual', TRUE, 1.0),

  -- BMW E46 (5x120)
  (1999, 2006, 'BMW', '323i',  'E46', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 42, 20, 47, 'manual', TRUE, 1.0),
  (1999, 2006, 'BMW', '325i',  'E46', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 42, 20, 47, 'manual', TRUE, 1.0),
  (1999, 2006, 'BMW', '328i',  'E46', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 42, 20, 47, 'manual', TRUE, 1.0),
  (1999, 2006, 'BMW', '330i',  'E46', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 7.5, 7.0, 9.5, 42, 15, 47, 'manual', TRUE, 1.0),
  (2001, 2006, 'BMW', 'M3',    'E46', '5x120', 72.6, 'M12x1.5', 18, 17, 19, 8.0, 8.0, 10.5, 47, 20, 50, 'manual', TRUE, 1.0),

  -- BMW G20/G80 (5x112)
  (2019, NULL, 'BMW', '330i',  'G20', '5x112', 66.5, 'M14x1.25', 18, 17, 20, 7.5, 7.5, 9.5, 30, 15, 40, 'manual', TRUE, 1.0),
  (2019, NULL, 'BMW', 'M340i', 'G20', '5x112', 66.5, 'M14x1.25', 18, 17, 20, 8.0, 8.0, 10.0, 30, 15, 40, 'manual', TRUE, 1.0),
  (2021, NULL, 'BMW', 'M3',    'G80', '5x112', 66.5, 'M14x1.25', 18, 18, 20, 9.0, 8.5, 11.0, 23, 10, 35, 'manual', TRUE, 1.0),

  -- Honda Civic
  (1992, 2000, 'Honda', 'Civic',        'EG',    '4x100',   56.1, 'M12x1.5', 14, 14, 17, 5.5, 6.0, 8.0, 45, 25, 50, 'manual', TRUE, 1.0),
  (1996, 2000, 'Honda', 'Civic',        'EK',    '4x100',   56.1, 'M12x1.5', 14, 14, 17, 5.5, 6.0, 8.0, 45, 25, 50, 'manual', TRUE, 1.0),
  (2006, 2011, 'Honda', 'Civic',        'FG/FA', '5x114.3', 64.1, 'M12x1.5', 16, 16, 18, 6.5, 7.0, 9.0, 45, 30, 50, 'manual', TRUE, 1.0),
  (2016, 2021, 'Honda', 'Civic',        'FC/FK', '5x114.3', 64.1, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),
  (2017, 2021, 'Honda', 'Civic Type R', 'FK8',   '5x120',   64.1, 'M14x1.5', 20, 18, 20, 8.5, 8.5, 10.0, 60, 35, 50, 'manual', TRUE, 1.0),
  (2022, NULL, 'Honda', 'Civic',        'FL',    '5x114.3', 64.1, 'M12x1.5', 17, 17, 19, 7.0, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),

  -- Subaru WRX/STI
  (2002, 2014, 'Subaru', 'WRX',     'GD/GR', '5x100',   56.1, 'M12x1.25', 17, 16, 18, 7.0, 7.0, 9.0, 48, 30, 55, 'manual', TRUE, 1.0),
  (2004, 2014, 'Subaru', 'WRX STI', 'GD/GR', '5x114.3', 56.1, 'M12x1.25', 18, 17, 19, 8.5, 8.0, 10.0, 55, 30, 55, 'manual', TRUE, 1.0),
  (2015, 2021, 'Subaru', 'WRX',     'VA',    '5x114.3', 56.1, 'M12x1.25', 17, 17, 19, 8.0, 7.5, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
  (2015, 2021, 'Subaru', 'WRX STI', 'VA',    '5x114.3', 56.1, 'M12x1.25', 19, 18, 19, 8.5, 8.0, 10.0, 55, 30, 55, 'manual', TRUE, 1.0),

  -- Toyota / Scion
  (2012, 2020, 'Toyota', '86',       'ZN6', '5x100',   56.1, 'M12x1.25', 17, 17, 18, 7.0, 7.0, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
  (2012, 2020, 'Scion',  'FR-S',     'ZN6', '5x100',   56.1, 'M12x1.25', 17, 17, 18, 7.0, 7.0, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
  (2022, NULL, 'Toyota', 'GR86',     'ZN8', '5x114.3', 56.1, 'M12x1.25', 18, 17, 19, 7.5, 7.0, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
  (2019, NULL, 'Toyota', 'GR Supra', 'A90', '5x112',   66.5, 'M14x1.25', 19, 18, 20, 9.0, 8.5, 10.5, 32, 15, 40, 'manual', TRUE, 1.0),

  -- Mazda Miata / MX-5
  (1990, 1997, 'Mazda', 'Miata', 'NA', '4x100',   54.1, 'M12x1.5', 14, 14, 16, 5.5, 6.0, 8.0, 45, 25, 50, 'manual', TRUE, 1.0),
  (1999, 2005, 'Mazda', 'Miata', 'NB', '4x100',   54.1, 'M12x1.5', 15, 14, 17, 6.0, 6.0, 8.0, 40, 20, 45, 'manual', TRUE, 1.0),
  (2006, 2015, 'Mazda', 'MX-5',  'NC', '5x114.3', 67.1, 'M12x1.5', 17, 16, 18, 7.0, 6.5, 8.5, 50, 30, 55, 'manual', TRUE, 1.0),
  (2016, NULL, 'Mazda', 'MX-5',  'ND', '5x114.3', 67.1, 'M12x1.5', 16, 16, 17, 6.5, 6.5, 8.0, 50, 35, 55, 'manual', TRUE, 1.0),

  -- Nissan
  (1989, 1994, 'Nissan', '240SX', 'S13', '4x114.3', 66.1, 'M12x1.25', 15, 15, 18, 6.0, 7.0, 9.5, 40, 0, 30, 'manual', TRUE, 1.0),
  (1995, 1998, 'Nissan', '240SX', 'S14', '5x114.3', 66.1, 'M12x1.25', 16, 16, 18, 6.5, 7.0, 9.5, 40, 0, 35, 'manual', TRUE, 1.0),
  (2003, 2008, 'Nissan', '350Z',  'Z33', '5x114.3', 66.1, 'M12x1.25', 18, 17, 19, 8.0, 8.0, 10.5, 30, 5, 40, 'manual', TRUE, 1.0),
  (2009, 2020, 'Nissan', '370Z',  'Z34', '5x114.3', 66.1, 'M12x1.25', 18, 18, 20, 9.0, 8.5, 11.0, 30, 5, 40, 'manual', TRUE, 1.0)

ON CONFLICT DO NOTHING;
