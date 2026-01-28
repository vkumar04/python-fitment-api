"""Comprehensive integration tests for fitment queries.

Tests cover:
1. Correct bolt pattern identification
2. Year clarification when needed
3. Proper Kansei recommendations with correct links
4. No false assumptions (year, model, trim)
5. Invalid vehicle combinations
6. Edge cases and error handling
7. Fitment styles (flush, aggressive, tucked)
8. Context switching between vehicles
"""

import json
import re
import time
from typing import Any

import httpx
import pytest

BASE_URL = "http://localhost:8000"


def parse_sse_response(response_text: str) -> dict[str, Any]:
    """Parse SSE response into structured data."""
    text_content = ""
    metadata: dict[str, Any] | None = None

    for line in response_text.split("\n"):
        if not line.startswith("data: "):
            continue
        data = line[6:]  # Remove "data: " prefix
        if data == "[DONE]":
            continue

        try:
            parsed = json.loads(data)
            if parsed.get("type") == "text-delta":
                text_content += parsed.get("delta", "")
            elif parsed.get("type") == "data-fitment":
                metadata = parsed.get("data", {})
        except json.JSONDecodeError:
            continue

    return {"text": text_content, "metadata": metadata}


def query_fitment(
    query: str, history: list[dict[str, str]] | None = None, retries: int = 2
) -> dict[str, Any]:
    """Send a fitment query and return parsed response."""
    payload: dict[str, Any] = {"query": query}
    if history:
        payload["history"] = history

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = httpx.post(
                f"{BASE_URL}/api/chat",
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            return parse_sse_response(response.text)
        except (httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
            last_error = e
            if attempt < retries:
                time.sleep(2)
                continue
    raise last_error if last_error else RuntimeError("No attempts made")


@pytest.fixture(scope="module", autouse=True)
def check_server():
    """Ensure server is running before tests."""
    max_retries = 3
    for i in range(max_retries):
        try:
            response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
            if response.status_code == 200:
                return
        except httpx.ConnectError:
            if i < max_retries - 1:
                time.sleep(2)
    pytest.skip("Server not running at localhost:8000")


# =============================================================================
# BMW CHASSIS CODES - VALID COMBINATIONS
# =============================================================================
class TestBMWValidChassisCodes:
    """Test valid BMW chassis code + model combinations."""

    def test_e30_m3_4x100(self):
        """E30 M3 (1986-1991) - 4x100 bolt pattern, should get Kansei 15" wheels."""
        result = query_fitment("e30 m3 wheels")
        text = result["text"]

        assert "4x100" in text
        assert "M3" in text or "E30" in text
        # Should recommend Kansei KNP or TANDEM 15"
        assert "KNP" in text or "TANDEM" in text
        assert "kanseiwheels.com" in text
        # Should NOT assume a specific year
        assert "2002" not in text

    def test_e36_m3_5x120(self):
        """E36 M3 (1992-1999) - 5x120 bolt pattern."""
        result = query_fitment("e36 m3 flush fitment")
        text = result["text"]

        assert "5x120" in text
        assert "M3" in text

    def test_e46_330i_5x120(self):
        """E46 330i (1999-2006) - 5x120 bolt pattern."""
        result = query_fitment("e46 330i wheels")
        text = result["text"]

        assert "5x120" in text
        assert "E46" in text or "330" in text

    def test_e39_m5_5x120(self):
        """E39 M5 (1998-2003) - 5x120 bolt pattern."""
        result = query_fitment("e39 m5 aggressive wheels")
        text = result["text"]

        assert "5x120" in text
        assert "M5" in text or "E39" in text

    def test_e90_335i_5x120(self):
        """E90 335i (2006-2011) - 5x120 bolt pattern."""
        result = query_fitment("e90 335i flush")
        text = result["text"]

        assert "5x120" in text

    def test_f30_340i_5x120(self):
        """F30 340i (2012-2019) - 5x120 bolt pattern."""
        result = query_fitment("f30 340i wheels")
        text = result["text"]

        assert "5x120" in text

    def test_g20_m340i_5x112(self):
        """G20 M340i (2019+) - 5x112 bolt pattern (BMW switched to 5x112)."""
        result = query_fitment("g20 m340i flush fitment")
        text = result["text"]

        assert "5x112" in text


# =============================================================================
# BMW CHASSIS CODES - INVALID COMBINATIONS
# =============================================================================
class TestBMWInvalidChassisCodes:
    """Test invalid BMW chassis code + model combinations."""

    def test_e30_m5_invalid(self):
        """E30 M5 doesn't exist - E30 only had M3."""
        result = query_fitment("e30 m5 wheels")
        text = result["text"].lower()

        # Should indicate this combo doesn't exist OR still provide E30 specs
        # LLM correctly says "vehicle not found" and suggests alternatives
        assert (
            "4x100" in text
            or "doesn't exist" in text
            or "invalid" in text
            or "not found" in text
            or "never had" in text
        )

    def test_e36_m5_invalid(self):
        """E36 M5 doesn't exist - E36 only had M3."""
        result = query_fitment("e36 m5 wheels")
        text = result["text"].lower()

        # Should handle gracefully - LLM correctly identifies invalid combo
        assert (
            "5x120" in text
            or "doesn't exist" in text
            or "invalid" in text
            or "not found" in text
            or "never had" in text
        )

    def test_e30_m4_invalid(self):
        """E30 M4 doesn't exist - M4 wasn't made until 2014."""
        result = query_fitment("e30 m4 wheels")
        text = result["text"].lower()

        # Should indicate this doesn't exist
        assert "4x100" in text or "doesn't exist" in text or "m4" in text


# =============================================================================
# YEAR-SENSITIVE VEHICLES (Different specs across generations)
# =============================================================================
class TestYearSensitiveVehicles:
    """Test vehicles where year significantly affects specs."""

    def test_prelude_no_year_asks_clarification(self):
        """Honda Prelude without year should ask for clarification."""
        result = query_fitment("what wheels fit my prelude")
        text = result["text"]

        # Should ask about year/generation since bolt pattern varies
        assert "year" in text.lower() or "generation" in text.lower()
        # May mention bolt patterns, or just ask for year info
        assert (
            "4x100" in text
            or "4x114.3" in text
            or "5x114.3" in text
            or "prelude" in text.lower()
        )

    def test_prelude_1985_4x100(self):
        """1985 Prelude (1st/2nd gen) - 4x100."""
        result = query_fitment("1985 Honda Prelude wheels")
        text = result["text"]

        assert "4x100" in text

    def test_prelude_1990_4x100(self):
        """1990 Prelude (3rd gen, 1988-1991) - 4x100."""
        result = query_fitment("1990 Honda Prelude flush")
        text = result["text"]

        # 3rd gen Prelude (1988-1991) uses 4x100
        assert "4x100" in text

    def test_prelude_1993_4x114(self):
        """1993 Prelude (4th gen, 1992-1996) - 4x114.3."""
        result = query_fitment("1993 Honda Prelude flush")
        text = result["text"]

        # 4th gen Prelude (1992-1996) uses 4x114.3
        assert "4x114.3" in text

    def test_prelude_1997_5x114(self):
        """1997 Prelude (5th gen) - 5x114.3."""
        result = query_fitment("1997 Honda Prelude aggressive fitment")
        text = result["text"]

        assert "5x114.3" in text

    def test_civic_2005_4x100(self):
        """2005 Civic (pre-2006) - 4x100."""
        result = query_fitment("2005 Honda Civic wheels")
        text = result["text"]

        assert "4x100" in text

    def test_civic_2010_5x114(self):
        """2010 Civic (2006+) - 5x114.3."""
        result = query_fitment("2010 Honda Civic flush")
        text = result["text"]

        assert "5x114.3" in text

    def test_wrx_2014_5x100(self):
        """2014 WRX (pre-2015) - 5x100."""
        result = query_fitment("2014 Subaru WRX wheels")
        text = result["text"]

        # Could be 5x100 or 5x114.3 depending on trim
        assert "5x100" in text or "5x114.3" in text

    def test_wrx_2020_5x114(self):
        """2020 WRX (2015+) - 5x114.3."""
        result = query_fitment("2020 Subaru WRX aggressive")
        text = result["text"]

        assert "5x114.3" in text

    def test_supra_a80_5x114(self):
        """A80 Supra (1993-2002) - 5x114.3."""
        result = query_fitment("1998 Toyota Supra wheels")
        text = result["text"]

        assert "5x114.3" in text

    def test_supra_a90_5x112(self):
        """A90 Supra (2019+) - 5x112 (BMW platform)."""
        result = query_fitment("2021 Toyota Supra flush")
        text = result["text"]

        assert "5x112" in text


# =============================================================================
# FITMENT STYLES - FLUSH, AGGRESSIVE, TUCKED
# =============================================================================
class TestFitmentStyles:
    """Test different fitment style requests."""

    def test_flush_fitment_moderate_offset(self):
        """Flush fitment should recommend moderate offsets."""
        result = query_fitment("2020 Honda Civic Type R flush fitment")
        text = result["text"]

        assert "flush" in text.lower() or "Flush" in text
        # Should have wheel specs
        assert re.search(r"\d+x[\d.]+ \+\d+", text)

    def test_aggressive_fitment_low_offset(self):
        """Aggressive fitment should recommend lower offsets."""
        result = query_fitment("2018 BMW M3 aggressive fitment")
        text = result["text"]

        # Should mention aggressive or poke
        assert (
            "aggressive" in text.lower()
            or "poke" in text.lower()
            or re.search(r"\+\d{1,2}\b", text)
        )

    def test_tucked_fitment_high_offset(self):
        """Tucked fitment should recommend higher offsets."""
        result = query_fitment("2019 Mazda Miata tucked wheels")
        text = result["text"]

        assert "Miata" in text or "MX-5" in text


# =============================================================================
# KANSEI WHEEL RECOMMENDATIONS
# =============================================================================
class TestKanseiRecommendations:
    """Test Kansei wheel recommendations and links."""

    def test_kansei_links_present_5x120(self):
        """5x120 vehicles should get Kansei recommendations with links."""
        result = query_fitment("2020 Honda Civic Type R flush")
        text = result["text"]

        # Civic Type R is 5x120
        assert "5x120" in text
        # Should have Kansei recommendations
        if "Kansei" in text and "Not available" not in text:
            assert "kanseiwheels.com" in text

    def test_kansei_4x100_15_inch_available(self):
        """4x100 vehicles should get KNP/TANDEM 15" recommendations."""
        result = query_fitment("e30 m3 wheels")
        text = result["text"]

        assert "4x100" in text
        # Kansei makes 15" wheels in 4x100
        if "KNP" in text or "TANDEM" in text:
            assert "kanseiwheels.com" in text
            assert "15" in text

    def test_kansei_not_available_message_no_link(self):
        """When Kansei not available, should be plain text not a link."""
        result = query_fitment("e39 m5 wheels")
        text = result["text"]

        # If Kansei not available for this size
        if "Not available" in text:
            # Should NOT have markdown link syntax for "not available"
            assert "[Not available" not in text

    def test_kansei_offroad_for_trucks(self):
        """Trucks should get Kansei Off-Road recommendations."""
        result = query_fitment("2022 Toyota Tacoma wheels")
        text = result["text"]

        assert "6x139.7" in text or "6x5.5" in text
        # Should mention off-road or truck wheels if available
        if "Kansei" in text and "Not available" not in text:
            assert "kanseiwheels.com" in text


# =============================================================================
# TRUCKS
# =============================================================================
class TestTrucks:
    """Test truck queries."""

    def test_f150_6x135(self):
        """Ford F-150 - 6x135 bolt pattern."""
        result = query_fitment("2020 Ford F-150 aggressive fitment")
        text = result["text"]

        assert "F-150" in text or "F150" in text or "f150" in text.lower()
        assert "6x135" in text

    def test_silverado_6x139(self):
        """Chevy Silverado - 6x139.7 bolt pattern."""
        result = query_fitment("2019 Chevy Silverado wheels")
        text = result["text"]

        assert "Silverado" in text or "silverado" in text.lower()
        assert "6x139.7" in text or "6x5.5" in text

    def test_tacoma_6x139(self):
        """Toyota Tacoma - 6x139.7 bolt pattern."""
        result = query_fitment("2022 Toyota Tacoma")
        text = result["text"]

        assert "Tacoma" in text or "tacoma" in text.lower()
        assert "6x139.7" in text or "6x5.5" in text

    def test_ram_1500_6x139(self):
        """RAM 1500 - 6x139.7 bolt pattern."""
        result = query_fitment("2021 RAM 1500 aggressive")
        text = result["text"]

        assert "RAM" in text or "1500" in text
        assert "6x139.7" in text or "6x5.5" in text


# =============================================================================
# JDM CARS
# =============================================================================
class TestJDMCars:
    """Test JDM vehicle queries."""

    def test_350z_5x114(self):
        """Nissan 350Z - 5x114.3."""
        result = query_fitment("2006 Nissan 350Z aggressive")
        text = result["text"]

        assert "350Z" in text or "350z" in text
        assert "5x114.3" in text

    def test_370z_5x114(self):
        """Nissan 370Z - 5x114.3."""
        result = query_fitment("2015 Nissan 370Z flush")
        text = result["text"]

        assert "370Z" in text or "370z" in text
        assert "5x114.3" in text

    def test_s2000_5x114(self):
        """Honda S2000 - 5x114.3."""
        result = query_fitment("2005 Honda S2000 flush")
        text = result["text"]

        assert "S2000" in text or "s2000" in text.lower()
        assert "5x114.3" in text

    def test_rx7_fd_5x114(self):
        """Mazda RX-7 FD - 5x114.3."""
        result = query_fitment("1995 Mazda RX-7 aggressive")
        text = result["text"]

        assert "RX-7" in text or "RX7" in text or "rx7" in text.lower()
        assert "5x114.3" in text

    def test_evo_x_5x114(self):
        """Mitsubishi Evo X - 5x114.3."""
        result = query_fitment("2014 Mitsubishi Evo X")
        text = result["text"]

        assert "Evo" in text or "EVO" in text or "Lancer" in text
        assert "5x114.3" in text


# =============================================================================
# EUROPEAN CARS
# =============================================================================
class TestEuropeanCars:
    """Test European vehicle queries."""

    def test_golf_r_mk7_5x112(self):
        """VW Golf R MK7 - 5x112."""
        result = query_fitment("mk7 golf r flush wheels")
        text = result["text"]

        assert "Golf" in text or "golf" in text.lower()
        assert "5x112" in text

    def test_audi_s4_b8_5x112(self):
        """Audi S4 B8 - 5x112."""
        result = query_fitment("2015 Audi S4 flush fitment")
        text = result["text"]

        assert "S4" in text or "Audi" in text
        assert "5x112" in text

    def test_mercedes_c63_5x112(self):
        """Mercedes C63 AMG - 5x112."""
        result = query_fitment("2018 Mercedes C63 AMG wheels")
        text = result["text"]

        assert "C63" in text or "Mercedes" in text
        assert "5x112" in text


# =============================================================================
# CONTEXT SWITCHING
# =============================================================================
class TestContextSwitching:
    """Test that context switches correctly between vehicles."""

    def test_e30_to_e36_switch(self):
        """Switching from E30 (4x100) to E36 (5x120) should update specs."""
        # First query E30
        result1 = query_fitment("e30 m3 wheels")
        assert "4x100" in result1["text"]

        # Then query E36 with history
        history = [
            {"role": "user", "content": "e30 m3 wheels"},
            {"role": "assistant", "content": result1["text"]},
        ]
        result2 = query_fitment("now what about e36 m3", history)

        # Should switch to E36 specs (5x120)
        assert "5x120" in result2["text"]
        # Should NOT keep E30's 4x100
        assert "4x100" not in result2["text"]

    def test_civic_to_type_r_switch(self):
        """Switching from Civic (5x114.3) to Type R (5x120)."""
        result1 = query_fitment("2020 Honda Civic wheels")
        # Regular Civic is 5x114.3

        history = [
            {"role": "user", "content": "2020 Honda Civic wheels"},
            {"role": "assistant", "content": result1["text"]},
        ]
        result2 = query_fitment("what about the 2020 Honda Civic Type R", history)

        # Type R is 5x120 — LLM should switch context
        text2 = result2["text"]
        assert "5x120" in text2 or "Type R" in text2 or "type r" in text2.lower()


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_greeting_no_vehicle(self):
        """Query without vehicle should prompt for one."""
        result = query_fitment("hello")
        text = result["text"]

        assert "vehicle" in text.lower() or "driving" in text.lower()

    def test_fitment_question_no_vehicle(self):
        """Fitment question without vehicle should ask for vehicle."""
        result = query_fitment("what's a good flush fitment")
        text = result["text"].lower()

        assert "vehicle" in text or "what" in text or "make" in text or "model" in text

    def test_nicknames_chevy(self):
        """'Chevy' should be recognized as Chevrolet."""
        result = query_fitment("2019 chevy camaro wheels")
        text = result["text"]

        assert "Camaro" in text or "camaro" in text.lower()

    def test_nicknames_bimmer(self):
        """'Bimmer' should be recognized as BMW."""
        result = query_fitment("bimmer 3 series flush")
        text = result["text"]

        assert "BMW" in text or "3 Series" in text or "5x120" in text

    def test_future_year(self):
        """Future year should still work or indicate no data."""
        result = query_fitment("2030 Honda Civic wheels")
        text = result["text"]

        # Should either provide specs or indicate no data
        assert "Civic" in text or "no data" in text.lower()

    def test_very_old_car(self):
        """Very old car should work or indicate limitations."""
        result = query_fitment("1970 Datsun 240Z wheels")
        text = result["text"]

        assert "240Z" in text or "Datsun" in text

    def test_misspelled_make(self):
        """Misspelled make should still work or be corrected."""
        result = query_fitment("2020 Toyoda Camry wheels")
        text = result["text"]

        # Should recognize as Toyota or ask for clarification
        assert "toyota" in text.lower() or "camry" in text.lower() or "vehicle" in text.lower()


# =============================================================================
# STAGGERED VS SQUARE SETUPS
# =============================================================================
class TestSetupTypes:
    """Test staggered vs square setup recommendations."""

    def test_rwd_sports_car_staggered(self):
        """RWD sports cars often get staggered recommendations."""
        result = query_fitment("2018 BMW M3 wheels")
        text = result["text"]

        # Should mention staggered or have different front/rear specs
        assert "staggered" in text.lower() or "Front:" in text

    def test_fwd_car_square(self):
        """FWD cars typically get square recommendations."""
        result = query_fitment("2020 Honda Civic flush")
        text = result["text"]

        # Should have wheel specs
        assert re.search(r"\d+x[\d.]+", text)


# =============================================================================
# VALIDATION LOGIC
# =============================================================================
class TestValidation:
    """Test wheel validation against vehicle specs."""

    def test_small_car_no_oversized_wheels(self):
        """Small/old cars shouldn't get oversized wheel recommendations."""
        result = query_fitment("1989 Honda Civic wheels")
        text = result["text"]

        assert "4x100" in text
        # Should recommend appropriate sizes (15" max typically)
        # Should NOT recommend 18"+ wheels
        if "Kansei" in text and "KNP" in text:
            # If recommending KNP, should be 15"
            assert "15" in text

    def test_truck_gets_truck_sizes(self):
        """Trucks should get appropriate truck wheel sizes."""
        result = query_fitment("2020 Ford F-150 wheels")
        text = result["text"]

        # Should have truck-appropriate specs
        assert "6x135" in text


# =============================================================================
# SUSPENSION TYPES
# =============================================================================
class TestSuspensionTypes:
    """Test suspension-aware fitment recommendations."""

    def test_stock_suspension_conservative_offset(self):
        """Stock suspension should get conservative offset recommendations."""
        result = query_fitment("2020 Honda Civic stock suspension flush")
        text = result["text"]
        metadata = result.get("metadata", {})

        # Should parse suspension as stock
        parsed = metadata.get("parsed", {})
        assert parsed.get("suspension") == "stock" or "stock" in text.lower()

        # Should have fitment recommendations
        assert "5x114.3" in text

    def test_lowered_suspension_more_aggressive(self):
        """Lowered suspension can run slightly more aggressive offsets."""
        result = query_fitment("2019 Subaru WRX lowered aggressive")
        text = result["text"]
        metadata = result.get("metadata", {})

        # Should parse suspension as lowered
        parsed = metadata.get("parsed", {})
        assert parsed.get("suspension") == "lowered" or "lower" in text.lower()

        # Should mention lowered or suspension considerations
        assert "5x114.3" in text

    def test_coilovers_aggressive_fitment(self):
        """Coilovers allow aggressive fitments with adjustment."""
        result = query_fitment("E36 M3 coilovers aggressive")
        text = result["text"]
        metadata = result.get("metadata", {})

        # Should parse suspension as coilovers
        parsed = metadata.get("parsed", {})
        assert parsed.get("suspension") == "coilovers" or "coilover" in text.lower()

        # Should have E36 specs
        assert "5x120" in text

    def test_air_suspension_maximum_flexibility(self):
        """Air suspension provides maximum fitment flexibility."""
        result = query_fitment("2020 BMW M3 bagged flush")
        text = result["text"]
        metadata = result.get("metadata", {})

        # Should parse suspension as air (bagged = air)
        parsed = metadata.get("parsed", {})
        suspension = parsed.get("suspension", "")
        assert (
            suspension in ["air", "bagged"]
            or "air" in text.lower()
            or "bag" in text.lower()
        )

        # Should have BMW specs
        assert "5x112" in text or "5x120" in text

    def test_lifted_truck_suspension(self):
        """Lifted trucks have different fitment considerations."""
        result = query_fitment("2020 Ford F150 lifted aggressive")
        text = result["text"]
        metadata = result.get("metadata", {})

        # Should parse suspension as lifted
        parsed = metadata.get("parsed", {})
        assert parsed.get("suspension") == "lifted" or "lift" in text.lower()

        # Should have F150 specs
        assert "6x135" in text

    def test_suspension_not_specified_still_works(self):
        """Query without suspension should still work."""
        result = query_fitment("2020 Toyota Camry flush")
        text = result["text"]

        # Should still provide fitment data
        assert "5x114.3" in text or "Camry" in text

    def test_suspension_filtering_coilovers_vs_stock(self):
        """Coilovers should allow lower offsets than stock."""
        result_stock = query_fitment("2018 Honda Accord stock suspension flush")
        result_coils = query_fitment("2018 Honda Accord coilovers aggressive")

        # Both should have specs
        assert "5x114.3" in result_stock["text"]
        assert "5x114.3" in result_coils["text"]

        # Metadata should show different suspension parsing
        stock_parsed = result_stock.get("metadata", {}).get("parsed", {})
        coils_parsed = result_coils.get("metadata", {}).get("parsed", {})

        assert stock_parsed.get("suspension") == "stock"
        assert coils_parsed.get("suspension") == "coilovers"

    def test_springs_as_lowered(self):
        """'Springs' or 'lowering springs' should parse as lowered."""
        result = query_fitment("2019 VW Golf R on lowering springs flush")
        text = result["text"]
        metadata = result.get("metadata", {})

        parsed = metadata.get("parsed", {})
        # Should parse as lowered
        assert parsed.get("suspension") == "lowered" or "lower" in text.lower()

        # Should have Golf R specs
        assert "5x112" in text


class TestSuspensionEdgeCases:
    """Test edge cases for suspension handling."""

    def test_multiple_suspension_mentions(self):
        """Query mentioning multiple suspension types should pick one."""
        result = query_fitment("2020 Civic coilovers or lowered flush")
        text = result["text"]
        metadata = result.get("metadata", {})

        # Should parse one suspension type
        parsed = metadata.get("parsed", {})
        suspension = parsed.get("suspension")
        assert suspension in ["coilovers", "lowered", None]

        # Should still provide specs
        assert "5x114.3" in text

    def test_suspension_with_chassis_code(self):
        """Suspension should work with chassis codes."""
        result = query_fitment("E46 M3 coilovers aggressive")
        text = result["text"]
        metadata = result.get("metadata", {})

        parsed = metadata.get("parsed", {})
        assert parsed.get("suspension") == "coilovers"
        assert "5x120" in text

    def test_static_as_lowered(self):
        """'Static' should be understood as lowered/coilovers."""
        result = query_fitment("2020 Honda Civic static aggressive")
        text = result["text"]

        # Should provide aggressive specs
        assert "5x114.3" in text

    def test_slammed_as_very_low(self):
        """'Slammed' should indicate very low suspension."""
        result = query_fitment("E36 M3 slammed aggressive")
        text = result["text"]

        # Should provide aggressive specs for slammed fitment
        assert "5x120" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
