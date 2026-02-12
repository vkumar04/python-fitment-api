-- Add new columns to kansei_wheels for weight, construction, brake clearance
-- Fix E39 center bore (74.1mm, not 72.6mm)

-- =============================================================================
-- 1. New columns on kansei_wheels
-- =============================================================================

ALTER TABLE kansei_wheels
  ADD COLUMN IF NOT EXISTS barcode TEXT,
  ADD COLUMN IF NOT EXISTS construction TEXT,
  ADD COLUMN IF NOT EXISTS brake_clearance_notes TEXT,
  ADD COLUMN IF NOT EXISTS compare_at_price DECIMAL(10,2);

-- Index on construction for filtering
CREATE INDEX IF NOT EXISTS idx_kansei_construction
  ON kansei_wheels(construction) WHERE construction IS NOT NULL;

-- =============================================================================
-- 2. Fix E39 center bore: 74.1mm (NOT 72.6mm like other 5x120 BMWs)
--    The E39 is the only 5x120 BMW with a 74.1mm hub bore.
--    72.6mm was incorrectly applied from the standard BMW 5x120 bore.
-- =============================================================================

UPDATE vehicle_specs
SET center_bore = 74.1,
    updated_at = NOW()
WHERE chassis_code = 'E39'
  AND center_bore = 72.6;
