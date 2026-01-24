-- Kansei wheels catalog table
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
    in_stock BOOLEAN DEFAULT true,
    weight DECIMAL(5,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_kansei_bolt_pattern ON kansei_wheels(bolt_pattern);
CREATE INDEX IF NOT EXISTS idx_kansei_diameter ON kansei_wheels(diameter);
CREATE INDEX IF NOT EXISTS idx_kansei_model ON kansei_wheels(model);

-- Function to find matching Kansei wheels
CREATE OR REPLACE FUNCTION find_kansei_wheels(
    p_bolt_pattern TEXT,
    p_diameter DECIMAL DEFAULT NULL,
    p_width DECIMAL DEFAULT NULL,
    p_offset INTEGER DEFAULT NULL,
    p_offset_tolerance INTEGER DEFAULT 10,
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    id INTEGER,
    model TEXT,
    finish TEXT,
    sku TEXT,
    diameter DECIMAL,
    width DECIMAL,
    bolt_pattern TEXT,
    wheel_offset INTEGER,
    price DECIMAL,
    category TEXT,
    url TEXT,
    in_stock BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        kw.id,
        kw.model,
        kw.finish,
        kw.sku,
        kw.diameter,
        kw.width,
        kw.bolt_pattern,
        kw.wheel_offset,
        kw.price,
        kw.category,
        kw.url,
        kw.in_stock
    FROM kansei_wheels kw
    WHERE UPPER(kw.bolt_pattern) = UPPER(p_bolt_pattern)
        AND (p_diameter IS NULL OR kw.diameter = p_diameter)
        AND (p_width IS NULL OR ABS(kw.width - p_width) <= 0.5)
        AND (p_offset IS NULL OR ABS(kw.wheel_offset - p_offset) <= p_offset_tolerance)
    ORDER BY kw.model, kw.price
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Table for user-contributed/LLM-generated fitments (needs review)
CREATE TABLE IF NOT EXISTS fitments_pending (
    id SERIAL PRIMARY KEY,
    year INTEGER,
    make TEXT,
    model TEXT,
    trim TEXT,
    front_diameter DECIMAL(4,1),
    front_width DECIMAL(4,1),
    front_offset INTEGER,
    rear_diameter DECIMAL(4,1),
    rear_width DECIMAL(4,1),
    rear_offset INTEGER,
    tire_front TEXT,
    tire_rear TEXT,
    bolt_pattern TEXT,
    fitment_style TEXT,
    source TEXT DEFAULT 'llm_generated',
    notes TEXT,
    reviewed BOOLEAN DEFAULT false,
    approved BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_reviewed ON fitments_pending(reviewed);
CREATE INDEX IF NOT EXISTS idx_pending_make_model ON fitments_pending(make, model);
