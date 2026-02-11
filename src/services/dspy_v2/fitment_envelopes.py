"""Fitment envelope registry — per-chassis geometric bounds.

An envelope defines the allowable wheel geometry for a specific chassis + use
case + suspension combination. The deterministic geometry solver uses these
thresholds instead of the LLM.

Envelope fields:
  max_outer_delta_mm  — max poke (positive = outboard) before it doesn't fit
  max_inner_delta_mm  — max inner clearance loss before strut contact
  roll_threshold_mm   — poke beyond this needs fender rolling
  pull_threshold_mm   — poke beyond this needs fender pulling/flaring
  preferred_diameters — ideal wheel diameters for this chassis + use case
  min_width / max_width — acceptable wheel width range
  min_offset / max_offset — acceptable offset range

If no chassis-specific envelope exists, DEFAULT_ENVELOPES provides safe global
thresholds (the same values that were previously hardcoded in pipeline.py).
"""

from __future__ import annotations

from typing import Any

# Type alias
Envelope = dict[str, Any]


# ---------------------------------------------------------------------------
# Per-chassis envelopes
# Key: (chassis_code, use_case, suspension)
# ---------------------------------------------------------------------------
CHASSIS_ENVELOPES: dict[tuple[str, str, str], Envelope] = {
    # =========================================================================
    # BMW E30 — narrow fender arches, limited inner clearance
    # =========================================================================
    ("E30", "flush", "stock"): {
        "max_outer_delta_mm": 10,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 22,
        "preferred_diameters": [15, 16],
        "min_width": 7.0,
        "max_width": 8.5,
        "min_offset": 15,
        "max_offset": 35,
    },
    ("E30", "flush", "lowered"): {
        "max_outer_delta_mm": 12,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [15, 16],
        "min_width": 7.0,
        "max_width": 9.0,
        "min_offset": 10,
        "max_offset": 35,
    },
    ("E30", "flush", "coilovers"): {
        "max_outer_delta_mm": 15,
        "max_inner_delta_mm": 22,
        "roll_threshold_mm": 18,
        "pull_threshold_mm": 28,
        "preferred_diameters": [15, 16],
        "min_width": 7.0,
        "max_width": 9.0,
        "min_offset": 10,
        "max_offset": 35,
    },
    ("E30", "aggressive", "stock"): {
        "max_outer_delta_mm": 18,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [15, 16],
        "min_width": 8.0,
        "max_width": 9.5,
        "min_offset": 0,
        "max_offset": 25,
    },
    ("E30", "aggressive", "coilovers"): {
        "max_outer_delta_mm": 30,
        "max_inner_delta_mm": 25,
        "roll_threshold_mm": 20,
        "pull_threshold_mm": 35,
        "preferred_diameters": [16, 17],
        "min_width": 8.0,
        "max_width": 10.0,
        "min_offset": 0,
        "max_offset": 25,
    },
    ("E30", "track", "coilovers"): {
        "max_outer_delta_mm": 8,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 20,
        "preferred_diameters": [15, 16],
        "min_width": 7.5,
        "max_width": 9.0,
        "min_offset": 15,
        "max_offset": 35,
    },
    # =========================================================================
    # BMW E36 — slightly wider arches than E30, M3 has factory flares
    # =========================================================================
    ("E36", "flush", "stock"): {
        "max_outer_delta_mm": 12,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [17, 18],
        "min_width": 7.5,
        "max_width": 9.0,
        "min_offset": 20,
        "max_offset": 45,
    },
    ("E36", "flush", "coilovers"): {
        "max_outer_delta_mm": 18,
        "max_inner_delta_mm": 22,
        "roll_threshold_mm": 18,
        "pull_threshold_mm": 30,
        "preferred_diameters": [17, 18],
        "min_width": 8.0,
        "max_width": 9.5,
        "min_offset": 15,
        "max_offset": 45,
    },
    ("E36", "aggressive", "coilovers"): {
        "max_outer_delta_mm": 30,
        "max_inner_delta_mm": 25,
        "roll_threshold_mm": 22,
        "pull_threshold_mm": 35,
        "preferred_diameters": [17, 18],
        "min_width": 9.0,
        "max_width": 10.5,
        "min_offset": 10,
        "max_offset": 35,
    },
    ("E36", "track", "coilovers"): {
        "max_outer_delta_mm": 8,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 20,
        "preferred_diameters": [17],
        "min_width": 8.0,
        "max_width": 9.5,
        "min_offset": 25,
        "max_offset": 45,
    },
    # =========================================================================
    # BMW E39 — wider body, M5 has Brembo brakes (min 18"), staggered stock
    # =========================================================================
    ("E39", "flush", "stock"): {
        "max_outer_delta_mm": 12,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [18, 19],
        "min_width": 8.0,
        "max_width": 9.5,
        "min_offset": 10,
        "max_offset": 35,
    },
    ("E39", "flush", "coilovers"): {
        "max_outer_delta_mm": 18,
        "max_inner_delta_mm": 22,
        "roll_threshold_mm": 18,
        "pull_threshold_mm": 30,
        "preferred_diameters": [18, 19],
        "min_width": 8.5,
        "max_width": 10.0,
        "min_offset": 5,
        "max_offset": 35,
    },
    ("E39", "aggressive", "coilovers"): {
        "max_outer_delta_mm": 28,
        "max_inner_delta_mm": 25,
        "roll_threshold_mm": 20,
        "pull_threshold_mm": 32,
        "preferred_diameters": [18, 19],
        "min_width": 9.0,
        "max_width": 10.5,
        "min_offset": 0,
        "max_offset": 30,
    },
    # =========================================================================
    # BMW E46 — M3 has wider arches, big brakes (min 18")
    # =========================================================================
    ("E46", "flush", "stock"): {
        "max_outer_delta_mm": 12,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [17, 18],
        "min_width": 7.5,
        "max_width": 9.0,
        "min_offset": 25,
        "max_offset": 47,
    },
    ("E46", "flush", "coilovers"): {
        "max_outer_delta_mm": 18,
        "max_inner_delta_mm": 22,
        "roll_threshold_mm": 18,
        "pull_threshold_mm": 30,
        "preferred_diameters": [17, 18],
        "min_width": 8.0,
        "max_width": 10.0,
        "min_offset": 20,
        "max_offset": 47,
    },
    ("E46", "aggressive", "coilovers"): {
        "max_outer_delta_mm": 28,
        "max_inner_delta_mm": 25,
        "roll_threshold_mm": 22,
        "pull_threshold_mm": 35,
        "preferred_diameters": [18, 19],
        "min_width": 9.0,
        "max_width": 10.5,
        "min_offset": 15,
        "max_offset": 40,
    },
    # =========================================================================
    # Honda EG/EK Civic — very tight fender arches, 4x100
    # =========================================================================
    ("EG", "flush", "stock"): {
        "max_outer_delta_mm": 8,
        "max_inner_delta_mm": 12,
        "roll_threshold_mm": 10,
        "pull_threshold_mm": 18,
        "preferred_diameters": [15, 16],
        "min_width": 6.5,
        "max_width": 7.5,
        "min_offset": 35,
        "max_offset": 50,
    },
    ("EK", "flush", "stock"): {
        "max_outer_delta_mm": 8,
        "max_inner_delta_mm": 12,
        "roll_threshold_mm": 10,
        "pull_threshold_mm": 18,
        "preferred_diameters": [15, 16],
        "min_width": 6.5,
        "max_width": 7.5,
        "min_offset": 35,
        "max_offset": 50,
    },
    # =========================================================================
    # Honda FK8 Civic Type R — wide body, big brakes (min 18")
    # =========================================================================
    ("FK8", "flush", "stock"): {
        "max_outer_delta_mm": 10,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [18, 19],
        "min_width": 8.5,
        "max_width": 9.5,
        "min_offset": 38,
        "max_offset": 55,
    },
    ("FK8", "track", "coilovers"): {
        "max_outer_delta_mm": 5,
        "max_inner_delta_mm": 12,
        "roll_threshold_mm": 10,
        "pull_threshold_mm": 18,
        "preferred_diameters": [18],
        "min_width": 9.0,
        "max_width": 10.0,
        "min_offset": 38,
        "max_offset": 50,
    },
    # =========================================================================
    # Honda FC/FK Civic (10th gen) — 5x114.3
    # =========================================================================
    ("FC/FK", "flush", "stock"): {
        "max_outer_delta_mm": 10,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 22,
        "preferred_diameters": [17, 18],
        "min_width": 7.0,
        "max_width": 8.5,
        "min_offset": 35,
        "max_offset": 50,
    },
    ("FC/FK", "aggressive", "coilovers"): {
        "max_outer_delta_mm": 25,
        "max_inner_delta_mm": 22,
        "roll_threshold_mm": 18,
        "pull_threshold_mm": 30,
        "preferred_diameters": [17, 18],
        "min_width": 8.0,
        "max_width": 9.5,
        "min_offset": 25,
        "max_offset": 45,
    },
    # =========================================================================
    # Honda FL Civic (11th gen) — 5x114.3
    # =========================================================================
    ("FL", "flush", "stock"): {
        "max_outer_delta_mm": 10,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 22,
        "preferred_diameters": [17, 18],
        "min_width": 7.0,
        "max_width": 8.5,
        "min_offset": 35,
        "max_offset": 50,
    },
    # =========================================================================
    # Nissan S13/S14 — drift-popular, wider clearance tolerance
    # =========================================================================
    ("S13", "flush", "stock"): {
        "max_outer_delta_mm": 15,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [16, 17],
        "min_width": 7.0,
        "max_width": 9.0,
        "min_offset": 10,
        "max_offset": 30,
    },
    ("S14", "flush", "stock"): {
        "max_outer_delta_mm": 15,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [17, 18],
        "min_width": 7.5,
        "max_width": 9.5,
        "min_offset": 10,
        "max_offset": 35,
    },
    ("S14", "aggressive", "coilovers"): {
        "max_outer_delta_mm": 35,
        "max_inner_delta_mm": 25,
        "roll_threshold_mm": 22,
        "pull_threshold_mm": 35,
        "preferred_diameters": [17, 18],
        "min_width": 9.0,
        "max_width": 10.5,
        "min_offset": -5,
        "max_offset": 20,
    },
    # =========================================================================
    # Mazda NA Miata — very small fenders
    # =========================================================================
    ("NA", "flush", "stock"): {
        "max_outer_delta_mm": 8,
        "max_inner_delta_mm": 12,
        "roll_threshold_mm": 10,
        "pull_threshold_mm": 18,
        "preferred_diameters": [14, 15],
        "min_width": 6.0,
        "max_width": 7.5,
        "min_offset": 25,
        "max_offset": 45,
    },
    ("NA", "flush", "coilovers"): {
        "max_outer_delta_mm": 12,
        "max_inner_delta_mm": 18,
        "roll_threshold_mm": 14,
        "pull_threshold_mm": 22,
        "preferred_diameters": [15, 16],
        "min_width": 6.5,
        "max_width": 8.0,
        "min_offset": 20,
        "max_offset": 45,
    },
    # =========================================================================
    # Subaru GD/GR WRX — fender scoop area tight
    # =========================================================================
    ("GD/GR", "flush", "stock"): {
        "max_outer_delta_mm": 10,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 22,
        "preferred_diameters": [17, 18],
        "min_width": 7.5,
        "max_width": 9.0,
        "min_offset": 35,
        "max_offset": 55,
    },
    # =========================================================================
    # Toyota ZN6 (86/FR-S/BRZ) — tight rear arches
    # =========================================================================
    ("ZN6", "flush", "stock"): {
        "max_outer_delta_mm": 10,
        "max_inner_delta_mm": 15,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 22,
        "preferred_diameters": [17, 18],
        "min_width": 7.5,
        "max_width": 9.0,
        "min_offset": 35,
        "max_offset": 50,
    },
    ("ZN6", "aggressive", "coilovers"): {
        "max_outer_delta_mm": 28,
        "max_inner_delta_mm": 22,
        "roll_threshold_mm": 20,
        "pull_threshold_mm": 32,
        "preferred_diameters": [17, 18],
        "min_width": 8.5,
        "max_width": 10.0,
        "min_offset": 20,
        "max_offset": 45,
    },
}


