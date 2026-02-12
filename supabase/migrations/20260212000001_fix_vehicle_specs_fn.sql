-- Fix find_vehicle_specs function: cast varchar columns to TEXT to match RETURNS TABLE
DROP FUNCTION IF EXISTS find_vehicle_specs(INTEGER, TEXT, TEXT, TEXT, TEXT);

CREATE OR REPLACE FUNCTION find_vehicle_specs(
  p_year INTEGER DEFAULT NULL,
  p_make TEXT DEFAULT NULL,
  p_model TEXT DEFAULT NULL,
  p_chassis_code TEXT DEFAULT NULL,
  p_trim TEXT DEFAULT NULL
)
RETURNS TABLE (
  id INTEGER,
  year_start INTEGER,
  year_end INTEGER,
  make TEXT,
  model TEXT,
  chassis_code TEXT,
  "trim" TEXT,
  bolt_pattern TEXT,
  center_bore DECIMAL,
  stud_size TEXT,
  oem_diameter DECIMAL,
  oem_diameter_front DECIMAL,
  oem_diameter_rear DECIMAL,
  min_diameter INTEGER,
  max_diameter INTEGER,
  oem_width DECIMAL,
  oem_width_front DECIMAL,
  oem_width_rear DECIMAL,
  min_width DECIMAL,
  max_width DECIMAL,
  oem_offset INTEGER,
  oem_offset_front INTEGER,
  oem_offset_rear INTEGER,
  min_offset INTEGER,
  max_offset INTEGER,
  oem_tire_front TEXT,
  oem_tire_rear TEXT,
  front_brake_size TEXT,
  min_wheel_diameter INTEGER,
  is_staggered_stock BOOLEAN,
  is_performance_trim BOOLEAN,
  source TEXT,
  verified BOOLEAN,
  confidence DECIMAL
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    vs.id, vs.year_start, vs.year_end,
    vs.make::TEXT, vs.model::TEXT,
    vs.chassis_code::TEXT, vs."trim"::TEXT,
    vs.bolt_pattern::TEXT, vs.center_bore, vs.stud_size::TEXT,
    vs.oem_diameter,
    vs.oem_diameter_front, vs.oem_diameter_rear,
    vs.min_diameter, vs.max_diameter,
    vs.oem_width,
    vs.oem_width_front, vs.oem_width_rear,
    vs.min_width, vs.max_width,
    vs.oem_offset,
    vs.oem_offset_front, vs.oem_offset_rear,
    vs.min_offset, vs.max_offset,
    vs.oem_tire_front::TEXT, vs.oem_tire_rear::TEXT,
    vs.front_brake_size::TEXT, vs.min_wheel_diameter,
    vs.is_staggered_stock, vs.is_performance_trim,
    vs.source::TEXT, vs.verified, vs.confidence
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
    CASE WHEN p_trim IS NOT NULL AND LOWER(vs."trim") = LOWER(p_trim) THEN 0
         WHEN vs."trim" IS NULL THEN 1
         ELSE 2 END,
    CASE WHEN p_chassis_code IS NOT NULL AND UPPER(vs.chassis_code) = UPPER(p_chassis_code) THEN 0 ELSE 1 END,
    CASE WHEN vs.verified THEN 0 ELSE 1 END,
    vs.confidence DESC,
    COALESCE(vs.year_end, 2030) - COALESCE(vs.year_start, 1950) ASC
  LIMIT 5;
END;
$$;
