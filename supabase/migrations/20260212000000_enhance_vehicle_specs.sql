-- Enhance vehicle_specs table with full fitment data.
-- Remote table currently has: id, make, model, chassis_code, year_start, year_end,
--   bolt_pattern, center_bore, stud_size, notes, created_at, updated_at
-- This adds: trim, OEM sizes (front/rear), tire sizes, brake data, ranges, flags, provenance

-- 1. Add all missing columns
ALTER TABLE vehicle_specs
  ADD COLUMN IF NOT EXISTS trim TEXT,
  ADD COLUMN IF NOT EXISTS oem_diameter DECIMAL(4,1),
  ADD COLUMN IF NOT EXISTS oem_diameter_front DECIMAL(4,1),
  ADD COLUMN IF NOT EXISTS oem_diameter_rear DECIMAL(4,1),
  ADD COLUMN IF NOT EXISTS oem_width DECIMAL(4,1),
  ADD COLUMN IF NOT EXISTS oem_width_front DECIMAL(4,1),
  ADD COLUMN IF NOT EXISTS oem_width_rear DECIMAL(4,1),
  ADD COLUMN IF NOT EXISTS oem_offset INTEGER,
  ADD COLUMN IF NOT EXISTS oem_offset_front INTEGER,
  ADD COLUMN IF NOT EXISTS oem_offset_rear INTEGER,
  ADD COLUMN IF NOT EXISTS oem_tire_front TEXT,
  ADD COLUMN IF NOT EXISTS oem_tire_rear TEXT,
  ADD COLUMN IF NOT EXISTS front_brake_size TEXT,
  ADD COLUMN IF NOT EXISTS min_diameter INTEGER DEFAULT 15,
  ADD COLUMN IF NOT EXISTS max_diameter INTEGER DEFAULT 20,
  ADD COLUMN IF NOT EXISTS min_width DECIMAL(4,1) DEFAULT 6.0,
  ADD COLUMN IF NOT EXISTS max_width DECIMAL(4,1) DEFAULT 10.0,
  ADD COLUMN IF NOT EXISTS min_offset INTEGER DEFAULT -10,
  ADD COLUMN IF NOT EXISTS max_offset INTEGER DEFAULT 50,
  ADD COLUMN IF NOT EXISTS min_wheel_diameter INTEGER,
  ADD COLUMN IF NOT EXISTS is_staggered_stock BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS is_performance_trim BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual',
  ADD COLUMN IF NOT EXISTS source_url TEXT,
  ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS confidence DECIMAL(3,2) DEFAULT 1.0;

-- 2. Create indexes
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_make_model ON vehicle_specs(make, model);
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_chassis ON vehicle_specs(chassis_code) WHERE chassis_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_bolt_pattern ON vehicle_specs(bolt_pattern);
CREATE INDEX IF NOT EXISTS idx_vehicle_specs_year ON vehicle_specs(year_start, year_end);

-- 3. Fix E39 hub bore: all E39 models use 74.1mm (not 72.6mm)
UPDATE vehicle_specs SET center_bore = 74.1 WHERE chassis_code = 'E39';

-- 4. Bulk update existing rows with OEM data by chassis code

-- BMW E30 base (4x100)
UPDATE vehicle_specs SET
  oem_diameter = 14, oem_diameter_front = 14, oem_diameter_rear = 14,
  oem_width = 6.0, oem_width_front = 6.0, oem_width_rear = 6.0,
  oem_offset = 35, oem_offset_front = 35, oem_offset_rear = 35,
  min_diameter = 13, max_diameter = 17, min_width = 6.0, max_width = 8.5,
  min_offset = 15, max_offset = 42
WHERE chassis_code = 'E30' AND bolt_pattern = '4x100';

