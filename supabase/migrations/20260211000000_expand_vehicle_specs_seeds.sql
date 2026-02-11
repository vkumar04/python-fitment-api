-- =============================================================================
-- Expand vehicle_specs seed data
-- Adds verified specs for vehicles tested in test_bolt_patterns.py that were
-- previously only covered by the hardcoded Python knowledge base.
-- =============================================================================

INSERT INTO vehicle_specs (year_start, year_end, make, model, chassis_code, bolt_pattern, center_bore, stud_size, oem_diameter, min_diameter, max_diameter, oem_width, min_width, max_width, oem_offset, min_offset, max_offset, source, verified, confidence)
VALUES
  -- Honda/Acura
  (2015, 2020, 'Honda', 'Civic Si',  'FC', '5x114.3', 64.1, 'M12x1.5', 18, 17, 19, 8.0, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),
  (2018, 2022, 'Honda', 'Accord',    NULL, '5x114.3', 64.1, 'M12x1.5', 17, 17, 19, 7.5, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),
  (2021, NULL, 'Acura', 'TLX',       NULL, '5x114.3', 64.1, 'M14x1.5', 19, 18, 20, 8.5, 8.0, 10.0, 45, 30, 50, 'manual', TRUE, 1.0),
  (2017, 2022, 'Acura', 'NSX',       NULL, '5x120',   64.1, 'M14x1.5', 19, 19, 20, 8.5, 8.0, 10.0, 50, 30, 55, 'manual', TRUE, 1.0),
  (2022, NULL, 'Honda', 'Civic Type R', 'FL5', '5x120', 64.1, 'M14x1.5', 19, 18, 20, 9.5, 8.5, 10.5, 45, 35, 50, 'manual', TRUE, 1.0),

  -- Toyota/Lexus
  (2018, NULL, 'Toyota', 'Camry',       NULL, '5x114.3', 60.1, 'M12x1.5', 17, 16, 19, 7.0, 7.0, 9.0, 40, 25, 50, 'manual', TRUE, 1.0),
  (2023, NULL, 'Toyota', 'GR Corolla',  NULL, '5x114.3', 64.1, 'M12x1.5', 18, 18, 19, 8.0, 8.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),
  (2014, NULL, 'Lexus',  'IS350',       NULL, '5x114.3', 60.1, 'M12x1.5', 18, 17, 20, 8.0, 7.5, 10.0, 40, 25, 50, 'manual', TRUE, 1.0),

  -- Nissan/Infiniti
  (2023, NULL, 'Nissan',   'Z',     'Z35', '5x114.3', 66.1, 'M12x1.25', 19, 18, 20, 9.0, 8.5, 10.5, 30, 10, 40, 'manual', TRUE, 1.0),
  (2009, NULL, 'Nissan',   'GT-R',  'R35', '5x114.3', 66.1, 'M12x1.25', 20, 19, 21, 9.5, 9.0, 11.0, 45, 20, 50, 'manual', TRUE, 1.0),
  (2017, 2022, 'Infiniti', 'Q60',   NULL,  '5x114.3', 66.1, 'M14x1.5',  19, 18, 20, 9.0, 8.0, 10.5, 40, 20, 50, 'manual', TRUE, 1.0),

  -- Subaru
  (2013, 2020, 'Subaru', 'BRZ',    'ZC6', '5x100',   56.1, 'M12x1.25', 17, 17, 18, 7.0, 7.0, 9.5, 48, 30, 55, 'manual', TRUE, 1.0),

  -- Mazda
  (2019, NULL, 'Mazda', 'Mazda3',    NULL, '5x114.3', 67.1, 'M12x1.5', 18, 17, 19, 7.0, 7.0, 9.0, 45, 30, 50, 'manual', TRUE, 1.0),
  -- ND Miata with 4x100 (test uses 2019 MX-5 expecting 4x100)
  -- Already covered by ND seed in consolidated migration

  -- Mitsubishi
  (2008, 2015, 'Mitsubishi', 'Lancer Evolution', NULL, '5x114.3', 67.1, 'M12x1.5', 18, 17, 19, 8.5, 8.0, 10.0, 38, 15, 45, 'manual', TRUE, 1.0),

  -- BMW (fill gaps in year-based test queries)
  (2014, 2020, 'BMW', 'M4',    'F82', '5x120', 72.6, 'M12x1.5', 18, 18, 20, 9.0, 8.5, 10.5, 29, 15, 40, 'manual', TRUE, 1.0),
  (2021, NULL, 'BMW', 'M4',    'G82', '5x112', 66.5, 'M14x1.25', 18, 18, 20, 9.0, 8.5, 11.0, 23, 10, 35, 'manual', TRUE, 1.0),
  (1983, 1989, 'BMW', 'M6',    'E24', '5x120', 72.6, 'M12x1.5', 14, 14, 17, 6.5, 6.5, 9.0, 23, 5, 35, 'manual', TRUE, 1.0),
  (2016, 2018, 'BMW', '340i',  'F30', '5x120', 72.6, 'M12x1.5', 18, 17, 20, 8.0, 7.5, 10.0, 34, 15, 45, 'manual', TRUE, 1.0),

  -- German — Mercedes/Audi/VW/Porsche
  (2015, NULL, 'Mercedes-Benz', 'C63 AMG', NULL, '5x112', 66.6, 'M14x1.5', 19, 18, 20, 8.5, 8.0, 10.5, 43, 25, 50, 'manual', TRUE, 1.0),
  (2017, NULL, 'Mercedes-Benz', 'E350',    NULL, '5x112', 66.6, 'M14x1.5', 18, 17, 20, 8.0, 7.5, 10.0, 43, 25, 50, 'manual', TRUE, 1.0),
  (2018, NULL, 'Audi', 'RS5',    NULL, '5x112', 66.5, 'M14x1.5', 19, 18, 20, 9.0, 8.0, 10.5, 35, 20, 45, 'manual', TRUE, 1.0),
  (2017, NULL, 'Audi', 'S4',     NULL, '5x112', 66.5, 'M14x1.5', 19, 18, 20, 8.5, 8.0, 10.0, 35, 20, 45, 'manual', TRUE, 1.0),
  (2015, NULL, 'Volkswagen', 'Golf R', NULL, '5x112', 57.1, 'M14x1.5', 19, 17, 20, 7.5, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),
  (2015, NULL, 'Volkswagen', 'GTI',    NULL, '5x112', 57.1, 'M14x1.5', 18, 17, 19, 7.5, 7.0, 9.5, 45, 30, 50, 'manual', TRUE, 1.0),
  (2012, NULL, 'Porsche', '911',    '991/992', '5x130', 71.6, 'M14x1.5', 20, 19, 21, 9.0, 8.5, 11.0, 50, 30, 60, 'manual', TRUE, 1.0),
  (2016, NULL, 'Porsche', 'Cayman', '982',     '5x130', 71.6, 'M14x1.5', 19, 18, 20, 8.0, 8.0, 10.0, 50, 30, 60, 'manual', TRUE, 1.0),

  -- American — Ford
  (2015, NULL, 'Ford', 'Mustang GT',  'S550', '5x114.3', 70.5, 'M14x1.5', 19, 17, 20, 9.0, 8.0, 11.0, 45, 20, 55, 'manual', TRUE, 1.0),
  (2015, NULL, 'Ford', 'F-150',       NULL,   '6x135',   87.1, 'M14x1.5', 17, 17, 22, 7.5, 7.5, 10.0, 44, -12, 50, 'manual', TRUE, 1.0),
  (2016, 2018, 'Ford', 'Focus RS',   NULL,   '5x108',   63.4, 'M12x1.5', 19, 18, 19, 8.0, 7.5, 9.0, 50, 35, 55, 'manual', TRUE, 1.0),

  -- American — Chevy/Dodge
  (2016, NULL, 'Chevrolet', 'Camaro SS',    NULL, '5x120', 67.1, 'M14x1.5', 20, 18, 20, 8.5, 8.0, 11.0, 35, 15, 45, 'manual', TRUE, 1.0),
  (2020, NULL, 'Chevrolet', 'Corvette C8',  NULL, '5x120', 70.3, 'M14x1.5', 19, 18, 21, 8.5, 8.5, 12.0, 30, 15, 50, 'manual', TRUE, 1.0),
  (2014, NULL, 'Chevrolet', 'Silverado',    NULL, '6x139.7', 78.1, 'M14x1.5', 17, 17, 22, 7.5, 7.5, 10.0, 28, -12, 44, 'manual', TRUE, 1.0),
  (2015, NULL, 'Dodge', 'Challenger', NULL, '5x115', 71.5, 'M14x1.5', 18, 18, 22, 7.5, 7.5, 11.0, 20, 5, 35, 'manual', TRUE, 1.0),
  (2015, NULL, 'Dodge', 'Charger',    NULL, '5x115', 71.5, 'M14x1.5', 18, 18, 22, 7.5, 7.5, 11.0, 20, 5, 35, 'manual', TRUE, 1.0),

  -- Electric — Tesla
  (2017, NULL, 'Tesla', 'Model 3', NULL, '5x114.3', 64.1, 'M14x1.5', 18, 18, 20, 8.5, 8.0, 10.0, 35, 20, 45, 'manual', TRUE, 1.0),
  (2012, NULL, 'Tesla', 'Model S', NULL, '5x120',   64.1, 'M14x1.5', 19, 19, 21, 8.5, 8.5, 10.5, 40, 25, 50, 'manual', TRUE, 1.0),
  (2020, NULL, 'Tesla', 'Model Y', NULL, '5x114.3', 64.1, 'M14x1.5', 19, 18, 21, 9.5, 8.5, 10.5, 35, 20, 45, 'manual', TRUE, 1.0)

ON CONFLICT DO NOTHING;
