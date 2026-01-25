-- Vehicle specifications table for canonical bolt patterns and specs
-- This stores validated vehicle data (from DB lookups or web searches)

CREATE TABLE IF NOT EXISTS vehicle_specs (
    id SERIAL PRIMARY KEY,

    -- Vehicle identification
    year_start INTEGER,                    -- Start of production year range
    year_end INTEGER,                      -- End of production year range (NULL = current)
    make TEXT NOT NULL,                    -- Manufacturer (normalized: "Chevrolet" not "chevy")
    model TEXT NOT NULL,                   -- Model name
    chassis_code TEXT,                     -- E30, E36, FK8, etc. (optional)
    trim TEXT,                             -- Specific trim level (optional)

    -- Wheel specifications
    bolt_pattern TEXT NOT NULL,            -- e.g., "5x120", "4x100"
    center_bore DECIMAL(5,2) NOT NULL,     -- Center bore in mm (e.g., 72.6)
    stud_size TEXT,                        -- e.g., "M12x1.5", "M14x1.5"

    -- Wheel size limits
    oem_diameter DECIMAL(4,1),             -- Stock wheel diameter
    min_diameter INTEGER DEFAULT 15,       -- Minimum safe diameter (brake clearance)
    max_diameter INTEGER DEFAULT 20,       -- Maximum recommended diameter
    oem_width DECIMAL(4,1),                -- Stock wheel width
    min_width DECIMAL(4,1) DEFAULT 6.0,    -- Minimum recommended width
    max_width DECIMAL(4,1) DEFAULT 10.0,   -- Maximum recommended width
    oem_offset INTEGER,                    -- Stock offset
    min_offset INTEGER DEFAULT -10,        -- Minimum offset (more poke)
    max_offset INTEGER DEFAULT 50,         -- Maximum offset (more tuck)

    -- Suspension adjustment factors (how much offset changes with suspension)
    stock_offset_adjustment INTEGER DEFAULT 0,      -- No change for stock
    lowered_offset_adjustment INTEGER DEFAULT -5,   -- Can go 5mm lower offset when lowered
    coilover_offset_adjustment INTEGER DEFAULT -10, -- Can go 10mm lower with coilovers
    air_offset_adjustment INTEGER DEFAULT -15,      -- Most aggressive with air

    -- Data source and validation
    source TEXT DEFAULT 'manual',          -- 'manual', 'web_search', 'community_data'
    source_url TEXT,                       -- URL if from web search
    verified BOOLEAN DEFAULT FALSE,        -- Has been human-verified
    confidence DECIMAL(3,2) DEFAULT 1.0,   -- 0.0-1.0 confidence score

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_year_range CHECK (year_start IS NULL OR year_end IS NULL OR year_start <= year_end),
    CONSTRAINT valid_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_make_model ON vehicle_specs(make, model);
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_chassis ON vehicle_specs(chassis_code) WHERE chassis_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_bolt_pattern ON vehicle_specs(bolt_pattern);
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_year ON vehicle_specs(year_start, year_end);

-- Function to find vehicle specs by year/make/model or chassis code
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
    stock_offset_adjustment INTEGER,
    lowered_offset_adjustment INTEGER,
    coilover_offset_adjustment INTEGER,
    air_offset_adjustment INTEGER,
    source TEXT,
    verified BOOLEAN,
    confidence DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        vs.id,
        vs.year_start,
        vs.year_end,
        vs.make,
        vs.model,
        vs.chassis_code,
        vs.trim,
        vs.bolt_pattern,
        vs.center_bore,
        vs.stud_size,
        vs.oem_diameter,
        vs.min_diameter,
        vs.max_diameter,
        vs.oem_width,
        vs.min_width,
        vs.max_width,
        vs.oem_offset,
        vs.min_offset,
        vs.max_offset,
        vs.stock_offset_adjustment,
        vs.lowered_offset_adjustment,
        vs.coilover_offset_adjustment,
        vs.air_offset_adjustment,
        vs.source,
        vs.verified,
        vs.confidence
    FROM vehicle_specs vs
    WHERE
        -- Match by chassis code if provided
        (p_chassis_code IS NULL OR UPPER(vs.chassis_code) = UPPER(p_chassis_code))
        -- Match by make (case insensitive)
        AND (p_make IS NULL OR LOWER(vs.make) = LOWER(p_make))
        -- Match by model (partial match, case insensitive)
        AND (p_model IS NULL OR LOWER(vs.model) LIKE '%' || LOWER(p_model) || '%')
        -- Match by year (within range)
        AND (p_year IS NULL OR (
            (vs.year_start IS NULL OR vs.year_start <= p_year)
            AND (vs.year_end IS NULL OR vs.year_end >= p_year)
        ))
    ORDER BY
        -- Prefer exact chassis code matches
        CASE WHEN p_chassis_code IS NOT NULL AND UPPER(vs.chassis_code) = UPPER(p_chassis_code) THEN 0 ELSE 1 END,
        -- Prefer verified specs
        CASE WHEN vs.verified THEN 0 ELSE 1 END,
        -- Prefer higher confidence
        vs.confidence DESC,
        -- Prefer more specific year ranges
        COALESCE(vs.year_end, 2030) - COALESCE(vs.year_start, 1950) ASC
    LIMIT 5;
END;
$$ LANGUAGE plpgsql;

-- Function to insert or update vehicle specs
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
RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
BEGIN
    -- Check if exists
    SELECT id INTO v_id
    FROM vehicle_specs
    WHERE LOWER(make) = LOWER(p_make)
      AND LOWER(model) = LOWER(p_model)
      AND (chassis_code IS NULL AND p_chassis_code IS NULL
           OR UPPER(chassis_code) = UPPER(p_chassis_code))
      AND (year_start = p_year_start OR (year_start IS NULL AND p_year_start IS NULL));

    IF v_id IS NOT NULL THEN
        -- Update existing
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
        -- Insert new
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
$$ LANGUAGE plpgsql;

-- Seed with common BMW chassis codes (these are well-known, verified)
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, min_diameter, max_diameter, oem_width, min_width, max_width, oem_offset, min_offset, max_offset, source, verified, confidence)
VALUES
    -- BMW E30 (4x100 - unique among BMWs)
    (1982, 1994, 'BMW', '318i', 'E30', '4x100', 57.1, 'M12x1.5', 14, 13, 17, 6.0, 6.0, 8.5, 35, 15, 42, 'manual', TRUE, 1.0),
    (1982, 1994, 'BMW', '325i', 'E30', '4x100', 57.1, 'M12x1.5', 14, 13, 17, 6.5, 6.0, 8.5, 35, 15, 42, 'manual', TRUE, 1.0),
    (1986, 1991, 'BMW', 'M3', 'E30', '4x100', 57.1, 'M12x1.5', 15, 14, 17, 7.0, 7.0, 9.0, 25, 10, 35, 'manual', TRUE, 1.0),

    -- BMW E36 (5x120)
    (1992, 1999, 'BMW', '318i', 'E36', '5x120', 72.6, 'M12x1.5', 15, 15, 18, 7.0, 7.0, 9.0, 35, 20, 45, 'manual', TRUE, 1.0),
    (1992, 1999, 'BMW', '325i', 'E36', '5x120', 72.6, 'M12x1.5', 15, 15, 18, 7.0, 7.0, 9.5, 35, 15, 45, 'manual', TRUE, 1.0),
    (1992, 1999, 'BMW', '328i', 'E36', '5x120', 72.6, 'M12x1.5', 16, 15, 18, 7.5, 7.0, 9.5, 35, 15, 45, 'manual', TRUE, 1.0),
    (1995, 1999, 'BMW', 'M3', 'E36', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 7.5, 7.5, 10.0, 41, 15, 45, 'manual', TRUE, 1.0),

    -- BMW E39 (5x120)
    (1996, 2003, 'BMW', '525i', 'E39', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 20, 10, 35, 'manual', TRUE, 1.0),
    (1996, 2003, 'BMW', '528i', 'E39', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 20, 10, 35, 'manual', TRUE, 1.0),
    (1996, 2003, 'BMW', '530i', 'E39', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 8.0, 7.5, 10.0, 20, 5, 35, 'manual', TRUE, 1.0),
    (1996, 2003, 'BMW', '540i', 'E39', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 8.0, 7.5, 10.0, 20, 5, 35, 'manual', TRUE, 1.0),
    (1998, 2003, 'BMW', 'M5', 'E39', '5x120', 72.6, 'M12x1.5', 18, 17, 20, 8.0, 8.0, 10.5, 20, 5, 35, 'manual', TRUE, 1.0),

    -- BMW E46 (5x120)
    (1999, 2006, 'BMW', '323i', 'E46', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 42, 20, 47, 'manual', TRUE, 1.0),
    (1999, 2006, 'BMW', '325i', 'E46', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 42, 20, 47, 'manual', TRUE, 1.0),
    (1999, 2006, 'BMW', '328i', 'E46', '5x120', 72.6, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 42, 20, 47, 'manual', TRUE, 1.0),
    (1999, 2006, 'BMW', '330i', 'E46', '5x120', 72.6, 'M12x1.5', 17, 16, 19, 7.5, 7.0, 9.5, 42, 15, 47, 'manual', TRUE, 1.0),
    (2001, 2006, 'BMW', 'M3', 'E46', '5x120', 72.6, 'M12x1.5', 18, 17, 19, 8.0, 8.0, 10.5, 47, 20, 50, 'manual', TRUE, 1.0),

    -- BMW G20/G80 (5x112 - new pattern)
    (2019, NULL, 'BMW', '330i', 'G20', '5x112', 66.5, 'M14x1.25', 18, 17, 20, 7.5, 7.5, 9.5, 30, 15, 40, 'manual', TRUE, 1.0),
    (2019, NULL, 'BMW', 'M340i', 'G20', '5x112', 66.5, 'M14x1.25', 18, 17, 20, 8.0, 8.0, 10.0, 30, 15, 40, 'manual', TRUE, 1.0),
    (2021, NULL, 'BMW', 'M3', 'G80', '5x112', 66.5, 'M14x1.25', 18, 18, 20, 9.0, 8.5, 11.0, 23, 10, 35, 'manual', TRUE, 1.0),

    -- Honda Civic (4x100 pre-2006, 5x114.3 after)
    (1992, 2000, 'Honda', 'Civic', 'EG', '4x100', 56.1, 'M12x1.5', 14, 14, 17, 5.5, 6.0, 8.0, 45, 25, 50, 'manual', TRUE, 1.0),
    (1996, 2000, 'Honda', 'Civic', 'EK', '4x100', 56.1, 'M12x1.5', 14, 14, 17, 5.5, 6.0, 8.0, 45, 25, 50, 'manual', TRUE, 1.0),
    (2006, 2011, 'Honda', 'Civic', 'FG/FA', '5x114.3', 64.1, 'M12x1.5', 16, 16, 18, 6.5, 7.0, 9.0, 45, 30, 50, 'manual', TRUE, 1.0),
    (2016, 2021, 'Honda', 'Civic', 'FC/FK', '5x114.3', 64.1, 'M12x1.5', 16, 16, 19, 7.0, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),
    (2017, 2021, 'Honda', 'Civic Type R', 'FK8', '5x120', 64.1, 'M14x1.5', 20, 18, 20, 8.5, 8.5, 10.0, 60, 35, 50, 'manual', TRUE, 1.0),
    (2022, NULL, 'Honda', 'Civic', 'FL', '5x114.3', 64.1, 'M12x1.5', 17, 17, 19, 7.0, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),

    -- Subaru WRX/STI
    (2002, 2014, 'Subaru', 'WRX', 'GD/GR', '5x100', 56.1, 'M12x1.25', 17, 16, 18, 7.0, 7.0, 9.0, 48, 30, 55, 'manual', TRUE, 1.0),
    (2004, 2014, 'Subaru', 'WRX STI', 'GD/GR', '5x114.3', 56.1, 'M12x1.25', 18, 17, 19, 8.5, 8.0, 10.0, 55, 30, 55, 'manual', TRUE, 1.0),
    (2015, 2021, 'Subaru', 'WRX', 'VA', '5x114.3', 56.1, 'M12x1.25', 17, 17, 19, 8.0, 7.5, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
    (2015, 2021, 'Subaru', 'WRX STI', 'VA', '5x114.3', 56.1, 'M12x1.25', 19, 18, 19, 8.5, 8.0, 10.0, 55, 30, 55, 'manual', TRUE, 1.0),

    -- Toyota/Scion
    (2012, 2020, 'Toyota', '86', 'ZN6', '5x100', 56.1, 'M12x1.25', 17, 17, 18, 7.0, 7.0, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
    (2012, 2020, 'Scion', 'FR-S', 'ZN6', '5x100', 56.1, 'M12x1.25', 17, 17, 18, 7.0, 7.0, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
    (2022, NULL, 'Toyota', 'GR86', 'ZN8', '5x114.3', 56.1, 'M12x1.25', 18, 17, 19, 7.5, 7.0, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),
    (2019, NULL, 'Toyota', 'GR Supra', 'A90', '5x112', 66.5, 'M14x1.25', 19, 18, 20, 9.0, 8.5, 10.5, 32, 15, 40, 'manual', TRUE, 1.0),

    -- Mazda Miata
    (1990, 1997, 'Mazda', 'Miata', 'NA', '4x100', 54.1, 'M12x1.5', 14, 14, 16, 5.5, 6.0, 8.0, 45, 25, 50, 'manual', TRUE, 1.0),
    (1999, 2005, 'Mazda', 'Miata', 'NB', '4x100', 54.1, 'M12x1.5', 15, 14, 17, 6.0, 6.0, 8.0, 40, 20, 45, 'manual', TRUE, 1.0),
    (2006, 2015, 'Mazda', 'MX-5', 'NC', '5x114.3', 67.1, 'M12x1.5', 17, 16, 18, 7.0, 6.5, 8.5, 50, 30, 55, 'manual', TRUE, 1.0),
    (2016, NULL, 'Mazda', 'MX-5', 'ND', '5x114.3', 67.1, 'M12x1.5', 16, 16, 17, 6.5, 6.5, 8.0, 50, 35, 55, 'manual', TRUE, 1.0),

    -- Nissan
    (1989, 1994, 'Nissan', '240SX', 'S13', '4x114.3', 66.1, 'M12x1.25', 15, 15, 18, 6.0, 7.0, 9.5, 40, 0, 30, 'manual', TRUE, 1.0),
    (1995, 1998, 'Nissan', '240SX', 'S14', '5x114.3', 66.1, 'M12x1.25', 16, 16, 18, 6.5, 7.0, 9.5, 40, 0, 35, 'manual', TRUE, 1.0),
    (2003, 2008, 'Nissan', '350Z', 'Z33', '5x114.3', 66.1, 'M12x1.25', 18, 17, 19, 8.0, 8.0, 10.5, 30, 5, 40, 'manual', TRUE, 1.0),
    (2009, 2020, 'Nissan', '370Z', 'Z34', '5x114.3', 66.1, 'M12x1.25', 18, 18, 20, 9.0, 8.5, 11.0, 30, 5, 40, 'manual', TRUE, 1.0)

ON CONFLICT DO NOTHING;

-- Add trigger to update updated_at
CREATE OR REPLACE FUNCTION update_vehicle_specs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS vehicle_specs_updated_at ON vehicle_specs;
CREATE TRIGGER vehicle_specs_updated_at
    BEFORE UPDATE ON vehicle_specs
    FOR EACH ROW
    EXECUTE FUNCTION update_vehicle_specs_timestamp();
