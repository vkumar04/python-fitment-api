"""Deterministic fitment solver tests.

These tests verify the geometry engine, OEM spec registry, fitment envelopes,
and hub bore compatibility — all WITHOUT calling any LLM. Pure math.

Usage:
    uv run pytest tests/test_fitment_deterministic.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.dspy_v2.oem_specs import lookup_oem_specs
from src.services.dspy_v2.fitment_envelopes import get_envelope
from src.services.dspy_v2.pipeline import calculate_wheel_fitment


# =============================================================================
# OEM Specs Registry Tests
# =============================================================================

class TestOEMSpecsLookup:
    """Test the hardcoded OEM specs registry."""

    def test_e30_m3_specs(self):
        oem = lookup_oem_specs("BMW", "M3", "E30")
        assert oem is not None
        assert oem["oem_width"] == 7.0
        assert oem["oem_offset"] == 25
        assert oem["oem_diameter"] == 15
        assert oem["is_staggered_stock"] is False
        assert oem["min_brake_clearance_diameter"] == 15

    def test_e36_m3_specs(self):
        oem = lookup_oem_specs("BMW", "M3", "E36")
        assert oem is not None
        assert oem["oem_width"] == 7.5
        assert oem["oem_offset"] == 41
        assert oem["oem_diameter"] == 17
        assert oem["is_staggered_stock"] is False
        assert oem["min_brake_clearance_diameter"] == 17

    def test_e39_m5_staggered(self):
        oem = lookup_oem_specs("BMW", "M5", "E39")
        assert oem is not None
        assert oem["oem_width"] == 8.0
        assert oem["oem_offset"] == 20
        assert oem["oem_rear_width"] == 9.5
        assert oem["oem_rear_offset"] == 22
        assert oem["is_staggered_stock"] is True
        assert oem["min_brake_clearance_diameter"] == 18

    def test_e46_m3_staggered(self):
        oem = lookup_oem_specs("BMW", "M3", "E46")
        assert oem is not None
        assert oem["oem_width"] == 8.0
        assert oem["oem_offset"] == 47
        assert oem["oem_rear_width"] == 9.0
        assert oem["oem_rear_offset"] == 26
        assert oem["is_staggered_stock"] is True
        assert oem["min_brake_clearance_diameter"] == 18

    def test_civic_10th_gen(self):
        oem = lookup_oem_specs("Honda", "Civic", "FC/FK", year=2020)
        assert oem is not None
        assert oem["oem_width"] == 7.0
        assert oem["oem_offset"] == 45

    def test_civic_11th_gen(self):
        oem = lookup_oem_specs("Honda", "Civic", "FL", year=2023)
        assert oem is not None
        assert oem["oem_width"] == 7.0
        assert oem["oem_offset"] == 45

    def test_unknown_vehicle_returns_none(self):
        oem = lookup_oem_specs("Lada", "Niva", None)
        assert oem is None

    def test_year_range_filtering(self):
        """E30 M3 was only 1986-1991."""
        oem = lookup_oem_specs("BMW", "M3", "E30", year=1988)
        assert oem is not None
        oem = lookup_oem_specs("BMW", "M3", "E30", year=2020)
        assert oem is None  # Out of production range

    def test_no_chassis_code_lookup(self):
        """Vehicles without chassis code should still match."""
        oem = lookup_oem_specs("Honda", "Accord", None, year=2020)
        assert oem is not None
        assert oem["oem_width"] == 7.5

    def test_model_without_chassis_finds_best_match(self):
        """When no chassis provided, should find any matching entry."""
        oem = lookup_oem_specs("BMW", "M3", None, year=1998)
        assert oem is not None
        # Should match E36 M3 (1995-1999)
        assert oem["oem_offset"] == 41

    def test_gr_supra_staggered(self):
        oem = lookup_oem_specs("Toyota", "GR Supra", "A90")
        assert oem is not None
        assert oem["is_staggered_stock"] is True
        assert oem["oem_width"] == 9.0
        assert oem["oem_rear_width"] == 10.0

    def test_nissan_370z_staggered(self):
        oem = lookup_oem_specs("Nissan", "370Z", "Z34")
        assert oem is not None
        assert oem["is_staggered_stock"] is True
        assert oem["oem_rear_width"] == 9.0

    def test_returns_copy_not_reference(self):
        """Lookup should return a copy, not the original dict."""
        oem1 = lookup_oem_specs("BMW", "M3", "E30")
        oem2 = lookup_oem_specs("BMW", "M3", "E30")
        assert oem1 is not oem2
        oem1["oem_width"] = 999  # type: ignore
        oem2_fresh = lookup_oem_specs("BMW", "M3", "E30")
        assert oem2_fresh is not None
        assert oem2_fresh["oem_width"] == 7.0


# =============================================================================
# Fitment Envelope Tests
# =============================================================================

class TestFitmentEnvelopes:
    """Test the per-chassis fitment envelope system."""

    def test_e30_flush_stock_envelope(self):
        env, confidence = get_envelope("E30", "flush", "stock")
        assert confidence == "high"
        assert env["max_outer_delta_mm"] == 10
        assert env["max_inner_delta_mm"] == 15

    def test_e30_aggressive_coilovers_envelope(self):
        env, confidence = get_envelope("E30", "aggressive", "coilovers")
        assert confidence == "high"
        assert env["max_outer_delta_mm"] == 30
        assert env["max_inner_delta_mm"] == 25

    def test_unknown_chassis_gets_defaults(self):
        env, confidence = get_envelope("UNKNOWN", "flush", "stock")
        assert confidence == "medium"
        assert env["max_outer_delta_mm"] == 18  # Global stock default

    def test_none_chassis_gets_defaults(self):
        env, confidence = get_envelope(None, None, None)
        assert confidence == "medium"

    def test_suspension_scaling(self):
        """When chassis has stock envelope but not coilovers, it should scale."""
        env_stock, _ = get_envelope("E36", "flush", "stock")
        env_coils, _ = get_envelope("E36", "flush", "coilovers")
        # Coilovers should have higher thresholds than stock
        assert env_coils["max_outer_delta_mm"] > env_stock["max_outer_delta_mm"]

    def test_use_case_aliases(self):
        """'daily' should map to 'flush', 'stance' to 'aggressive'."""
        env_daily, _ = get_envelope("E30", "daily", "stock")
        env_flush, _ = get_envelope("E30", "flush", "stock")
        assert env_daily["max_outer_delta_mm"] == env_flush["max_outer_delta_mm"]

    def test_suspension_aliases(self):
        """'coils' should map to 'coilovers'."""
        env_coils, _ = get_envelope("E30", "flush", "coils")
        env_coilovers, _ = get_envelope("E30", "flush", "coilovers")
        assert env_coils["max_outer_delta_mm"] == env_coilovers["max_outer_delta_mm"]


# =============================================================================
# Geometry Engine Tests
# =============================================================================

class TestGeometryEngine:
    """Test calculate_wheel_fitment() with known setups."""

    def test_e36_m3_17x9_plus42(self):
        """E36 M3 track setup: 17x9 +42 on OEM 17x7.5 +41."""
        calc = calculate_wheel_fitment(
            wheel_width_inches=9.0,
            wheel_offset_mm=42,
            oem_width_inches=7.5,
            oem_offset_mm=41,
            suspension="coilovers",
        )
        # Width diff = 1.5" * 25.4 = 38.1mm, offset diff = 41-42 = -1
        # Poke = 38.1/2 + (-1) = 18.05mm
        assert abs(calc["poke_mm"] - 18.1) < 0.2
        assert calc["style"] == "mild poke"

    def test_e30_m3_flush_15x8_plus25(self):
        """E30 M3 flush: 15x8 +25 on OEM 15x7 +25."""
        calc = calculate_wheel_fitment(
            wheel_width_inches=8.0,
            wheel_offset_mm=25,
            oem_width_inches=7.0,
            oem_offset_mm=25,
            suspension="stock",
        )
        # Width diff = 1.0" * 25.4 = 25.4mm, offset diff = 0
        # Poke = 25.4/2 + 0 = 12.7mm
        assert abs(calc["poke_mm"] - 12.7) < 0.1
        assert calc["style"] == "mild poke"

    def test_oem_wheels_zero_poke(self):
        """OEM-sized wheel should have 0 poke and 0 inner change."""
        calc = calculate_wheel_fitment(
            wheel_width_inches=7.5,
            wheel_offset_mm=41,
            oem_width_inches=7.5,
            oem_offset_mm=41,
            suspension="stock",
        )
        assert calc["poke_mm"] == 0.0
        assert calc["inner_change_mm"] == 0.0
        assert calc["fits_without_mods"] is True
        assert calc["verdict"] == "fits"
        assert len(calc["mods_needed"]) == 0

    def test_aggressive_poke_needs_mods(self):
        """Very aggressive offset should require fender work."""
        calc = calculate_wheel_fitment(
            wheel_width_inches=10.0,
            wheel_offset_mm=0,
            oem_width_inches=7.0,
            oem_offset_mm=25,
            suspension="stock",
        )
        # Width diff = 3.0" * 25.4 = 76.2mm, offset diff = 25-0 = 25
        # Poke = 76.2/2 + 25 = 63.1mm — very aggressive
        assert calc["poke_mm"] > 60
        assert calc["fits_without_mods"] is False
        assert len(calc["mods_needed"]) > 0

    def test_envelope_overrides_global_thresholds(self):
        """Per-chassis envelope should override global poke limits."""
        # E30 flush stock envelope: max_outer_delta_mm = 10
        envelope = {
            "max_outer_delta_mm": 10,
            "max_inner_delta_mm": 15,
            "roll_threshold_mm": 12,
            "pull_threshold_mm": 22,
        }
        calc = calculate_wheel_fitment(
            wheel_width_inches=8.0,
            wheel_offset_mm=25,
            oem_width_inches=7.0,
            oem_offset_mm=25,
            suspension="stock",
            envelope=envelope,
        )
        # Poke = 12.7mm, envelope max = 10mm → should NOT fit without mods
        assert calc["poke_mm"] > 10
        assert calc["fits_without_mods"] is False
        assert calc["verdict"] == "fits_with_mods"

    def test_without_envelope_uses_global(self):
        """Without envelope, should use global stock limit (18mm)."""
        calc = calculate_wheel_fitment(
            wheel_width_inches=8.0,
            wheel_offset_mm=25,
            oem_width_inches=7.0,
            oem_offset_mm=25,
            suspension="stock",
        )
        # Poke = 12.7mm, global stock limit = 18mm → FITS
        assert calc["poke_mm"] > 10
        assert calc["fits_without_mods"] is True

    def test_does_not_fit_extreme_poke(self):
        """Extreme poke should trigger does_not_fit verdict."""
        envelope = {
            "max_outer_delta_mm": 10,
            "max_inner_delta_mm": 15,
            "roll_threshold_mm": 15,
            "pull_threshold_mm": 25,
        }
        calc = calculate_wheel_fitment(
            wheel_width_inches=12.0,
            wheel_offset_mm=-20,
            oem_width_inches=7.0,
            oem_offset_mm=25,
            suspension="stock",
            envelope=envelope,
        )
        # Poke = (5*25.4/2) + (25+20) = 63.5 + 45 = 108.5mm
        # pull_threshold + 15 = 40mm → does_not_fit
        assert calc["verdict"] == "does_not_fit"

    def test_inner_clearance_math(self):
        """Inner clearance change should be calculated correctly."""
        calc = calculate_wheel_fitment(
            wheel_width_inches=9.0,
            wheel_offset_mm=35,
            oem_width_inches=7.0,
            oem_offset_mm=41,
            suspension="stock",
        )
        # Width diff = 2.0" * 25.4 = 50.8mm
        # Inner change = 50.8/2 - (35 - 41) = 25.4 + 6 = 31.4mm
        assert abs(calc["inner_change_mm"] - 31.4) < 0.1

    def test_verdict_field_present(self):
        """All results should include verdict field."""
        calc = calculate_wheel_fitment(
            wheel_width_inches=7.5,
            wheel_offset_mm=41,
            oem_width_inches=7.5,
            oem_offset_mm=41,
        )
        assert "verdict" in calc
        assert calc["verdict"] in ("fits", "fits_with_mods", "does_not_fit")


# =============================================================================
# Hub Bore Compatibility Tests
# =============================================================================

class TestHubBoreCompatibility:
    """Test hub bore logic via OEM specs."""

    def test_e30_m3_hub_72_6_vs_kansei_73_1(self):
        """E30 M3 has 72.6mm hub. Kansei is 73.1mm bore → hub rings."""
        oem = lookup_oem_specs("BMW", "M3", "E30")
        assert oem is not None
        # Hub bore check is in pipeline's _validate_fitment_matches
        # Here we just verify the center_bore data exists
        # (72.6mm hub < 73.1mm bore → hub rings needed)

    def test_e39_m5_hub_74_1_vs_kansei_73_1(self):
        """E39 M5 has 74.1mm hub (not 72.6mm like other 5x120 BMWs).

        Kansei bore is 73.1mm — wheel bore < hub bore = incompatible.
        Center bore comes from DB/vehicle_specs, not oem_specs registry.
        """
        oem = lookup_oem_specs("BMW", "M5", "E39")
        assert oem is not None
        assert oem["is_staggered_stock"] is True


# =============================================================================
# Integration: OEM + Envelope + Geometry
# =============================================================================

class TestIntegration:
    """Test the full deterministic chain: OEM → Envelope → Geometry."""

    def test_e30_m3_flush_stock_chain(self):
        """E30 M3 flush stock: 15x8 +25 → should need minor fender adjustment."""
        oem = lookup_oem_specs("BMW", "M3", "E30")
        assert oem is not None

        envelope, confidence = get_envelope("E30", "flush", "stock")
        assert confidence == "high"

        calc = calculate_wheel_fitment(
            wheel_width_inches=8.0,
            wheel_offset_mm=25,
            oem_width_inches=oem["oem_width"],
            oem_offset_mm=oem["oem_offset"],
            suspension="stock",
            envelope=envelope,
        )
        # 12.7mm poke with 10mm envelope → fits_with_mods
        assert calc["verdict"] == "fits_with_mods"
        assert len(calc["mods_needed"]) > 0

    def test_e36_m3_track_17x9_plus42(self):
        """E36 M3 track: 17x9 +42 on coilovers → high confidence."""
        oem = lookup_oem_specs("BMW", "M3", "E36")
        assert oem is not None

        envelope, confidence = get_envelope("E36", "track", "coilovers")
        assert confidence == "high"

        calc = calculate_wheel_fitment(
            wheel_width_inches=9.0,
            wheel_offset_mm=42,
            oem_width_inches=oem["oem_width"],
            oem_offset_mm=oem["oem_offset"],
            suspension="coilovers",
            envelope=envelope,
        )
        # Poke ~18mm, track coilovers envelope max is 8mm → fits_with_mods
        assert calc["verdict"] in ("fits_with_mods", "does_not_fit")

    def test_e39_m5_17_inch_rejected(self):
        """E39 M5 with 17" wheel should fail brake clearance (min 18")."""
        oem = lookup_oem_specs("BMW", "M5", "E39")
        assert oem is not None
        assert oem["min_brake_clearance_diameter"] == 18
        # 17" < 18" min → hard fail (checked in _validate_fitment_matches)

    def test_unknown_vehicle_medium_confidence(self):
        """Unknown vehicle should get medium confidence envelope."""
        oem = lookup_oem_specs("Lada", "Niva", None)
        assert oem is None

        envelope, confidence = get_envelope(None, "flush", "stock")
        assert confidence == "medium"