# ---------------------------------------------------------------------------
# Default envelopes — global fallback when no chassis-specific data exists
# These match the previous hardcoded values in calculate_wheel_fitment()
# ---------------------------------------------------------------------------
DEFAULT_ENVELOPES: dict[str, Envelope] = {
    "stock": {
        "max_outer_delta_mm": 18,
        "max_inner_delta_mm": 20,
        "roll_threshold_mm": 15,
        "pull_threshold_mm": 25,
        "preferred_diameters": [],
    },
    "lowered": {
        "max_outer_delta_mm": 25,
        "max_inner_delta_mm": 20,
        "roll_threshold_mm": 20,
        "pull_threshold_mm": 30,
        "preferred_diameters": [],
    },
    "coilovers": {
        "max_outer_delta_mm": 35,
        "max_inner_delta_mm": 25,
        "roll_threshold_mm": 25,
        "pull_threshold_mm": 38,
        "preferred_diameters": [],
    },
    "air": {
        "max_outer_delta_mm": 50,
        "max_inner_delta_mm": 30,
        "roll_threshold_mm": 35,
        "pull_threshold_mm": 50,
        "preferred_diameters": [],
    },
    "lifted": {
        "max_outer_delta_mm": 10,
        "max_inner_delta_mm": 20,
        "roll_threshold_mm": 12,
        "pull_threshold_mm": 20,
        "preferred_diameters": [],
    },
}


