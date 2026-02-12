-- Add center_bore column to kansei_wheels
-- Bore varies by product line:
--   Street wheels (4x, 5x bolt patterns): 73.1mm
--   Off-road 6x139.7: 106.1mm
--   Off-road 5x150 (Tundra/LC): 110.3mm

ALTER TABLE kansei_wheels
  ADD COLUMN IF NOT EXISTS center_bore DECIMAL(5,1) NOT NULL DEFAULT 73.1;

-- Populate off-road bores based on bolt pattern
UPDATE kansei_wheels SET center_bore = 106.1
  WHERE bolt_pattern = '6X139.7';

UPDATE kansei_wheels SET center_bore = 110.3
  WHERE bolt_pattern = '5X150';