-- BMW E30 M3 (5x120)
UPDATE vehicle_specs SET
  oem_diameter = 15, oem_diameter_front = 15, oem_diameter_rear = 15,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 25, oem_offset_front = 25, oem_offset_rear = 25,
  oem_tire_front = '205/55R15', oem_tire_rear = '205/55R15',
  front_brake_size = '280mm', min_wheel_diameter = 15,
  min_diameter = 14, max_diameter = 17, min_width = 7.0, max_width = 9.0,
  min_offset = 10, max_offset = 35, is_performance_trim = TRUE
WHERE chassis_code = 'E30' AND bolt_pattern = '5x120';

-- BMW E36
UPDATE vehicle_specs SET
  oem_diameter = 15, oem_diameter_front = 15, oem_diameter_rear = 15,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 35, oem_offset_front = 35, oem_offset_rear = 35,
  min_diameter = 15, max_diameter = 18, min_width = 7.0, max_width = 9.5,
  min_offset = 15, max_offset = 45
WHERE chassis_code = 'E36' AND model NOT IN ('M3');

UPDATE vehicle_specs SET
  oem_diameter = 17, oem_diameter_front = 17, oem_diameter_rear = 17,
  oem_width = 7.5, oem_width_front = 7.5, oem_width_rear = 7.5,
  oem_offset = 41, oem_offset_front = 41, oem_offset_rear = 41,
  oem_tire_front = '225/45R17', oem_tire_rear = '225/45R17',
  front_brake_size = '315mm', min_wheel_diameter = 16,
  min_diameter = 16, max_diameter = 19, min_width = 7.5, max_width = 10.0,
  min_offset = 15, max_offset = 45, is_performance_trim = TRUE
WHERE chassis_code = 'E36' AND model = 'M3';

-- BMW E39 non-M
UPDATE vehicle_specs SET
  oem_diameter = 16, oem_diameter_front = 16, oem_diameter_rear = 16,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 20, oem_offset_front = 20, oem_offset_rear = 20,
  oem_tire_front = '225/55R16', oem_tire_rear = '225/55R16',
  front_brake_size = '296mm', min_wheel_diameter = 16,
  min_diameter = 16, max_diameter = 19, min_width = 7.0, max_width = 9.5,
  min_offset = 10, max_offset = 35
WHERE chassis_code = 'E39' AND model NOT IN ('M5');

-- BMW E39 M5
UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 8.0, oem_width_front = 8.0, oem_width_rear = 9.5,
  oem_offset = 20, oem_offset_front = 20, oem_offset_rear = 22,
  oem_tire_front = '245/40R18', oem_tire_rear = '275/35R18',
  front_brake_size = '345mm', min_wheel_diameter = 18,
  min_diameter = 17, max_diameter = 20, min_width = 8.0, max_width = 10.5,
  min_offset = 5, max_offset = 35,
  is_staggered_stock = TRUE, is_performance_trim = TRUE
WHERE chassis_code = 'E39' AND model = 'M5';

-- BMW E46 non-M
UPDATE vehicle_specs SET
  oem_diameter = 16, oem_diameter_front = 16, oem_diameter_rear = 16,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 42, oem_offset_front = 42, oem_offset_rear = 42,
  min_diameter = 16, max_diameter = 19, min_width = 7.0, max_width = 9.5,
  min_offset = 20, max_offset = 47
WHERE chassis_code = 'E46' AND model NOT IN ('M3');

-- BMW E46 M3
UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 8.0, oem_width_front = 8.0, oem_width_rear = 8.0,
  oem_offset = 47, oem_offset_front = 47, oem_offset_rear = 47,
  oem_tire_front = '225/45R18', oem_tire_rear = '255/40R18',
  front_brake_size = '325mm', min_wheel_diameter = 17,
  min_diameter = 17, max_diameter = 19, min_width = 8.0, max_width = 10.5,
  min_offset = 20, max_offset = 50, is_performance_trim = TRUE
WHERE chassis_code = 'E46' AND model = 'M3';

-- BMW E90/E92
UPDATE vehicle_specs SET
  oem_diameter = 16, oem_diameter_front = 16, oem_diameter_rear = 16,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 34, oem_offset_front = 34, oem_offset_rear = 34,
  min_diameter = 16, max_diameter = 19, min_width = 7.0, max_width = 9.5,
  min_offset = 15, max_offset = 45