# ---------------------------------------------------------------------------
# Lookup function
# ---------------------------------------------------------------------------

def get_envelope(
    chassis_code: str | None,
    use_case: str | None,
    suspension: str | None,
) -> tuple[Envelope, str]:
    """Get the fitment envelope for a chassis + use case + suspension.

    Returns:
        Tuple of (envelope_dict, confidence_level).
        confidence_level is "high" (chassis-specific) or "medium" (defaults).
    """
    susp = (suspension or "stock").lower()
    use = (use_case or "flush").lower()

    # Normalize use_case aliases
    use_aliases = {
        "daily": "flush",
        "conservative": "flush",
        "safe": "flush",
        "fitted": "flush",
        "poke": "aggressive",
        "stance": "aggressive",
        "show": "aggressive",
        "performance": "track",
        "grip": "track",
    }
    use = use_aliases.get(use, use)

    # Normalize suspension aliases
    susp_aliases = {
        "coils": "coilovers",
        "slammed": "coilovers",
        "bagged": "air",
        "bags": "air",
        "air ride": "air",
        "air suspension": "air",
        "dropped": "lowered",
        "lowering springs": "lowered",
        "leveled": "lifted",
    }
    susp = susp_aliases.get(susp, susp)

    if chassis_code:
        chassis_upper = chassis_code.strip().upper()

        # Try exact match
        key = (chassis_upper, use, susp)
        if key in CHASSIS_ENVELOPES:
            return CHASSIS_ENVELOPES[key], "high"

        # Try with stock suspension (chassis-specific base)
        key_stock = (chassis_upper, use, "stock")
        if key_stock in CHASSIS_ENVELOPES:
            # Use chassis base, but adjust max_outer/inner for suspension
            base = dict(CHASSIS_ENVELOPES[key_stock])
            susp_default = DEFAULT_ENVELOPES.get(susp, DEFAULT_ENVELOPES["stock"])
            stock_default = DEFAULT_ENVELOPES["stock"]

            # Scale the chassis envelope by the ratio of suspension default to stock default
            outer_ratio = susp_default["max_outer_delta_mm"] / stock_default["max_outer_delta_mm"]
            inner_ratio = susp_default["max_inner_delta_mm"] / stock_default["max_inner_delta_mm"]
            base["max_outer_delta_mm"] = round(base["max_outer_delta_mm"] * outer_ratio, 1)
            base["max_inner_delta_mm"] = round(base["max_inner_delta_mm"] * inner_ratio, 1)
            base["roll_threshold_mm"] = round(base.get("roll_threshold_mm", 15) * outer_ratio, 1)
            base["pull_threshold_mm"] = round(base.get("pull_threshold_mm", 25) * outer_ratio, 1)
            return base, "high"

        # Try flush as fallback use_case (most conservative)
        key_flush = (chassis_upper, "flush", susp)
        if key_flush in CHASSIS_ENVELOPES:
            return CHASSIS_ENVELOPES[key_flush], "high"

        key_flush_stock = (chassis_upper, "flush", "stock")
        if key_flush_stock in CHASSIS_ENVELOPES:
            base = dict(CHASSIS_ENVELOPES[key_flush_stock])
            susp_default = DEFAULT_ENVELOPES.get(susp, DEFAULT_ENVELOPES["stock"])
            stock_default = DEFAULT_ENVELOPES["stock"]
            outer_ratio = susp_default["max_outer_delta_mm"] / stock_default["max_outer_delta_mm"]
            inner_ratio = susp_default["max_inner_delta_mm"] / stock_default["max_inner_delta_mm"]
            base["max_outer_delta_mm"] = round(base["max_outer_delta_mm"] * outer_ratio, 1)
            base["max_inner_delta_mm"] = round(base["max_inner_delta_mm"] * inner_ratio, 1)
            base["roll_threshold_mm"] = round(base.get("roll_threshold_mm", 15) * outer_ratio, 1)
            base["pull_threshold_mm"] = round(base.get("pull_threshold_mm", 25) * outer_ratio, 1)
            return base, "high"

    # Fallback: global defaults
    envelope = DEFAULT_ENVELOPES.get(susp, DEFAULT_ENVELOPES["stock"])
    return dict(envelope), "medium"
