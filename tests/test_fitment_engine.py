"""Tests for the fitment scoring engine and knowledge base."""

from app.models.vehicle import VehicleSpecs
from app.models.wheel import KanseiWheel
from app.services.fitment_engine import (
    calculate_poke,
    calculate_tire_recommendation,
    check_brake_clearance,
    lookup_bolt_pattern,
    lookup_known_specs,
    lookup_vehicle_specs,
    score_fitment,
    validate_bolt_pattern,
    vehicle_confidence,
)

# ---------------------------------------------------------------------------
# Knowledge Base Tests
# ---------------------------------------------------------------------------


class TestKnowledgeBase:
    """Verify the hardcoded knowledge base returns correct bolt patterns."""

    def test_e30_m3_is_5x120(self):
        specs = lookup_known_specs("BMW", "M3", chassis_code="E30")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x120"

    def test_e30_325i_is_4x100(self):
        specs = lookup_known_specs("BMW", "325i", chassis_code="E30")
        assert specs is not None
        assert specs["bolt_pattern"] == "4x100"

    def test_e36_m3_is_5x120(self):
        specs = lookup_known_specs("BMW", "M3", chassis_code="E36")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x120"

    def test_g20_is_5x112(self):
        specs = lookup_known_specs("BMW", "330i", chassis_code="G20")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x112"

    def test_civic_2020_is_5x114(self):
        specs = lookup_known_specs("Honda", "Civic", year=2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5x114.3"

    def test_civic_1995_is_4x100(self):
        specs = lookup_known_specs("Honda", "Civic", year=1995)
        assert specs is not None
        assert specs["bolt_pattern"] == "4x100"

    def test_fk8_type_r_is_5x120(self):
        specs = lookup_known_specs("Honda", "Civic Type R", chassis_code="FK8")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x120"

    def test_miata_na_is_4x100(self):
        specs = lookup_known_specs("Mazda", "Miata", year=1993)
        assert specs is not None
        assert specs["bolt_pattern"] == "4x100"

    def test_miata_nd_is_5x114(self):
        specs = lookup_known_specs("Mazda", "MX-5", year=2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5x114.3"

    def test_350z_is_5x114(self):
        specs = lookup_known_specs("Nissan", "350Z")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x114.3"

    def test_wrx_va_is_5x114(self):
        specs = lookup_known_specs("Subaru", "WRX", chassis_code="VA")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x114.3"

    def test_a90_supra_is_5x112(self):
        specs = lookup_known_specs("Toyota", "Supra", year=2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5x112"

    def test_mustang_is_5x114(self):
        specs = lookup_known_specs("Ford", "Mustang", year=2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5x114.3"

    def test_camaro_is_5x120(self):
        specs = lookup_known_specs("Chevrolet", "Camaro")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x120"

    def test_vw_is_5x112(self):
        specs = lookup_known_specs("Volkswagen", "GTI")
        assert specs is not None
        assert specs["bolt_pattern"] == "5x112"

    def test_bmw_year_resolution_m3_2020(self):
        specs = lookup_known_specs("BMW", "M3", year=2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5x112"  # G80

    def test_bmw_year_resolution_m3_2005(self):
        specs = lookup_known_specs("BMW", "M3", year=2005)
        assert specs is not None
        assert specs["bolt_pattern"] == "5x120"  # E46


# ---------------------------------------------------------------------------
# Bolt Pattern Lookup Table Tests
# ---------------------------------------------------------------------------


class TestBoltPatternLookup:
    def test_known_vehicle(self):
        assert lookup_bolt_pattern("Honda", "Civic", 2020) == "5X114.3"

    def test_unknown_vehicle(self):
        assert lookup_bolt_pattern("Unknown", "Car", 2020) is None


# ---------------------------------------------------------------------------
# Vehicle Spec Lookup Tests
# ---------------------------------------------------------------------------


class TestVehicleSpecLookup:
    def test_returns_bolt_pattern_and_hub_bore(self):
        specs = lookup_vehicle_specs("Honda", "Civic", 2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5X114.3"
        assert specs["hub_bore"] == 64.1

    def test_bmw_has_hub_bore(self):
        specs = lookup_vehicle_specs("BMW", "3 Series", 2020)
        assert specs is not None
        assert specs["hub_bore"] == 66.5  # G20 generation (2019-2025)

    def test_unknown_vehicle_returns_none(self):
        assert lookup_vehicle_specs("Unknown", "Car", 2020) is None

    def test_backward_compat_bolt_pattern(self):
        """lookup_bolt_pattern should delegate to lookup_vehicle_specs."""
        assert lookup_bolt_pattern("Toyota", "Camry", 2020) == "5X114.3"


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_patterns(self):
        assert validate_bolt_pattern("5x120")
        assert validate_bolt_pattern("4x100")
        assert validate_bolt_pattern("5x114.3")
        assert validate_bolt_pattern("6x139.7")

    def test_invalid_patterns(self):
        assert not validate_bolt_pattern("invalid")
        assert not validate_bolt_pattern("5x")
        assert not validate_bolt_pattern("")


# ---------------------------------------------------------------------------
# Scoring Tests
# ---------------------------------------------------------------------------


class TestScoring:
    def _make_wheel(self, **overrides) -> KanseiWheel:
        defaults = {
            "id": 1,
            "model": "SEVEN",
            "diameter": 18.0,
            "width": 9.5,
            "bolt_pattern": "5x120",
            "wheel_offset": 22,
            "in_stock": True,
            "center_bore": 73.1,
        }
        defaults.update(overrides)
        return KanseiWheel(**defaults)

    def _make_vehicle(self, **overrides) -> VehicleSpecs:
        defaults = {
            "year": 2005,
            "make": "BMW",
            "model": "M3",
            "bolt_pattern": "5x120",
            "oem_diameter": 18.0,
            "oem_width": 9.0,
            "oem_offset": 25,
            "hub_bore": 72.6,
        }
        defaults.update(overrides)
        return VehicleSpecs(**defaults)

    def test_perfect_match(self):
        wheel = self._make_wheel(diameter=18, wheel_offset=25)
        vehicle = self._make_vehicle(oem_diameter=18, oem_offset=25)
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score >= 0.9

    def test_bolt_pattern_mismatch(self):
        wheel = self._make_wheel(bolt_pattern="4x100")
        vehicle = self._make_vehicle(bolt_pattern="5x120")
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score == 0.0

    def test_large_offset_delta_penalty(self):
        wheel = self._make_wheel(wheel_offset=0)
        vehicle = self._make_vehicle(oem_offset=45)
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score < 0.8

    def test_out_of_stock_penalty(self):
        wheel = self._make_wheel(in_stock=False)
        vehicle = self._make_vehicle()
        result_oos = score_fitment(wheel, vehicle)
        wheel_is = self._make_wheel(in_stock=True)
        result_is = score_fitment(wheel_is, vehicle)
        assert result_oos.fitment_score < result_is.fitment_score

    # --- Hub bore tests (per-wheel bore via wheel.center_bore) ---

    def test_hub_bore_hard_reject_when_wheel_bore_smaller(self):
        """Wheel bore < vehicle hub → score 0.0, not compatible."""
        wheel = self._make_wheel(center_bore=73.1)
        # Vehicle hub bore larger than wheel bore (e.g. truck with 87.1mm hub)
        vehicle = self._make_vehicle(hub_bore=87.1, bolt_pattern="5x120")
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score == 0.0
        assert (
            "not compatible" in result.notes[0].lower()
            or "incompatible" in result.notes[0].lower()
        )

    def test_hub_bore_perfect_match(self):
        """Wheel bore == vehicle hub → perfect hub-centric fit note."""
        wheel = self._make_wheel(center_bore=72.6)
        vehicle = self._make_vehicle(hub_bore=72.6)
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score > 0.0
        assert any("perfect hub-centric" in n.lower() for n in result.notes)

    def test_hub_bore_rings_required(self):
        """Wheel bore > vehicle hub → hub-centric rings required note."""
        wheel = self._make_wheel(center_bore=73.1)
        vehicle = self._make_vehicle(hub_bore=64.1)
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score > 0.0
        assert any("hub-centric rings" in n.lower() for n in result.notes)

    def test_hub_bore_uses_wheel_center_bore(self):
        """score_fitment uses wheel.center_bore for hub bore comparison."""
        # Truck wheel with 106.1mm bore on a Tacoma with 106.1mm hub
        wheel = self._make_wheel(
            center_bore=106.1, bolt_pattern="6x139.7", diameter=17.0
        )
        vehicle = self._make_vehicle(
            hub_bore=106.1, bolt_pattern="6x139.7", oem_diameter=16.0
        )
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score > 0.0
        assert any("perfect hub-centric" in n.lower() for n in result.notes)

    def test_hub_bore_none_skips_check(self):
        """When vehicle has no hub_bore, hub bore check is skipped."""
        wheel = self._make_wheel()
        vehicle = self._make_vehicle(hub_bore=None)
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score > 0.0
        assert not any("hub" in n.lower() for n in result.notes)

    def test_score_includes_poke(self):
        """score_fitment should include poke calculation when OEM width is known."""
        wheel = self._make_wheel(width=9.5, wheel_offset=22)
        vehicle = self._make_vehicle(oem_width=9.0, oem_offset=25)
        result = score_fitment(wheel, vehicle)
        assert result.poke is not None
        assert isinstance(result.poke.poke_mm, float)

    def test_score_includes_confidence(self):
        """score_fitment should include confidence level."""
        wheel = self._make_wheel()
        vehicle = self._make_vehicle()
        result = score_fitment(wheel, vehicle)
        assert result.confidence in ("high", "medium", "low")
        assert result.confidence_reason != ""

    def test_score_includes_tire_recommendation(self):
        """score_fitment should include tire recommendation when OEM tire is known."""
        wheel = self._make_wheel(diameter=18.0, width=9.0)
        vehicle = self._make_vehicle(oem_tire_front="225/45R18")
        result = score_fitment(wheel, vehicle)
        assert result.tire_recommendation is not None
        assert result.tire_recommendation.size != ""

    def test_brake_clearance_hard_reject(self):
        """Wheel below min diameter should get score 0 (hard reject)."""
        wheel = self._make_wheel(diameter=16.0)
        vehicle = self._make_vehicle(
            oem_diameter=18.0, min_wheel_diameter=17.0, is_performance_trim=True
        )
        result = score_fitment(wheel, vehicle)
        assert result.fitment_score == 0.0
        assert not result.brake_clearance_ok
        assert result.brake_clearance_note is not None

    def test_mods_needed_for_hub_rings(self):
        """Hub rings should appear in mods_needed."""
        wheel = self._make_wheel(center_bore=73.1)
        vehicle = self._make_vehicle(hub_bore=64.1)
        result = score_fitment(wheel, vehicle)
        assert any("hub-centric" in m.lower() for m in result.mods_needed)

    def test_staggered_note(self):
        """Staggered stock vehicles should get a note."""
        wheel = self._make_wheel()
        vehicle = self._make_vehicle(is_staggered_stock=True)
        result = score_fitment(wheel, vehicle)
        assert any("staggered" in n.lower() for n in result.notes)


# ---------------------------------------------------------------------------
# Tire Recommendation Tests
# ---------------------------------------------------------------------------


class TestTireRecommendation:
    def test_basic_tire_calc(self):
        rec = calculate_tire_recommendation(18.0, 8.0, "225/45R18")
        assert rec is not None
        assert rec.width_mm > 0
        assert rec.aspect_ratio > 0
        assert rec.sidewall_mm > 0
        assert rec.overall_diameter_mm > 0

    def test_returns_none_for_no_oem_tire(self):
        assert calculate_tire_recommendation(18.0, 8.0, None) is None

    def test_returns_none_for_bad_tire_string(self):
        assert calculate_tire_recommendation(18.0, 8.0, "not-a-tire") is None

    def test_diameter_within_5_pct_of_oem(self):
        """Recommended tire overall diameter should be within 5% of OEM."""
        rec = calculate_tire_recommendation(18.0, 9.0, "225/45R18")
        assert rec is not None
        assert abs(rec.oem_diameter_diff_pct) < 5.0

    def test_wider_wheel_gets_wider_tire(self):
        rec_narrow = calculate_tire_recommendation(18.0, 7.5, "225/45R18")
        rec_wide = calculate_tire_recommendation(18.0, 10.0, "225/45R18")
        assert rec_narrow is not None and rec_wide is not None
        assert rec_wide.width_mm >= rec_narrow.width_mm

    def test_upsized_diameter(self):
        """Going from 17 to 18 should still give a reasonable tire."""
        rec = calculate_tire_recommendation(18.0, 8.0, "215/45R17")
        assert rec is not None
        assert rec.aspect_ratio < 50  # Should be lower profile


# ---------------------------------------------------------------------------
# Poke Calculation Tests
# ---------------------------------------------------------------------------


class TestPokeCalculation:
    def test_flush_when_same_specs(self):
        poke = calculate_poke(8.0, 35, 8.0, 35)
        assert poke is not None
        assert poke.poke_mm == 0.0
        assert poke.stance_label == "flush"

    def test_poke_with_lower_offset(self):
        """Lower offset than OEM = more poke."""
        poke = calculate_poke(8.0, 40, 8.0, 25)
        assert poke is not None
        assert poke.poke_mm > 0
        assert poke.stance_label in ("mild poke", "moderate poke", "aggressive")

    def test_tuck_with_higher_offset(self):
        """Higher offset than OEM = tuck."""
        poke = calculate_poke(8.0, 25, 8.0, 45)
        assert poke is not None
        assert poke.poke_mm < 0
        assert poke.stance_label in ("mild tuck", "moderate tuck", "deep tuck")

    def test_wider_wheel_adds_poke(self):
        """Wider wheel at same offset adds poke."""
        poke = calculate_poke(8.0, 35, 10.0, 35)
        assert poke is not None
        assert poke.poke_mm > 0

    def test_returns_none_without_oem_data(self):
        assert calculate_poke(None, 35, 8.0, 35) is None
        assert calculate_poke(8.0, None, 8.0, 35) is None

    def test_mild_poke_label(self):
        """3-10mm poke should be 'mild poke'."""
        # 5mm poke: oem_offset=40, new_offset=35, same width
        poke = calculate_poke(8.0, 40, 8.0, 35)
        assert poke is not None
        assert poke.poke_mm == 5.0
        assert poke.stance_label == "mild poke"

    def test_moderate_poke_label(self):
        """10-20mm poke should be 'moderate poke'."""
        # 15mm poke
        poke = calculate_poke(8.0, 40, 8.0, 25)
        assert poke is not None
        assert poke.poke_mm == 15.0
        assert poke.stance_label == "moderate poke"

    def test_aggressive_label(self):
        """Over 20mm poke should be 'aggressive'."""
        # 25mm poke
        poke = calculate_poke(8.0, 40, 8.0, 15)
        assert poke is not None
        assert poke.poke_mm == 25.0
        assert poke.stance_label == "aggressive"

    def test_deep_tuck_label(self):
        """Over 20mm tuck should be 'deep tuck'."""
        # -25mm poke (deep tuck)
        poke = calculate_poke(8.0, 15, 8.0, 40)
        assert poke is not None
        assert poke.poke_mm == -25.0
        assert poke.stance_label == "deep tuck"


# ---------------------------------------------------------------------------
# Brake Clearance Tests
# ---------------------------------------------------------------------------


class TestBrakeCheck:
    def test_clears_when_above_min(self):
        ok, note = check_brake_clearance(18.0, 17.0, False, 17.0)
        assert ok is True
        assert note is None

    def test_fails_below_min(self):
        ok, note = check_brake_clearance(16.0, 17.0, False, 17.0)
        assert ok is False
        assert note is not None
        assert "minimum" in note.lower() or "not clear" in note.lower()

    def test_performance_downsize_warning(self):
        """Performance trim downsizing returns ok=True with warning."""
        ok, note = check_brake_clearance(17.0, None, True, 18.0)
        assert ok is True
        assert note is not None
        assert "performance" in note.lower() or "caliper" in note.lower()

    def test_15_inch_warning(self):
        """15 inch wheels get a hard reject warning."""
        ok, note = check_brake_clearance(15.0, None, False, None)
        assert ok is False
        assert note is not None
        assert "15" in note

    def test_ok_when_no_constraints(self):
        """16 inch wheel with no min and no performance trim should be ok."""
        ok, note = check_brake_clearance(16.0, None, False, None)
        assert ok is True
        assert note is None

    def test_emoji_in_brake_notes(self):
        """Brake clearance notes should include emoji prefixes."""
        ok, note = check_brake_clearance(16.0, 17.0, False, 17.0)
        assert ok is False
        assert note is not None
        assert "❌" in note

        ok2, note2 = check_brake_clearance(17.0, None, True, 18.0)
        assert ok2 is True
        assert note2 is not None
        assert "⚠️" in note2


# ---------------------------------------------------------------------------
# Vehicle Confidence Tests
# ---------------------------------------------------------------------------


class TestVehicleConfidence:
    def test_high_with_chassis_offset_and_tire(self):
        """High confidence requires chassis_code + oem_offset + oem_tire."""
        v = VehicleSpecs(
            year=2020,
            make="BMW",
            model="M3",
            bolt_pattern="5x120",
            chassis_code="G80",
            hub_bore=72.6,
            oem_diameter=18.0,
            oem_offset=26,
            oem_tire_front="255/35ZR18",
        )
        level, reason = vehicle_confidence(v)
        assert level == "high"
        assert "G80" in reason

    def test_medium_with_offset_only(self):
        """Medium confidence when offset is known but no chassis or tire."""
        v = VehicleSpecs(
            year=2020,
            make="Honda",
            model="Civic",
            bolt_pattern="5x114.3",
            hub_bore=64.1,
            oem_diameter=16.0,
            oem_offset=45,
        )
        level, _ = vehicle_confidence(v)
        assert level == "medium"

    def test_medium_with_chassis_but_no_tire(self):
        """Medium confidence when chassis_code + offset but missing tire."""
        v = VehicleSpecs(
            year=2020,
            make="BMW",
            model="M3",
            bolt_pattern="5x120",
            chassis_code="G80",
            hub_bore=72.6,
            oem_diameter=18.0,
            oem_offset=26,
        )
        level, _ = vehicle_confidence(v)
        assert level == "medium"

    def test_low_without_specifics(self):
        v = VehicleSpecs(
            year=2020,
            make="Unknown",
            model="Car",
            bolt_pattern="5x114.3",
        )
        level, reason = vehicle_confidence(v)
        assert level == "low"
        assert "verification" in reason.lower()


# ---------------------------------------------------------------------------
# Trim-Aware Lookup Tests
# ---------------------------------------------------------------------------


class TestTrimAwareLookup:
    def test_civic_type_r_gets_5x120(self):
        # DB stores as model="Civic Type R", not trim="Type R" on "Civic"
        specs = lookup_vehicle_specs("Honda", "Civic Type R", 2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5X120"

    def test_civic_base_gets_5x114(self):
        specs = lookup_vehicle_specs("Honda", "Civic", 2020)
        assert specs is not None
        assert specs["bolt_pattern"] == "5X114.3"

    def test_wrx_sti_is_performance(self):
        specs = lookup_vehicle_specs("Subaru", "WRX", 2020, trim="STI")
        assert specs is not None
        assert specs["is_performance_trim"] is True

    def test_mustang_gt_is_staggered(self):
        specs = lookup_vehicle_specs("Ford", "Mustang", 2020, trim="GT")
        assert specs is not None
        assert specs["is_staggered_stock"] is True

    def test_elantra_n_gets_chassis_code(self):
        specs = lookup_vehicle_specs("Hyundai", "Elantra", 2023, trim="N")
        assert specs is not None
        assert specs["chassis_code"] == "CN7"

    def test_no_trim_matches(self):
        """Entries without a specific trim should match when no trim specified."""
        specs = lookup_vehicle_specs("BMW", "3 Series", 2015)
        assert specs is not None
        # DB uses NULL for trim (not "*" like the old hardcoded list)
        assert specs["bolt_pattern"] == "5X120"

    def test_e39_m5_lookup(self):
        """E39 M5 should have correct specs from DB."""
        specs = lookup_vehicle_specs("BMW", "M5", 2001)
        assert specs is not None
        assert specs["bolt_pattern"] == "5X120"
        assert specs["hub_bore"] == 74.1  # E39 platform = 74.1mm
        assert specs["is_staggered_stock"] is True