WHERE chassis_code IN ('E90', 'E92') AND model NOT IN ('M3');

UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 8.5, oem_width_front = 8.5, oem_width_rear = 9.0,
  oem_offset = 29, oem_offset_front = 29, oem_offset_rear = 32,
  oem_tire_front = '245/35ZR18', oem_tire_rear = '265/35ZR18',
  front_brake_size = '360mm', min_wheel_diameter = 18,
  min_diameter = 18, max_diameter = 20, min_width = 8.5, max_width = 11.0,
  min_offset = 15, max_offset = 45,
  is_staggered_stock = TRUE, is_performance_trim = TRUE
WHERE chassis_code IN ('E90', 'E92') AND model = 'M3';

-- BMW G20/G80 (5x112)
UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 7.5, oem_width_front = 7.5, oem_width_rear = 7.5,
  oem_offset = 30, oem_offset_front = 30, oem_offset_rear = 30,
  oem_tire_front = '225/45R18', oem_tire_rear = '225/45R18',
  front_brake_size = '330mm', min_wheel_diameter = 17,
  min_diameter = 17, max_diameter = 20, min_width = 7.5, max_width = 9.5,
  min_offset = 15, max_offset = 40
WHERE chassis_code = 'G20';

UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 9.0, oem_width_front = 9.0, oem_width_rear = 10.0,
  oem_offset = 23, oem_offset_front = 23, oem_offset_rear = 40,
  oem_tire_front = '275/35ZR18', oem_tire_rear = '285/30ZR19',
  front_brake_size = '380mm', min_wheel_diameter = 18,
  min_diameter = 18, max_diameter = 20, min_width = 8.5, max_width = 11.0,
  min_offset = 10, max_offset = 35,
  is_staggered_stock = TRUE, is_performance_trim = TRUE
WHERE chassis_code = 'G80';

-- 5. Insert new vehicles not in the DB yet

