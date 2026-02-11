"""Verified OEM vehicle specifications registry.

This is the deterministic source of truth for OEM wheel specs used in fitment
calculations. Every entry is manually verified. The LLM is NEVER used for these
values because incorrect OEM specs produce wrong poke/clearance calculations
and dangerous "no mods needed" claims.

Lookup priority:
  1. (make, model, chassis_code)   — most specific
  2. (make, model) with year range — year-matched fallback
  3. None                          — unknown vehicle, conservative defaults used
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Type alias for OEM spec entries
# ---------------------------------------------------------------------------
OEMEntry = dict[str, Any]

# ---------------------------------------------------------------------------
# Verified OEM Specs Registry
#
# Key: (make, model, chassis_code | None)
# Each entry must include at minimum:
#   oem_diameter, oem_width, oem_offset, is_staggered_stock,
#   min_brake_clearance_diameter
#
# For staggered-stock vehicles, also include:
#   oem_rear_width, oem_rear_offset
#
# Source: DB seed migrations + manual verification
# ---------------------------------------------------------------------------

OEM_SPECS: dict[tuple[str, str, str | None], OEMEntry] = {
    # =========================================================================
    # BMW E30
    # =========================================================================
    ("BMW", "318i", "E30"): {
        "oem_diameter": 14,
        "oem_width": 6.0,
        "oem_offset": 35,
        "oem_rear_width": 6.0,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 13,
        "year_start": 1982,
        "year_end": 1994,
    },
    ("BMW", "325i", "E30"): {
        "oem_diameter": 14,
        "oem_width": 6.5,
        "oem_offset": 35,
        "oem_rear_width": 6.5,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 13,
        "year_start": 1982,
        "year_end": 1994,
    },
    ("BMW", "M3", "E30"): {
        "oem_diameter": 15,
        "oem_width": 7.0,
        "oem_offset": 25,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 25,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "oem_tire_front": "205/55R15",
        "oem_tire_rear": "205/55R15",
        "year_start": 1986,
        "year_end": 1991,
    },
    # =========================================================================
    # BMW E36
    # =========================================================================
    ("BMW", "318i", "E36"): {
        "oem_diameter": 15,
        "oem_width": 7.0,
        "oem_offset": 35,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 1992,
        "year_end": 1999,
    },
    ("BMW", "325i", "E36"): {
        "oem_diameter": 15,
        "oem_width": 7.0,
        "oem_offset": 35,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 1992,
        "year_end": 1999,
    },
    ("BMW", "328i", "E36"): {
        "oem_diameter": 16,
        "oem_width": 7.5,
        "oem_offset": 35,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 1992,
        "year_end": 1999,
    },
    ("BMW", "M3", "E36"): {
        "oem_diameter": 17,
        "oem_width": 7.5,
        "oem_offset": 41,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 41,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "oem_tire_front": "225/45R17",
        "oem_tire_rear": "225/45R17",
        "year_start": 1995,
        "year_end": 1999,
    },
    # =========================================================================
    # BMW E39
    # =========================================================================
    ("BMW", "525i", "E39"): {
        "oem_diameter": 16,
        "oem_width": 7.0,
        "oem_offset": 20,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 20,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 1996,
        "year_end": 2003,
    },
    ("BMW", "528i", "E39"): {
        "oem_diameter": 16,
        "oem_width": 7.0,
        "oem_offset": 20,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 20,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 1996,
        "year_end": 2003,
    },
    ("BMW", "530i", "E39"): {
        "oem_diameter": 17,
        "oem_width": 8.0,
        "oem_offset": 20,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 20,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 1996,
        "year_end": 2003,
    },
    ("BMW", "540i", "E39"): {
        "oem_diameter": 17,
        "oem_width": 8.0,
        "oem_offset": 20,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 20,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 1996,
        "year_end": 2003,
    },
    ("BMW", "M5", "E39"): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 20,
        "oem_rear_width": 9.5,
        "oem_rear_offset": 22,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "oem_tire_front": "245/40R18",
        "oem_tire_rear": "275/35R18",
        "year_start": 1998,
        "year_end": 2003,
    },
    # =========================================================================
    # BMW E46
    # =========================================================================
    ("BMW", "323i", "E46"): {
        "oem_diameter": 16,
        "oem_width": 7.0,
        "oem_offset": 42,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 42,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 1999,
        "year_end": 2006,
    },
    ("BMW", "325i", "E46"): {
        "oem_diameter": 16,
        "oem_width": 7.0,
        "oem_offset": 42,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 42,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 1999,
        "year_end": 2006,
    },
    ("BMW", "328i", "E46"): {
        "oem_diameter": 16,
        "oem_width": 7.0,
        "oem_offset": 42,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 42,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 1999,
        "year_end": 2006,
    },
    ("BMW", "330i", "E46"): {
        "oem_diameter": 17,
        "oem_width": 7.5,
        "oem_offset": 42,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 42,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 1999,
        "year_end": 2006,
    },
    ("BMW", "M3", "E46"): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 47,
        "oem_rear_width": 9.0,
        "oem_rear_offset": 26,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "oem_tire_front": "225/45R18",
        "oem_tire_rear": "255/40R18",
        "year_start": 2001,
        "year_end": 2006,
    },
    # =========================================================================
    # BMW G-series (5x112)
    # =========================================================================
    ("BMW", "330i", "G20"): {
        "oem_diameter": 18,
        "oem_width": 7.5,
        "oem_offset": 30,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 30,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2019,
        "year_end": None,
    },
    ("BMW", "M340i", "G20"): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 30,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 30,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2019,
        "year_end": None,
    },
    ("BMW", "M3", "G80"): {
        "oem_diameter": 18,
        "oem_width": 9.0,
        "oem_offset": 23,
        "oem_rear_width": 10.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "oem_tire_front": "275/40R18",
        "oem_tire_rear": "285/35R19",
        "year_start": 2021,
        "year_end": None,
    },
    ("BMW", "M4", "F82"): {
        "oem_diameter": 18,
        "oem_width": 9.0,
        "oem_offset": 29,
        "oem_rear_width": 10.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "year_start": 2014,
        "year_end": 2020,
    },
    ("BMW", "M4", "G82"): {
        "oem_diameter": 18,
        "oem_width": 9.0,
        "oem_offset": 23,
        "oem_rear_width": 10.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "year_start": 2021,
        "year_end": None,
    },
    ("BMW", "M6", "E24"): {
        "oem_diameter": 14,
        "oem_width": 6.5,
        "oem_offset": 23,
        "oem_rear_width": 6.5,
        "oem_rear_offset": 23,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 14,
        "year_start": 1983,
        "year_end": 1989,
    },
    ("BMW", "340i", "F30"): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 34,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 34,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2016,
        "year_end": 2018,
    },
    # =========================================================================
    # Honda / Acura
    # =========================================================================
    ("Honda", "Civic", "EG"): {
        "oem_diameter": 14,
        "oem_width": 5.5,
        "oem_offset": 45,
        "oem_rear_width": 5.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 13,
        "year_start": 1992,
        "year_end": 2000,
    },
    ("Honda", "Civic", "EK"): {
        "oem_diameter": 14,
        "oem_width": 5.5,
        "oem_offset": 45,
        "oem_rear_width": 5.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 13,
        "year_start": 1996,
        "year_end": 2000,
    },
    ("Honda", "Civic", "FG/FA"): {
        "oem_diameter": 16,
        "oem_width": 6.5,
        "oem_offset": 45,
        "oem_rear_width": 6.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 2006,
        "year_end": 2011,
    },
    ("Honda", "Civic", "FC/FK"): {
        "oem_diameter": 16,
        "oem_width": 7.0,
        "oem_offset": 45,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2016,
        "year_end": 2021,
    },
    ("Honda", "Civic", "FL"): {
        "oem_diameter": 17,
        "oem_width": 7.0,
        "oem_offset": 45,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2022,
        "year_end": None,
    },
    ("Honda", "Civic Type R", "FK8"): {
        "oem_diameter": 20,
        "oem_width": 8.5,
        "oem_offset": 60,
        "oem_rear_width": 8.5,
        "oem_rear_offset": 60,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "oem_tire_front": "245/30R20",
        "oem_tire_rear": "245/30R20",
        "year_start": 2017,
        "year_end": 2021,
    },
    ("Honda", "Civic Type R", "FL5"): {
        "oem_diameter": 19,
        "oem_width": 9.5,
        "oem_offset": 45,
        "oem_rear_width": 9.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2022,
        "year_end": None,
    },
    ("Honda", "Civic Si", "FC"): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 45,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": 2020,
    },
    ("Honda", "Accord", None): {
        "oem_diameter": 17,
        "oem_width": 7.5,
        "oem_offset": 45,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2018,
        "year_end": 2022,
    },
    ("Acura", "TLX", None): {
        "oem_diameter": 19,
        "oem_width": 8.5,
        "oem_offset": 45,
        "oem_rear_width": 8.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2021,
        "year_end": None,
    },
    ("Acura", "NSX", None): {
        "oem_diameter": 19,
        "oem_width": 8.5,
        "oem_offset": 50,
        "oem_rear_width": 11.0,
        "oem_rear_offset": 56,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 19,
        "oem_tire_front": "245/35R19",
        "oem_tire_rear": "305/30R20",
        "year_start": 2017,
        "year_end": 2022,
    },
    # =========================================================================
    # Subaru
    # =========================================================================
    ("Subaru", "WRX", "GD/GR"): {
        "oem_diameter": 17,
        "oem_width": 7.0,
        "oem_offset": 48,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 48,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2002,
        "year_end": 2014,
    },
    ("Subaru", "WRX STI", "GD/GR"): {
        "oem_diameter": 18,
        "oem_width": 8.5,
        "oem_offset": 55,
        "oem_rear_width": 8.5,
        "oem_rear_offset": 55,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "oem_tire_front": "245/40R18",
        "oem_tire_rear": "245/40R18",
        "year_start": 2004,
        "year_end": 2014,
    },
    ("Subaru", "WRX", "VA"): {
        "oem_diameter": 17,
        "oem_width": 8.0,
        "oem_offset": 48,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 48,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": 2021,
    },
    ("Subaru", "WRX STI", "VA"): {
        "oem_diameter": 19,
        "oem_width": 8.5,
        "oem_offset": 55,
        "oem_rear_width": 8.5,
        "oem_rear_offset": 55,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2015,
        "year_end": 2021,
    },
    ("Subaru", "BRZ", "ZC6"): {
        "oem_diameter": 17,
        "oem_width": 7.0,
        "oem_offset": 48,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 48,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2013,
        "year_end": 2020,
    },
    # =========================================================================
    # Toyota / Scion / Lexus
    # =========================================================================
    ("Toyota", "86", "ZN6"): {
        "oem_diameter": 17,
        "oem_width": 7.0,
        "oem_offset": 48,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 48,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2012,
        "year_end": 2020,
    },
    ("Scion", "FR-S", "ZN6"): {
        "oem_diameter": 17,
        "oem_width": 7.0,
        "oem_offset": 48,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 48,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2012,
        "year_end": 2016,
    },
    ("Toyota", "GR86", "ZN8"): {
        "oem_diameter": 18,
        "oem_width": 7.5,
        "oem_offset": 48,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 48,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2022,
        "year_end": None,
    },
    ("Toyota", "GR Supra", "A90"): {
        "oem_diameter": 19,
        "oem_width": 9.0,
        "oem_offset": 32,
        "oem_rear_width": 10.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "oem_tire_front": "255/35R19",
        "oem_tire_rear": "275/35R19",
        "year_start": 2019,
        "year_end": None,
    },
    ("Toyota", "Camry", None): {
        "oem_diameter": 17,
        "oem_width": 7.0,
        "oem_offset": 40,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2018,
        "year_end": None,
    },
    ("Toyota", "GR Corolla", None): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 45,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2023,
        "year_end": None,
    },
    ("Lexus", "IS350", None): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 40,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2014,
        "year_end": None,
    },
    # =========================================================================
    # Mazda
    # =========================================================================
    ("Mazda", "Miata", "NA"): {
        "oem_diameter": 14,
        "oem_width": 5.5,
        "oem_offset": 45,
        "oem_rear_width": 5.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 14,
        "year_start": 1990,
        "year_end": 1997,
    },
    ("Mazda", "Miata", "NB"): {
        "oem_diameter": 15,
        "oem_width": 6.0,
        "oem_offset": 40,
        "oem_rear_width": 6.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 14,
        "year_start": 1999,
        "year_end": 2005,
    },
    ("Mazda", "MX-5", "NC"): {
        "oem_diameter": 17,
        "oem_width": 7.0,
        "oem_offset": 50,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 50,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2006,
        "year_end": 2015,
    },
    ("Mazda", "MX-5", "ND"): {
        "oem_diameter": 16,
        "oem_width": 6.5,
        "oem_offset": 50,
        "oem_rear_width": 6.5,
        "oem_rear_offset": 50,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2016,
        "year_end": None,
    },
    ("Mazda", "Mazda3", None): {
        "oem_diameter": 18,
        "oem_width": 7.0,
        "oem_offset": 45,
        "oem_rear_width": 7.0,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 16,
        "year_start": 2019,
        "year_end": None,
    },
    # =========================================================================
    # Nissan / Infiniti
    # =========================================================================
    ("Nissan", "240SX", "S13"): {
        "oem_diameter": 15,
        "oem_width": 6.0,
        "oem_offset": 40,
        "oem_rear_width": 6.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 14,
        "year_start": 1989,
        "year_end": 1994,
    },
    ("Nissan", "240SX", "S14"): {
        "oem_diameter": 16,
        "oem_width": 6.5,
        "oem_offset": 40,
        "oem_rear_width": 6.5,
        "oem_rear_offset": 40,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 15,
        "year_start": 1995,
        "year_end": 1998,
    },
    ("Nissan", "350Z", "Z33"): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 30,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 30,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2003,
        "year_end": 2008,
    },
    ("Nissan", "370Z", "Z34"): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 30,
        "oem_rear_width": 9.0,
        "oem_rear_offset": 30,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "oem_tire_front": "245/40R18",
        "oem_tire_rear": "275/35R19",
        "year_start": 2009,
        "year_end": 2020,
    },
    ("Nissan", "Z", "Z35"): {
        "oem_diameter": 19,
        "oem_width": 9.0,
        "oem_offset": 30,
        "oem_rear_width": 10.0,
        "oem_rear_offset": 30,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "year_start": 2023,
        "year_end": None,
    },
    ("Nissan", "GT-R", "R35"): {
        "oem_diameter": 20,
        "oem_width": 9.5,
        "oem_offset": 45,
        "oem_rear_width": 10.5,
        "oem_rear_offset": 25,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 20,
        "oem_tire_front": "255/40R20",
        "oem_tire_rear": "285/35R20",
        "year_start": 2009,
        "year_end": None,
    },
    ("Infiniti", "Q60", None): {
        "oem_diameter": 19,
        "oem_width": 9.0,
        "oem_offset": 40,
        "oem_rear_width": 9.0,
        "oem_rear_offset": 40,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2017,
        "year_end": 2022,
    },
    # =========================================================================
    # Mitsubishi
    # =========================================================================
    ("Mitsubishi", "Lancer Evolution", None): {
        "oem_diameter": 18,
        "oem_width": 8.5,
        "oem_offset": 38,
        "oem_rear_width": 8.5,
        "oem_rear_offset": 38,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "oem_tire_front": "245/40R18",
        "oem_tire_rear": "245/40R18",
        "year_start": 2008,
        "year_end": 2015,
    },
    # =========================================================================
    # German — Mercedes / Audi / VW / Porsche
    # =========================================================================
    ("Mercedes-Benz", "C63 AMG", None): {
        "oem_diameter": 19,
        "oem_width": 8.5,
        "oem_offset": 43,
        "oem_rear_width": 9.5,
        "oem_rear_offset": 36,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "year_start": 2015,
        "year_end": None,
    },
    ("Mercedes-Benz", "E350", None): {
        "oem_diameter": 18,
        "oem_width": 8.0,
        "oem_offset": 43,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 43,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2017,
        "year_end": None,
    },
    ("Audi", "RS5", None): {
        "oem_diameter": 19,
        "oem_width": 9.0,
        "oem_offset": 35,
        "oem_rear_width": 9.0,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2018,
        "year_end": None,
    },
    ("Audi", "S4", None): {
        "oem_diameter": 19,
        "oem_width": 8.5,
        "oem_offset": 35,
        "oem_rear_width": 8.5,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2017,
        "year_end": None,
    },
    ("Volkswagen", "Golf R", None): {
        "oem_diameter": 19,
        "oem_width": 7.5,
        "oem_offset": 45,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": None,
    },
    ("Volkswagen", "GTI", None): {
        "oem_diameter": 18,
        "oem_width": 7.5,
        "oem_offset": 45,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 45,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": None,
    },
    ("Porsche", "911", "991/992"): {
        "oem_diameter": 20,
        "oem_width": 8.5,
        "oem_offset": 50,
        "oem_rear_width": 11.5,
        "oem_rear_offset": 56,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 19,
        "year_start": 2012,
        "year_end": None,
    },
    ("Porsche", "Cayman", "982"): {
        "oem_diameter": 19,
        "oem_width": 8.0,
        "oem_offset": 50,
        "oem_rear_width": 10.0,
        "oem_rear_offset": 45,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "year_start": 2016,
        "year_end": None,
    },
    # =========================================================================
    # American — Ford
    # =========================================================================
    ("Ford", "Mustang GT", "S550"): {
        "oem_diameter": 19,
        "oem_width": 9.0,
        "oem_offset": 45,
        "oem_rear_width": 9.5,
        "oem_rear_offset": 50,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": None,
    },
    ("Ford", "F-150", None): {
        "oem_diameter": 17,
        "oem_width": 7.5,
        "oem_offset": 44,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 44,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": None,
    },
    ("Ford", "Focus RS", None): {
        "oem_diameter": 19,
        "oem_width": 8.0,
        "oem_offset": 50,
        "oem_rear_width": 8.0,
        "oem_rear_offset": 50,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2016,
        "year_end": 2018,
    },
    # =========================================================================
    # American — Chevrolet / Dodge
    # =========================================================================
    ("Chevrolet", "Camaro SS", None): {
        "oem_diameter": 20,
        "oem_width": 8.5,
        "oem_offset": 35,
        "oem_rear_width": 10.0,
        "oem_rear_offset": 35,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 18,
        "year_start": 2016,
        "year_end": None,
    },
    ("Chevrolet", "Corvette C8", None): {
        "oem_diameter": 19,
        "oem_width": 8.5,
        "oem_offset": 30,
        "oem_rear_width": 11.0,
        "oem_rear_offset": 65,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 19,
        "year_start": 2020,
        "year_end": None,
    },
    ("Chevrolet", "Silverado", None): {
        "oem_diameter": 17,
        "oem_width": 7.5,
        "oem_offset": 28,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 28,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2014,
        "year_end": None,
    },
    ("Dodge", "Challenger", None): {
        "oem_diameter": 18,
        "oem_width": 7.5,
        "oem_offset": 20,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 20,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": None,
    },
    ("Dodge", "Charger", None): {
        "oem_diameter": 18,
        "oem_width": 7.5,
        "oem_offset": 20,
        "oem_rear_width": 7.5,
        "oem_rear_offset": 20,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 17,
        "year_start": 2015,
        "year_end": None,
    },
    # =========================================================================
    # Tesla
    # =========================================================================
    ("Tesla", "Model 3", None): {
        "oem_diameter": 18,
        "oem_width": 8.5,
        "oem_offset": 35,
        "oem_rear_width": 8.5,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2017,
        "year_end": None,
    },
    ("Tesla", "Model S", None): {
        "oem_diameter": 19,
        "oem_width": 8.5,
        "oem_offset": 40,
        "oem_rear_width": 9.5,
        "oem_rear_offset": 40,
        "is_staggered_stock": True,
        "min_brake_clearance_diameter": 19,
        "year_start": 2012,
        "year_end": None,
    },
    ("Tesla", "Model Y", None): {
        "oem_diameter": 19,
        "oem_width": 9.5,
        "oem_offset": 35,
        "oem_rear_width": 9.5,
        "oem_rear_offset": 35,
        "is_staggered_stock": False,
        "min_brake_clearance_diameter": 18,
        "year_start": 2020,
        "year_end": None,
    },
}


# ---------------------------------------------------------------------------
# Lookup function
# ---------------------------------------------------------------------------

def lookup_oem_specs(
    make: str | None,
    model: str | None,
    chassis_code: str | None,
    year: int | None = None,
) -> dict[str, Any] | None:
    """Look up verified OEM specs for a vehicle.

    Lookup priority:
      1. Exact (make, model, chassis_code) match
      2. (make, model, None) — for vehicles without chassis code
      3. Year-range filtering if year is provided

    Returns:
        OEM spec dict if found, None otherwise.
    """
    if not make or not model:
        return None

    make_upper = make.strip()
    model_upper = model.strip()
    chassis_upper = chassis_code.strip().upper() if chassis_code else None

    # Priority 1: Exact match with chassis code
    if chassis_upper:
        key = (make_upper, model_upper, chassis_upper)
        if key in OEM_SPECS:
            entry = OEM_SPECS[key]
            if _year_in_range(year, entry):
                return dict(entry)  # Return copy

    # Priority 2: Match without chassis code (for entries keyed with None)
    key_no_chassis = (make_upper, model_upper, None)
    if key_no_chassis in OEM_SPECS:
        entry = OEM_SPECS[key_no_chassis]
        if _year_in_range(year, entry):
            return dict(entry)

    # Priority 3: Scan all entries for make+model match with year range
    # (handles case where chassis_code is not provided but entry has one)
    best_match: OEMEntry | None = None
    for (m, mod, _chassis), entry in OEM_SPECS.items():
        if m == make_upper and mod == model_upper:
            if _year_in_range(year, entry):
                # Prefer more specific (chassis) over generic
                if best_match is None or _chassis is not None:
                    best_match = entry

    if best_match is not None:
        return dict(best_match)

    return None


def _year_in_range(year: int | None, entry: OEMEntry) -> bool:
    """Check if year falls within the entry's production range."""
    if year is None:
        return True  # No year filter = accept any entry
    y_start = entry.get("year_start")
    y_end = entry.get("year_end")
    if y_start is not None and year < y_start:
        return False
    if y_end is not None and year > y_end:
        return False
    return True
