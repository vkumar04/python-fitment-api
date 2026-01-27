"""Tests for the DSPy v2 pipeline."""

import asyncio
import os

import pytest

# Skip if no API keys
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
)


class TestParseVehicleInput:
    """Test the ParseVehicleInput signature."""

    def test_parse_year_make_model(self):
        """Test parsing a simple year/make/model query."""
        import dspy

        from src.services.dspy_v2.signatures import ParseVehicleInput

        # Configure DSPy
        lm = dspy.LM("openai/gpt-4o-mini", max_tokens=256)
        dspy.configure(lm=lm)

        parser = dspy.ChainOfThought(ParseVehicleInput)
        result = parser(user_input="2020 Honda Civic")

        assert result.make == "Honda"
        assert result.model == "Civic"
        assert result.year == 2020 or str(result.year) == "2020"
        assert (
            result.is_valid_input == True
            or str(result.is_valid_input).lower() == "true"
        )

    def test_parse_chassis_code(self):
        """Test parsing a chassis code query."""
        import dspy

        from src.services.dspy_v2.signatures import ParseVehicleInput

        lm = dspy.LM("openai/gpt-4o-mini", max_tokens=256)
        dspy.configure(lm=lm)

        parser = dspy.ChainOfThought(ParseVehicleInput)
        result = parser(user_input="E30 M3")

        assert result.make == "BMW"
        assert result.model == "M3"
        assert result.chassis_code is not None
        assert "E30" in str(result.chassis_code).upper()

    def test_parse_with_suspension(self):
        """Test parsing a query with suspension info."""
        import dspy

        from src.services.dspy_v2.signatures import ParseVehicleInput

        lm = dspy.LM("openai/gpt-4o-mini", max_tokens=256)
        dspy.configure(lm=lm)

        parser = dspy.ChainOfThought(ParseVehicleInput)
        result = parser(user_input="2018 WRX STI on coilovers")

        assert result.make == "Subaru"
        assert "WRX" in str(result.model)
        assert result.suspension == "coilovers"

    def test_parse_invalid_input(self):
        """Test parsing an invalid/unclear query."""
        import dspy

        from src.services.dspy_v2.signatures import ParseVehicleInput

        lm = dspy.LM("openai/gpt-4o-mini", max_tokens=256)
        dspy.configure(lm=lm)

        parser = dspy.ChainOfThought(ParseVehicleInput)
        result = parser(user_input="what wheels should I get?")

        is_valid = result.is_valid_input
        if isinstance(is_valid, str):
            is_valid = is_valid.lower() == "true"

        assert is_valid == False
        assert result.clarification_needed is not None


class TestToolsLookup:
    """Test the web search tools."""

    def test_lookup_bmw_specs(self):
        """Test looking up BMW E30 specs."""
        from src.services.dspy_v2.tools import search_vehicle_specs_web

        result = search_vehicle_specs_web(
            year=1989, make="BMW", model="M3", chassis_code="E30"
        )

        assert result["found"] == True
        assert result["bolt_pattern"] == "4x100"
        assert result["center_bore"] == 57.1

    def test_lookup_honda_specs(self):
        """Test looking up Honda Civic specs."""
        from src.services.dspy_v2.tools import search_vehicle_specs_web

        result = search_vehicle_specs_web(
            year=2020, make="Honda", model="Civic", chassis_code=None
        )

        assert result["found"] == True
        assert "114.3" in result["bolt_pattern"]  # 5x114.3


class TestFullPipeline:
    """Integration tests for the full pipeline."""

    def test_pipeline_basic_query(self):
        """Test the full pipeline with a basic query."""
        from src.services.dspy_v2 import create_pipeline

        pipeline = create_pipeline(model="openai/gpt-4o-mini")
        result = pipeline.forward("E30 M3")

        # Check we got a response
        assert result.response is not None
        assert len(result.response) > 0

        # Check parsed info
        assert result.parsed is not None
        assert result.parsed.get("make") == "BMW"
        assert result.parsed.get("model") == "M3"

        # Check specs were resolved
        assert result.specs is not None
        assert result.specs.get("bolt_pattern") == "4x100"

    def test_pipeline_invalid_vehicle(self):
        """Test pipeline handles invalid vehicle gracefully."""
        from src.services.dspy_v2 import create_pipeline

        pipeline = create_pipeline(model="openai/gpt-4o-mini")
        result = pipeline.forward("E30 M5")  # E30 M5 doesn't exist

        # Should still get a response
        assert result.response is not None

        # Validation should catch this
        validation = result.validation
        # Either invalid vehicle or needs clarification
        assert validation is not None


class TestRAGService:
    """Test the refactored RAG service."""

    def test_ask_method(self):
        """Test the ask method returns proper structure."""
        from src.services.rag_service import RAGService

        async def _run():
            service = RAGService(model="openai/gpt-4o-mini")
            return await service.ask("2020 Honda Civic")

        result = asyncio.run(_run())

        assert "response" in result
        assert "parsed" in result
        assert "specs" in result
        assert "validation" in result

        # Should have parsed the vehicle
        assert result["parsed"] is not None
        assert result["parsed"].get("make") == "Honda"


if __name__ == "__main__":
    # Run a quick test
    from src.services.dspy_v2 import create_pipeline

    pipeline = create_pipeline(model="openai/gpt-4o-mini")
    result = pipeline.forward("E30 M3")
    print(f"Response: {result.response[:100]}...")
    print("Pipeline test passed!")