-- BMW F30 3 Series
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2012, 2018, 'BMW', '3 Series', 'F30', '5x120', 72.6, 'M12x1.5', 18, 18, 18, 8.0, 8.0, 8.0, 34, 34, 34, '225/45R18', '225/45R18', '312mm', 17, 20, 7.0, 10.0, 15, 45, 17, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- BMW F80 M3
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, is_staggered_stock, is_performance_trim, source, verified, confidence)
VALUES (2014, 2018, 'BMW', 'M3', 'F80', '5x120', 72.6, 'M12x1.5', 18, 18, 18, 9.0, 9.0, 10.0, 29, 29, 40, '255/35ZR18', '275/35ZR18', '380mm', 18, 20, 8.5, 11.0, 10, 45, 18, TRUE, TRUE, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Honda Civic SI
INSERT INTO vehicle_specs (year_start, year_end, make, model, trim, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, is_performance_trim, source, verified, confidence)
VALUES (2017, 2025, 'Honda', 'Civic', 'SI', '5x114.3', 64.1, 'M12x1.5', 18, 18, 18, 8.0, 8.0, 8.0, 45, 45, 45, '235/40R18', '235/40R18', '300mm', 17, 19, 7.0, 9.5, 30, 50, 17, TRUE, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Honda Civic Type R FL5
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, is_performance_trim, source, verified, confidence)
VALUES (2022, 2025, 'Honda', 'Civic Type R', 'FL5', '5x120', 64.1, 'M14x1.5', 19, 19, 19, 9.5, 9.5, 9.5, 45, 45, 45, '265/30ZR19', '265/30ZR19', '350mm', 18, 20, 8.5, 10.0, 35, 50, 18, TRUE, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Honda Accord
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2008, 2025, 'Honda', 'Accord', '5x114.3', 64.1, 'M12x1.5', 17, 17, 17, 7.5, 7.5, 7.5, 45, 45, 45, '225/50R17', '225/50R17', '282mm', 16, 19, 7.0, 9.5, 30, 50, 16, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Toyota Camry
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2012, 2025, 'Toyota', 'Camry', '5x114.3', 60.1, 'M12x1.5', 17, 17, 17, 7.0, 7.0, 7.0, 40, 40, 40, '215/55R17', '215/55R17', '296mm', 16, 19, 6.5, 9.0, 30, 50, 16, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Toyota Corolla
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2014, 2025, 'Toyota', 'Corolla', '5x114.3', 60.1, 'M12x1.5', 16, 16, 16, 6.5, 6.5, 6.5, 45, 45, 45, '205/55R16', '205/55R16', '275mm', 15, 18, 6.0, 8.5, 30, 50, 15, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Toyota Tacoma
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2005, 2025, 'Toyota', 'Tacoma', '6x139.7', 106.1, 'M12x1.5', 16, 16, 16, 7.0, 7.0, 7.0, 30, 30, 30, '245/75R16', '245/75R16', '319mm', 16, 18, 7.0, 9.0, -10, 30, 16, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Toyota 4Runner
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2010, 2025, 'Toyota', '4Runner', '6x139.7', 106.1, 'M12x1.5', 17, 17, 17, 7.0, 7.0, 7.0, 15, 15, 15, '265/70R17', '265/70R17', '319mm', 17, 18, 7.0, 9.0, -10, 30, 17, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Subaru BRZ 1st gen
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2013, 2020, 'Subaru', 'BRZ', '5x100', 56.1, 'M12x1.25', 17, 17, 17, 7.0, 7.0, 7.0, 48, 48, 48, '215/45R17', '215/45R17', '294mm', 16, 18, 7.0, 9.5, 30, 55, 16, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Subaru BRZ 2nd gen
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2022, 2025, 'Subaru', 'BRZ', '5x114.3', 56.1, 'M12x1.25', 18, 18, 18, 7.5, 7.5, 7.5, 48, 48, 48, '225/40R18', '225/40R18', '294mm', 17, 19, 7.0, 9.5, 30, 55, 17, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Ford Mustang GT S550
INSERT INTO vehicle_specs (year_start, year_end, make, model, trim, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, is_staggered_stock, is_performance_trim, source, verified, confidence)
VALUES (2015, 2025, 'Ford', 'Mustang', 'GT', 'S550', '5x114.3', 70.5, 'M14x1.5', 19, 19, 19, 9.0, 9.0, 9.5, 45, 45, 50, '255/40R19', '275/40R19', '380mm', 18, 20, 8.5, 11.0, 20, 55, 18, TRUE, TRUE, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Ford Mustang base S550
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2015, 2025, 'Ford', 'Mustang', 'S550', '5x114.3', 70.5, 'M14x1.5', 18, 18, 18, 8.5, 8.5, 8.5, 45, 45, 45, '235/50R18', '235/50R18', '330mm', 17, 20, 7.5, 10.0, 20, 55, 17, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Chevrolet Camaro SS
INSERT INTO vehicle_specs (year_start, year_end, make, model, trim, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, is_staggered_stock, is_performance_trim, source, verified, confidence)
VALUES (2016, 2025, 'Chevrolet', 'Camaro', 'SS', 'Alpha', '5x120', 67.1, 'M14x1.5', 20, 20, 20, 8.5, 8.5, 9.5, 32, 32, 30, '245/40R20', '275/35R20', '350mm', 19, 20, 8.0, 10.5, 15, 45, 19, TRUE, TRUE, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Chevrolet Camaro base
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2016, 2025, 'Chevrolet', 'Camaro', 'Alpha', '5x120', 67.1, 'M14x1.5', 18, 18, 18, 8.0, 8.0, 8.0, 35, 35, 35, '245/45R18', '245/45R18', '320mm', 18, 20, 7.5, 10.0, 15, 45, 18, 'manual', TRUE, 0.9)
ON CONFLICT DO NOTHING;

-- VW GTI MK7/MK8
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2015, 2025, 'Volkswagen', 'GTI', 'MK7/MK8', '5x112', 57.1, 'M14x1.5', 18, 18, 18, 7.5, 7.5, 7.5, 49, 49, 49, '225/40R18', '225/40R18', '312mm', 17, 19, 7.0, 9.0, 35, 55, 17, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- VW Golf
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2015, 2025, 'Volkswagen', 'Golf', '5x112', 57.1, 'M14x1.5', 16, 16, 16, 6.5, 6.5, 6.5, 46, 46, 46, '205/55R16', '205/55R16', '288mm', 15, 19, 6.0, 9.0, 30, 55, 15, 'manual', TRUE, 0.9)
ON CONFLICT DO NOTHING;

-- Mazda MX-5 Miata ND
INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2016, 2025, 'Mazda', 'MX-5 Miata', 'ND', '5x114.3', 67.1, 'M12x1.5', 16, 16, 16, 6.5, 6.5, 6.5, 50, 50, 50, '195/50R16', '195/50R16', '280mm', 16, 17, 6.0, 8.0, 35, 55, 16, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Hyundai Elantra base
INSERT INTO vehicle_specs (year_start, year_end, make, model, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, source, verified, confidence)
VALUES (2017, 2025, 'Hyundai', 'Elantra', '5x114.3', 67.1, 'M12x1.5', 16, 16, 16, 6.5, 6.5, 6.5, 45, 45, 45, '205/55R16', '205/55R16', '280mm', 15, 19, 6.0, 8.5, 30, 50, 15, 'manual', TRUE, 0.9)
ON CONFLICT DO NOTHING;

-- Hyundai Elantra N
INSERT INTO vehicle_specs (year_start, year_end, make, model, trim, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, oem_diameter_front, oem_diameter_rear, oem_width, oem_width_front, oem_width_rear, oem_offset, oem_offset_front, oem_offset_rear, oem_tire_front, oem_tire_rear, front_brake_size, min_diameter, max_diameter, min_width, max_width, min_offset, max_offset, min_wheel_diameter, is_performance_trim, source, verified, confidence)
VALUES (2022, 2025, 'Hyundai', 'Elantra', 'N', 'CN7', '5x114.3', 67.1, 'M12x1.5', 19, 19, 19, 8.0, 8.0, 8.0, 40, 40, 40, '245/35R19', '245/35R19', '345mm', 18, 19, 7.5, 9.5, 25, 50, 18, TRUE, 'manual', TRUE, 1.0)
ON CONFLICT DO NOTHING;

-- Nissan 370Z (update existing)
UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 8.0, oem_width_front = 8.0, oem_width_rear = 9.0,
  oem_offset = 30, oem_offset_front = 30, oem_offset_rear = 30,
  oem_tire_front = '225/45R18', oem_tire_rear = '245/45R18',
  front_brake_size = '320mm', min_wheel_diameter = 18,
  min_diameter = 18, max_diameter = 20, min_width = 8.5, max_width = 11.0,
  min_offset = 5, max_offset = 40,
  is_staggered_stock = TRUE
WHERE chassis_code = 'Z34';

-- Nissan 350Z (update existing)
UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 8.0, oem_width_front = 8.0, oem_width_rear = 8.0,
  oem_offset = 30, oem_offset_front = 30, oem_offset_rear = 30,
  oem_tire_front = '225/45R18', oem_tire_rear = '245/45R18',
  front_brake_size = '324mm', min_wheel_diameter = 17,
  min_diameter = 17, max_diameter = 19, min_width = 8.0, max_width = 10.5,
  min_offset = 5, max_offset = 40
WHERE chassis_code = 'Z33';

-- Nissan 240SX S13/S14 (update existing)
UPDATE vehicle_specs SET
  oem_diameter = 15, oem_diameter_front = 15, oem_diameter_rear = 15,
  oem_width = 6.0, oem_width_front = 6.0, oem_width_rear = 6.0,
  oem_offset = 40, oem_offset_front = 40, oem_offset_rear = 40,
  min_diameter = 15, max_diameter = 18, min_width = 7.0, max_width = 9.5,
  min_offset = 0, max_offset = 30
WHERE chassis_code = 'S13';

UPDATE vehicle_specs SET
  oem_diameter = 16, oem_diameter_front = 16, oem_diameter_rear = 16,
  oem_width = 6.5, oem_width_front = 6.5, oem_width_rear = 6.5,
  oem_offset = 40, oem_offset_front = 40, oem_offset_rear = 40,
  min_diameter = 16, max_diameter = 18, min_width = 7.0, max_width = 9.5,
  min_offset = 0, max_offset = 35
WHERE chassis_code = 'S14';

-- Toyota 86 / Scion FR-S / Subaru BRZ (update existing ZN6)
UPDATE vehicle_specs SET
  oem_diameter = 17, oem_diameter_front = 17, oem_diameter_rear = 17,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 48, oem_offset_front = 48, oem_offset_rear = 48,
  oem_tire_front = '215/45R17', oem_tire_rear = '215/45R17',
  front_brake_size = '294mm', min_wheel_diameter = 16,
  min_diameter = 17, max_diameter = 18, min_width = 7.0, max_width = 9.5,
  min_offset = 30, max_offset = 55
WHERE chassis_code = 'ZN6';

-- Toyota GR86 (update existing ZN8)
UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 7.5, oem_width_front = 7.5, oem_width_rear = 7.5,
  oem_offset = 48, oem_offset_front = 48, oem_offset_rear = 48,
  oem_tire_front = '225/40R18', oem_tire_rear = '225/40R18',
  front_brake_size = '294mm', min_wheel_diameter = 17,
  min_diameter = 17, max_diameter = 19, min_width = 7.0, max_width = 9.5,
  min_offset = 30, max_offset = 55
WHERE chassis_code = 'ZN8';

-- Toyota GR Supra (update existing A90)
UPDATE vehicle_specs SET
  oem_diameter = 19, oem_diameter_front = 19, oem_diameter_rear = 19,
  oem_width = 9.0, oem_width_front = 9.0, oem_width_rear = 10.0,
  oem_offset = 32, oem_offset_front = 32, oem_offset_rear = 40,
  oem_tire_front = '255/35ZR19', oem_tire_rear = '275/35ZR19',
  front_brake_size = '348mm', min_wheel_diameter = 18,
  min_diameter = 18, max_diameter = 20, min_width = 8.5, max_width = 10.5,
  min_offset = 15, max_offset = 40,
  is_staggered_stock = TRUE, is_performance_trim = TRUE
WHERE chassis_code = 'A90';

-- Mazda Miata NA/NB (update existing)
UPDATE vehicle_specs SET
  oem_diameter = 14, oem_diameter_front = 14, oem_diameter_rear = 14,
  oem_width = 5.5, oem_width_front = 5.5, oem_width_rear = 5.5,
  oem_offset = 45, oem_offset_front = 45, oem_offset_rear = 45,
  min_diameter = 14, max_diameter = 16, min_width = 6.0, max_width = 8.0,
  min_offset = 25, max_offset = 50
WHERE chassis_code = 'NA';

UPDATE vehicle_specs SET
  oem_diameter = 15, oem_diameter_front = 15, oem_diameter_rear = 15,
  oem_width = 6.0, oem_width_front = 6.0, oem_width_rear = 6.0,
  oem_offset = 40, oem_offset_front = 40, oem_offset_rear = 40,
  min_diameter = 14, max_diameter = 17, min_width = 6.0, max_width = 8.0,
  min_offset = 20, max_offset = 45
WHERE chassis_code = 'NB';

-- Mazda MX-5 NC/ND (update existing)
UPDATE vehicle_specs SET
  oem_diameter = 17, oem_diameter_front = 17, oem_diameter_rear = 17,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 50, oem_offset_front = 50, oem_offset_rear = 50,
  oem_tire_front = '205/45R17', oem_tire_rear = '205/45R17',
  front_brake_size = '290mm', min_wheel_diameter = 16,
  min_diameter = 16, max_diameter = 18, min_width = 6.5, max_width = 8.5,
  min_offset = 30, max_offset = 55
WHERE chassis_code = 'NC';

UPDATE vehicle_specs SET
  oem_diameter = 16, oem_diameter_front = 16, oem_diameter_rear = 16,
  oem_width = 6.5, oem_width_front = 6.5, oem_width_rear = 6.5,
  oem_offset = 50, oem_offset_front = 50, oem_offset_rear = 50,
  oem_tire_front = '195/50R16', oem_tire_rear = '195/50R16',
  front_brake_size = '280mm', min_wheel_diameter = 16,
  min_diameter = 16, max_diameter = 17, min_width = 6.5, max_width = 8.0,
  min_offset = 35, max_offset = 55
WHERE chassis_code = 'ND';

-- Honda Civic (update existing by chassis code)
UPDATE vehicle_specs SET
  oem_diameter = 14, oem_diameter_front = 14, oem_diameter_rear = 14,
  oem_width = 5.5, oem_width_front = 5.5, oem_width_rear = 5.5,
  oem_offset = 45, oem_offset_front = 45, oem_offset_rear = 45,
  min_diameter = 14, max_diameter = 17, min_width = 6.0, max_width = 8.0,
  min_offset = 25, max_offset = 50
WHERE make = 'Honda' AND model = 'Civic' AND chassis_code IN ('EG', 'EK');

UPDATE vehicle_specs SET
  oem_diameter = 16, oem_diameter_front = 16, oem_diameter_rear = 16,
  oem_width = 6.5, oem_width_front = 6.5, oem_width_rear = 6.5,
  oem_offset = 45, oem_offset_front = 45, oem_offset_rear = 45,
  oem_tire_front = '205/55R16', oem_tire_rear = '205/55R16',
  front_brake_size = '282mm', min_wheel_diameter = 16,
  min_diameter = 16, max_diameter = 18, min_width = 7.0, max_width = 9.0,
  min_offset = 30, max_offset = 50
WHERE make = 'Honda' AND model = 'Civic' AND chassis_code = 'FG/FA';

UPDATE vehicle_specs SET
  oem_diameter = 16, oem_diameter_front = 16, oem_diameter_rear = 16,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 45, oem_offset_front = 45, oem_offset_rear = 45,
  oem_tire_front = '205/55R16', oem_tire_rear = '205/55R16',
  front_brake_size = '282mm', min_wheel_diameter = 16,
  min_diameter = 16, max_diameter = 19, min_width = 7.0, max_width = 9.5,
  min_offset = 30, max_offset = 50
WHERE make = 'Honda' AND model = 'Civic' AND chassis_code = 'FC/FK';

UPDATE vehicle_specs SET
  oem_diameter = 20, oem_diameter_front = 20, oem_diameter_rear = 20,
  oem_width = 8.5, oem_width_front = 8.5, oem_width_rear = 8.5,
  oem_offset = 60, oem_offset_front = 60, oem_offset_rear = 60,
  oem_tire_front = '245/30ZR20', oem_tire_rear = '245/30ZR20',
  front_brake_size = '350mm', min_wheel_diameter = 18,
  min_diameter = 18, max_diameter = 20, min_width = 8.5, max_width = 10.0,
  min_offset = 35, max_offset = 50,
  is_performance_trim = TRUE
WHERE make = 'Honda' AND model = 'Civic Type R' AND chassis_code = 'FK8';

UPDATE vehicle_specs SET
  oem_diameter = 17, oem_diameter_front = 17, oem_diameter_rear = 17,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 45, oem_offset_front = 45, oem_offset_rear = 45,
  oem_tire_front = '215/50R17', oem_tire_rear = '215/50R17',
  front_brake_size = '282mm', min_wheel_diameter = 17,
  min_diameter = 17, max_diameter = 19, min_width = 7.0, max_width = 9.5,
  min_offset = 30, max_offset = 50
WHERE make = 'Honda' AND model = 'Civic' AND chassis_code = 'FL';

-- Subaru WRX/STI (update existing)
UPDATE vehicle_specs SET
  oem_diameter = 17, oem_diameter_front = 17, oem_diameter_rear = 17,
  oem_width = 7.0, oem_width_front = 7.0, oem_width_rear = 7.0,
  oem_offset = 48, oem_offset_front = 48, oem_offset_rear = 48,
  oem_tire_front = '225/45R17', oem_tire_rear = '225/45R17',
  front_brake_size = '292mm', min_wheel_diameter = 16,
  min_diameter = 16, max_diameter = 18, min_width = 7.0, max_width = 9.0,
  min_offset = 30, max_offset = 55
WHERE make = 'Subaru' AND model = 'WRX' AND chassis_code = 'GD/GR';

UPDATE vehicle_specs SET
  oem_diameter = 18, oem_diameter_front = 18, oem_diameter_rear = 18,
  oem_width = 8.5, oem_width_front = 8.5, oem_width_rear = 8.5,
  oem_offset = 55, oem_offset_front = 55, oem_offset_rear = 55,
  oem_tire_front = '245/40R18', oem_tire_rear = '245/40R18',
  front_brake_size = '340mm', min_wheel_diameter = 17,
  min_diameter = 17, max_diameter = 19, min_width = 8.0, max_width = 10.0,
  min_offset = 30, max_offset = 55,
  is_performance_trim = TRUE
WHERE make = 'Subaru' AND model = 'WRX STI' AND chassis_code = 'GD/GR';

UPDATE vehicle_specs SET
  oem_diameter = 17, oem_diameter_front = 17, oem_diameter_rear = 17,
  oem_width = 8.0, oem_width_front = 8.0, oem_width_rear = 8.0,
  oem_offset = 48, oem_offset_front = 48, oem_offset_rear = 48,
  oem_tire_front = '235/45R17', oem_tire_rear = '235/45R17',
  front_brake_size = '300mm', min_wheel_diameter = 17,
  min_diameter = 17, max_diameter = 19, min_width = 7.5, max_width = 9.5,
  min_offset = 30, max_offset = 55
WHERE make = 'Subaru' AND model = 'WRX' AND chassis_code = 'VA';

UPDATE vehicle_specs SET
  oem_diameter = 19, oem_diameter_front = 19, oem_diameter_rear = 19,
  oem_width = 8.5, oem_width_front = 8.5, oem_width_rear = 8.5,
  oem_offset = 55, oem_offset_front = 55, oem_offset_rear = 55,
  oem_tire_front = '245/35R19', oem_tire_rear = '245/35R19',
  front_brake_size = '340mm', min_wheel_diameter = 18,
  min_diameter = 18, max_diameter = 19, min_width = 8.0, max_width = 10.0,
  min_offset = 30, max_offset = 55,
  is_performance_trim = TRUE
WHERE make = 'Subaru' AND model = 'WRX STI' AND chassis_code = 'VA';

-- 6. Update the find_vehicle_specs function to return new fields and support trim
DROP FUNCTION IF EXISTS find_vehicle_specs(INTEGER, TEXT, TEXT, TEXT);

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
    -- Exact trim match first
    CASE WHEN p_trim IS NOT NULL AND LOWER(vs."trim") = LOWER(p_trim) THEN 0
         WHEN vs."trim" IS NULL THEN 1
         ELSE 2 END,
    -- Chassis code match
    CASE WHEN p_chassis_code IS NOT NULL AND UPPER(vs.chassis_code) = UPPER(p_chassis_code) THEN 0 ELSE 1 END,
    -- Verified first
    CASE WHEN vs.verified THEN 0 ELSE 1 END,
    vs.confidence DESC,
    -- Narrower year range = more specific
    COALESCE(vs.year_end, 2030) - COALESCE(vs.year_start, 1950) ASC
  LIMIT 5;
END;
$$;
