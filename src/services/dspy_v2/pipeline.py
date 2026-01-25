"""Main DSPy Pipeline for wheel fitment assistance.

This module orchestrates the entire fitment flow:
1. Parse user input → extract vehicle info
2. Resolve specs → check DB, search web if needed, validate
3. Get fitment data → community fitments + Kansei wheels
4. Validate matches → ensure wheels actually fit
5. Generate response → conversational output
"""

import json
from typing import Any

import dspy

from . import db
from .signatures import (
    GenerateFitmentResponse,
    ParseVehicleInput,
    SearchVehicleSpecs,
    ValidateFitmentMatch,
    ValidateVehicleSpecs,
)
from .tools import search_vehicle_specs_web, validate_bolt_pattern

# -----------------------------------------------------------------------------
# Training Data for Optimization
# -----------------------------------------------------------------------------

PARSE_TRAINING_DATA = [
    # Year + Make + Model
    {
        "user_input": "2020 Honda Civic",
        "year": 2020,
        "make": "Honda",
        "model": "Civic",
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "2019 BMW M3",
        "year": 2019,
        "make": "BMW",
        "model": "M3",
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "1995 Nissan 240SX",
        "year": 1995,
        "make": "Nissan",
        "model": "240SX",
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    # Chassis codes
    {
        "user_input": "E30 M3",
        "year": None,
        "make": "BMW",
        "model": "M3",
        "chassis_code": "E30",
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "e36 325i",
        "year": None,
        "make": "BMW",
        "model": "325i",
        "chassis_code": "E36",
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "E39 M5",
        "year": None,
        "make": "BMW",
        "model": "M5",
        "chassis_code": "E39",
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "FK8 Type R",
        "year": None,
        "make": "Honda",
        "model": "Civic Type R",
        "chassis_code": "FK8",
        "trim": "Type R",
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "S14 240sx",
        "year": None,
        "make": "Nissan",
        "model": "240SX",
        "chassis_code": "S14",
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    # Invalid chassis combos (still parse correctly, validation catches it)
    {
        "user_input": "E30 M5",
        "year": None,
        "make": "BMW",
        "model": "M5",
        "chassis_code": "E30",
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "E36 M5",
        "year": None,
        "make": "BMW",
        "model": "M5",
        "chassis_code": "E36",
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    # With suspension
    {
        "user_input": "2018 WRX STI on coilovers",
        "year": 2018,
        "make": "Subaru",
        "model": "WRX",
        "chassis_code": None,
        "trim": "STI",
        "suspension": "coilovers",
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "E46 M3 lowered",
        "year": None,
        "make": "BMW",
        "model": "M3",
        "chassis_code": "E46",
        "trim": None,
        "suspension": "lowered",
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "bagged civic",
        "year": None,
        "make": "Honda",
        "model": "Civic",
        "chassis_code": None,
        "trim": None,
        "suspension": "air",
        "fitment_style": None,
        "is_valid_input": True,
    },
    # With fitment style
    {
        "user_input": "2020 Civic flush fitment",
        "year": 2020,
        "make": "Honda",
        "model": "Civic",
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": "flush",
        "is_valid_input": True,
    },
    {
        "user_input": "E30 aggressive stance",
        "year": None,
        "make": "BMW",
        "model": None,
        "chassis_code": "E30",
        "trim": None,
        "suspension": None,
        "fitment_style": "aggressive",
        "is_valid_input": True,
    },
    {
        "user_input": "350z tucked",
        "year": None,
        "make": "Nissan",
        "model": "350Z",
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": "tucked",
        "is_valid_input": True,
    },
    # Nicknames
    {
        "user_input": "chevy camaro",
        "year": None,
        "make": "Chevrolet",
        "model": "Camaro",
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    {
        "user_input": "bimmer e46",
        "year": None,
        "make": "BMW",
        "model": None,
        "chassis_code": "E46",
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": True,
    },
    # Invalid/unclear
    {
        "user_input": "what wheels fit?",
        "year": None,
        "make": None,
        "model": None,
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": None,
        "is_valid_input": False,
        "clarification_needed": "What vehicle are you working with? Please provide year, make, and model.",
    },
    {
        "user_input": "flush fitment",
        "year": None,
        "make": None,
        "model": None,
        "chassis_code": None,
        "trim": None,
        "suspension": None,
        "fitment_style": "flush",
        "is_valid_input": False,
        "clarification_needed": "What vehicle are you fitting wheels on?",
    },
]


# -----------------------------------------------------------------------------
# Pipeline Module
# -----------------------------------------------------------------------------


class FitmentPipeline(dspy.Module):
    """Complete DSPy pipeline for wheel fitment assistance.

    Flow:
    1. parse_input: Extract vehicle info from user query
    2. resolve_specs: Get specs from DB or web, validate
    3. get_fitments: Fetch community data + Kansei wheels
    4. validate_match: Ensure wheels actually fit
    5. generate_response: Create conversational output
    """

    def __init__(self) -> None:
        super().__init__()

        # Step 1: Parse user input
        self.parse_input = dspy.ChainOfThought(ParseVehicleInput)

        # Step 2: Validate specs (after we have them)
        self.validate_specs = dspy.ChainOfThought(ValidateVehicleSpecs)

        # Step 3: Search for specs if not in DB (using ChainOfThought for reasoning)
        self.search_specs = dspy.ChainOfThought(SearchVehicleSpecs)

        # Step 4: Validate fitment matches
        self.validate_fitment = dspy.Predict(ValidateFitmentMatch)

        # Step 5: Generate response
        self.generate_response = dspy.Predict(GenerateFitmentResponse)

    async def forward(self, user_input: str) -> dspy.Prediction:
        """Process a user query through the full pipeline.

        Returns a Prediction with:
        - response: The conversational response text
        - parsed: Parsed vehicle info
        - specs: Vehicle specifications
        - kansei_wheels: Matching Kansei wheels
        - community_fitments: Community fitment data
        - validation: Validation results
        """
        # Step 1: Parse user input
        parsed = self.parse_input(user_input=user_input)

        # Check if we got enough info
        if not parsed.is_valid_input or str(parsed.is_valid_input).lower() == "false":
            clarification = (
                parsed.clarification_needed or "What vehicle are you working with?"
            )
            return dspy.Prediction(
                response=clarification,
                parsed=self._extract_parsed(parsed),
                specs=None,
                kansei_wheels=[],
                community_fitments=[],
                validation={"valid": False, "reason": "insufficient_input"},
            )

        parsed_info = self._extract_parsed(parsed)

        # Step 2: Resolve vehicle specs (DB lookup first, then web search)
        specs = await self._resolve_specs(parsed_info)

        if specs is None:
            # Couldn't find specs anywhere
            return dspy.Prediction(
                response="I couldn't find wheel specs for that vehicle. Can you provide more details like the year or chassis code?",
                parsed=parsed_info,
                specs=None,
                kansei_wheels=[],
                community_fitments=[],
                validation={"valid": False, "reason": "specs_not_found"},
            )

        # Step 3: Validate the specs make sense for this vehicle
        validation_result = await self._validate_vehicle_specs(parsed_info, specs)

        if not validation_result["is_valid"]:
            # Invalid vehicle combination
            suggestion = validation_result.get("suggestions", "")
            errors = validation_result.get("validation_errors", [])
            error_msg = errors[0] if errors else "Invalid vehicle combination"

            response = f"**Vehicle Not Found**\n\n{error_msg}"
            if suggestion:
                response += f"\n\n{suggestion}"

            return dspy.Prediction(
                response=response,
                parsed=parsed_info,
                specs=specs,
                kansei_wheels=[],
                community_fitments=[],
                validation=validation_result,
            )

        # Step 4: Get community fitments and Kansei wheels
        community_fitments = await db.search_community_fitments(
            make=parsed_info["make"],
            model=parsed_info["model"],
            year=parsed_info.get("year"),
            fitment_style=parsed_info.get("fitment_style"),
            suspension=parsed_info.get("suspension"),
        )

        # Get Kansei wheels for this bolt pattern
        kansei_wheels = await db.find_kansei_wheels(
            bolt_pattern=specs["bolt_pattern"],
            min_diameter=specs["min_diameter"],
            max_diameter=specs["max_diameter"],
            min_width=specs["min_width"],
            max_width=specs["max_width"],
        )

        # Step 5: Validate fitment matches
        validated_wheels = await self._validate_fitment_matches(
            specs=specs,
            kansei_wheels=kansei_wheels,
            suspension=parsed_info.get("suspension"),
        )

        # Step 6: Generate conversational response
        response = await self._generate_response(
            parsed_info=parsed_info,
            specs=specs,
            community_fitments=community_fitments,
            kansei_wheels=validated_wheels["valid"],
            fitment_style=parsed_info.get("fitment_style"),
        )

        return dspy.Prediction(
            response=response,
            parsed=parsed_info,
            specs=specs,
            kansei_wheels=validated_wheels["valid"],
            community_fitments=community_fitments,
            validation={"valid": True, "wheel_validation": validated_wheels},
        )

    def _extract_parsed(self, parsed: dspy.Prediction) -> dict[str, Any]:
        """Extract parsed values into a clean dictionary."""

        def clean(val: Any) -> Any:
            if val is None or str(val).lower() == "none":
                return None
            if isinstance(val, str):
                return val.strip()
            return val

        year = clean(parsed.year)
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        return {
            "year": year,
            "make": clean(parsed.make),
            "model": clean(parsed.model),
            "chassis_code": clean(parsed.chassis_code),
            "trim": clean(parsed.trim),
            "suspension": clean(parsed.suspension),
            "fitment_style": clean(parsed.fitment_style),
        }

    async def _resolve_specs(self, parsed: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve vehicle specs from DB or web search."""
        # Try DB first
        db_specs = await db.find_vehicle_specs(
            year=parsed.get("year"),
            make=parsed.get("make"),
            model=parsed.get("model"),
            chassis_code=parsed.get("chassis_code"),
        )

        if db_specs and db_specs.get("bolt_pattern"):
            return db_specs

        # Not in DB - try web search
        if parsed.get("make"):
            web_result = await search_vehicle_specs_web(
                year=parsed.get("year"),
                make=parsed["make"],
                model=parsed.get("model") or "",
                chassis_code=parsed.get("chassis_code"),
            )

            if web_result.get("found"):
                # Validate the web result
                if not validate_bolt_pattern(web_result.get("bolt_pattern", "")):
                    return None

                # Save to DB for future lookups
                year_start = parsed.get("year")
                year_end = parsed.get("year")

                await db.save_vehicle_specs(
                    year_start=year_start,
                    year_end=year_end,
                    make=parsed["make"],
                    model=parsed.get("model") or "Unknown",
                    chassis_code=parsed.get("chassis_code"),
                    bolt_pattern=web_result["bolt_pattern"],
                    center_bore=web_result["center_bore"],
                    stud_size=web_result.get("stud_size"),
                    min_diameter=web_result.get("min_diameter", 15),
                    max_diameter=web_result.get("max_diameter", 20),
                    min_width=web_result.get("min_width", 6.0),
                    max_width=web_result.get("max_width", 10.0),
                    min_offset=web_result.get("min_offset", -10),
                    max_offset=web_result.get("max_offset", 50),
                    source="web_search",
                    source_url=web_result.get("source_url"),
                    confidence=web_result.get("confidence", 0.8),
                )

                return {
                    "bolt_pattern": web_result["bolt_pattern"],
                    "center_bore": web_result["center_bore"],
                    "stud_size": web_result.get("stud_size"),
                    "min_diameter": web_result.get("min_diameter", 15),
                    "max_diameter": web_result.get("max_diameter", 20),
                    "min_width": web_result.get("min_width", 6.0),
                    "max_width": web_result.get("max_width", 10.0),
                    "min_offset": web_result.get("min_offset", -10),
                    "max_offset": web_result.get("max_offset", 50),
                    "source": "web_search",
                    "confidence": web_result.get("confidence", 0.8),
                }

        return None

    async def _validate_vehicle_specs(
        self,
        parsed: dict[str, Any],
        specs: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate that the vehicle exists and specs are correct."""
        result = self.validate_specs(
            year=parsed.get("year"),
            make=parsed.get("make"),
            model=parsed.get("model"),
            chassis_code=parsed.get("chassis_code"),
            trim=parsed.get("trim"),
            bolt_pattern=specs.get("bolt_pattern", ""),
            center_bore=specs.get("center_bore", 0),
            min_diameter=specs.get("min_diameter", 15),
            max_diameter=specs.get("max_diameter", 20),
            min_width=specs.get("min_width", 6.0),
            max_width=specs.get("max_width", 10.0),
            min_offset=specs.get("min_offset", -10),
            max_offset=specs.get("max_offset", 50),
        )

        is_valid = result.is_valid
        if isinstance(is_valid, str):
            is_valid = is_valid.lower() == "true"

        errors = result.validation_errors
        if isinstance(errors, str):
            try:
                errors = json.loads(errors)
            except json.JSONDecodeError:
                errors = [errors] if errors else []

        return {
            "is_valid": is_valid,
            "validation_errors": errors or [],
            "corrected_specs": result.corrected_specs,
            "suggestions": result.suggestions,
        }

    async def _validate_fitment_matches(
        self,
        specs: dict[str, Any],
        kansei_wheels: list[dict[str, Any]],
        suspension: str | None,
    ) -> dict[str, Any]:
        """Validate which Kansei wheels actually fit."""
        if not kansei_wheels:
            return {
                "valid": [],
                "rejected": [],
                "summary": "No Kansei wheels available for this bolt pattern",
            }

        # Adjust offset range based on suspension
        min_offset = specs.get("min_offset", -10)
        max_offset = specs.get("max_offset", 50)

        suspension_adjustments = {
            "stock": 0,
            "lowered": -5,
            "coilovers": -10,
            "air": -15,
            "lifted": 5,  # Lifted trucks need more offset
        }

        adjustment = suspension_adjustments.get(suspension or "stock", 0)
        adjusted_min_offset = min_offset + adjustment

        # Filter wheels
        valid_wheels = []
        rejected_wheels = []

        for wheel in kansei_wheels:
            offset = wheel.get("offset", 0)
            diameter = wheel.get("diameter", 0)
            width = wheel.get("width", 0)

            rejection_reasons = []

            # Check diameter
            if diameter < specs.get("min_diameter", 15):
                rejection_reasons.append(
                    f'Diameter {diameter}" too small (min {specs.get("min_diameter")}")'
                )
            elif diameter > specs.get("max_diameter", 20):
                rejection_reasons.append(
                    f'Diameter {diameter}" too large (max {specs.get("max_diameter")}")'
                )

            # Check width
            if width < specs.get("min_width", 6.0):
                rejection_reasons.append(
                    f'Width {width}" too narrow (min {specs.get("min_width")}")'
                )
            elif width > specs.get("max_width", 10.0):
                rejection_reasons.append(
                    f'Width {width}" too wide (max {specs.get("max_width")}")'
                )

            # Check offset
            if offset < adjusted_min_offset:
                rejection_reasons.append(
                    f"Offset +{offset} too aggressive (min +{adjusted_min_offset})"
                )
            elif offset > max_offset:
                rejection_reasons.append(
                    f"Offset +{offset} too conservative (max +{max_offset})"
                )

            if rejection_reasons:
                wheel["rejection_reasons"] = rejection_reasons
                rejected_wheels.append(wheel)
            else:
                # Add fitment notes
                notes = []
                if offset < min_offset + 5:
                    notes.append("aggressive fit, may need fender work")
                if offset > max_offset - 5:
                    notes.append("conservative fit, good clearance")
                if diameter == specs.get("max_diameter"):
                    notes.append("maximum recommended diameter")

                wheel["fitment_notes"] = notes
                valid_wheels.append(wheel)

        summary = f"{len(valid_wheels)} wheels fit"
        if rejected_wheels:
            summary += f", {len(rejected_wheels)} incompatible"

        return {
            "valid": valid_wheels,
            "rejected": rejected_wheels,
            "summary": summary,
        }

    async def _generate_response(
        self,
        parsed_info: dict[str, Any],
        specs: dict[str, Any],
        community_fitments: list[dict[str, Any]],
        kansei_wheels: list[dict[str, Any]],
        fitment_style: str | None,
    ) -> str:
        """Generate the conversational response."""
        # Build vehicle summary
        year_str = str(parsed_info.get("year")) if parsed_info.get("year") else ""
        chassis_str = (
            f" ({parsed_info.get('chassis_code')})"
            if parsed_info.get("chassis_code")
            else ""
        )
        vehicle_summary = f"{year_str} {parsed_info.get('make', '')} {parsed_info.get('model', '')}{chassis_str}".strip()

        if parsed_info.get("suspension"):
            vehicle_summary += f" on {parsed_info['suspension']}"

        # Build specs summary
        hub_ring_note = ""
        center_bore = specs.get("center_bore", 0)
        if center_bore and center_bore != 73.1:
            hub_ring_note = f"\nHub rings needed: 73.1mm to {center_bore}mm"

        specs_summary = f"""Bolt Pattern: {specs.get("bolt_pattern", "Unknown")}
Center Bore: {center_bore}mm{hub_ring_note}
Wheel Diameter: {specs.get("min_diameter", 15)}" to {specs.get("max_diameter", 20)}"
Width Range: {specs.get("min_width", 6.0)}" to {specs.get("max_width", 10.0)}"
Offset Range: +{specs.get("min_offset", -10)} to +{specs.get("max_offset", 50)}"""

        # Format community fitments
        community_str = db.format_fitments_for_prompt(community_fitments)

        # Format Kansei wheels
        kansei_str = db.format_kansei_for_prompt(kansei_wheels)

        # Generate response using DSPy
        result = self.generate_response(
            vehicle_summary=vehicle_summary,
            vehicle_specs=specs_summary,
            community_fitments=community_str,
            kansei_options=kansei_str,
            fitment_style=fitment_style,
        )

        return result.response


# -----------------------------------------------------------------------------
# Factory Function
# -----------------------------------------------------------------------------


def create_pipeline(model: str = "openai/gpt-4o") -> FitmentPipeline:
    """Create and configure the fitment pipeline.

    Args:
        model: The LLM model to use (default: gpt-4o for accuracy)

    Returns:
        Configured FitmentPipeline instance
    """
    lm = dspy.LM(model, max_tokens=1024)
    dspy.configure(lm=lm)

    return FitmentPipeline()
