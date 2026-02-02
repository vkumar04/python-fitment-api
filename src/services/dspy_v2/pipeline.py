"""Main DSPy Pipeline for wheel fitment assistance.

This module orchestrates the entire fitment flow:
1. Parse user input → extract vehicle info
2. Resolve specs → check DB, search web if needed, validate
3. Get fitment data → community fitments + Kansei wheels
4. Validate matches → ensure wheels actually fit
5. Generate response → conversational output with validation

The pipeline exposes `retrieve()` for RAG use cases where the caller
streams the final response separately (e.g. via OpenAI streaming).
"""

import json
import re
from dataclasses import dataclass, field
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


@dataclass
class RetrievalResult:
    """Result of the retrieval phase (parse → resolve → validate → fetch).

    This contains everything the LLM needs to generate a response,
    but does NOT include the generated response itself.
    """

    parsed: dict[str, Any]
    specs: dict[str, Any] | None
    kansei_wheels: list[dict[str, Any]] = field(default_factory=list)
    community_fitments: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    # Pre-formatted strings for the prompt
    vehicle_summary: str = ""
    specs_summary: str = ""
    community_str: str = ""
    kansei_str: str = ""

    # Pre-computed recommendations (math-based, OpenAI should use verbatim)
    recommended_setups_str: str = ""

    # If set, the caller should return this text directly (error/clarification)
    early_response: str | None = None

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
# Validation Functions for dspy.Refine
# -----------------------------------------------------------------------------


def extract_wheel_sizes_from_response(response: str) -> list[tuple[int, float]]:
    """Extract wheel sizes (diameter x width) mentioned in a response.

    Returns list of (diameter, width) tuples found in the response.
    """
    # Match patterns like "18x9.5", "17x9", "18x8.5"
    pattern = r'\b(\d{2})x(\d+\.?\d*)\b'
    matches = re.findall(pattern, response)
    return [(int(d), float(w)) for d, w in matches]


# -----------------------------------------------------------------------------
# Math-Based Fitment Calculations
# -----------------------------------------------------------------------------


def calculate_wheel_fitment(
    wheel_width_inches: float,
    wheel_offset_mm: int,
    oem_width_inches: float,
    oem_offset_mm: int,
    suspension: str = "stock",
) -> dict[str, Any]:
    """Calculate fitment geometry for a wheel compared to OEM specs.

    This uses actual math to determine if a wheel will fit, rather than
    relying on community data which may be inconsistent.

    Key concept: Offset is the distance from the wheel centerline to the
    mounting face. Higher offset = wheel sits further inboard (tucked).
    Lower offset = wheel sits further outboard (poke).

    Formulas:
    - Poke (outer lip position) = (width_diff × 25.4 / 2) + (oem_offset - wheel_offset)
    - Inner change = how much closer the inner lip is to suspension
      = (width_diff × 25.4 / 2) + (wheel_offset - oem_offset)

    Args:
        wheel_width_inches: Aftermarket wheel width (e.g., 9.0)
        wheel_offset_mm: Aftermarket wheel offset (e.g., +35)
        oem_width_inches: Stock wheel width (e.g., 7.5)
        oem_offset_mm: Stock wheel offset (e.g., +41)
        suspension: Suspension type affects acceptable poke

    Returns:
        Dict with calculated fitment values and whether it's likely to fit
    """
    # Convert width difference to mm (1 inch = 25.4mm)
    width_diff_inches = wheel_width_inches - oem_width_inches
    width_diff_mm = width_diff_inches * 25.4

    # Offset difference (positive = more poke, negative = more tuck)
    offset_diff = oem_offset_mm - wheel_offset_mm

    # Poke calculation: how much further out the wheel sits vs OEM
    # Half the extra width goes outboard, plus offset difference
    poke_mm = (width_diff_mm / 2) + offset_diff

    # Inner clearance change: how much closer the inner lip is to suspension
    # Positive value = inner lip moved inward (closer to strut - potentially bad)
    # Negative value = inner lip moved outward (more clearance - good)
    #
    # - Wider wheel: inner lip moves inward by half width increase
    # - Higher offset: mounting face closer to outer edge, so inner lip moves OUTWARD
    # - Lower offset: mounting face closer to inner edge, so inner lip moves INWARD
    inner_change_mm = (width_diff_mm / 2) - (wheel_offset_mm - oem_offset_mm)

    # Acceptable poke thresholds based on suspension
    # These are realistic for aftermarket wheels - most enthusiast setups
    # run some poke even on stock suspension
    poke_limits = {
        "stock": 18,       # Stock suspension: ~18mm poke is daily-able
        "lowered": 25,     # Lowered: more aggressive OK with roll
        "coilovers": 35,   # Coilovers: can adjust camber, more poke OK
        "air": 50,         # Air: max flexibility when aired out
        "lifted": 10,      # Lifted trucks: less poke tolerance
    }

    # Inner clearance limits (strut/shock clearance)
    inner_limits = {
        "stock": 20,
        "lowered": 20,
        "coilovers": 25,   # Coilovers often have slimmer bodies
        "air": 30,
        "lifted": 20,
    }

    max_poke = poke_limits.get(suspension, 10)
    max_inner = inner_limits.get(suspension, 15)

    # Determine if it fits
    fits = poke_mm <= max_poke and inner_change_mm <= max_inner

    # Fitment style based on poke
    # Note: On wide-body/flared cars (E30 M3, E36 M3), the flares absorb
    # more poke visually, so +10mm may still look "flush"
    if poke_mm < -5:
        style = "tucked"
    elif poke_mm < 10:
        style = "flush"  # Up to 10mm is visually flush on most cars
    elif poke_mm < 20:
        style = "mild poke"  # 10-20mm is noticeable but daily-able
    else:
        style = "aggressive poke"  # 20mm+ requires mods on most cars

    # Modification notes
    mods_needed = []
    if poke_mm > max_poke:
        if poke_mm > max_poke + 15:
            mods_needed.append("fender flares or wide body kit")
        elif poke_mm > max_poke + 5:
            mods_needed.append("fender rolling/pulling")
        else:
            mods_needed.append("minor fender adjustment")

    if inner_change_mm > max_inner:
        mods_needed.append("may need thinner strut spacers or camber arms")

    return {
        "poke_mm": round(poke_mm, 1),
        "inner_change_mm": round(inner_change_mm, 1),
        "fits_without_mods": fits,
        "style": style,
        "mods_needed": mods_needed,
        "suspension": suspension,
    }


def filter_wheels_by_math(
    kansei_wheels: list[dict[str, Any]],
    oem_width: float,
    oem_offset: int,
    suspension: str = "stock",
    fitment_style: str | None = None,
) -> list[dict[str, Any]]:
    """Filter Kansei wheels using math-based fitment calculations.

    Args:
        kansei_wheels: List of Kansei wheel dicts with diameter, width, offset
        oem_width: OEM wheel width in inches
        oem_offset: OEM wheel offset in mm
        suspension: User's suspension type
        fitment_style: Desired style (flush/aggressive/tucked)

    Returns:
        Filtered list of wheels that fit, with fitment calculations attached
    """
    filtered = []

    for wheel in kansei_wheels:
        width = wheel.get("width", 0)
        offset = wheel.get("offset", 0)

        calc = calculate_wheel_fitment(
            wheel_width_inches=width,
            wheel_offset_mm=offset,
            oem_width_inches=oem_width,
            oem_offset_mm=oem_offset,
            suspension=suspension,
        )

        # Filter by fitment style preference
        # Thresholds consistent with calculate_wheel_fitment:
        # - tucked: < -5mm
        # - flush: -5mm to +10mm
        # - mild poke: +10mm to +20mm
        # - aggressive: >= +20mm
        if fitment_style:
            style_lower = fitment_style.lower()
            if style_lower == "flush" and calc["poke_mm"] > 10:
                continue  # Too much poke for flush (needs < 10mm)
            elif style_lower == "aggressive" and calc["poke_mm"] < 15:
                continue  # Not aggressive enough (needs >= 15mm for aggressive look)
            elif style_lower == "tucked" and calc["poke_mm"] > -5:
                continue  # Not tucked enough (needs < -5mm)

        # Include wheels that fit (or nearly fit with minor mods)
        if calc["fits_without_mods"] or calc["poke_mm"] <= 20:
            wheel_copy = wheel.copy()
            wheel_copy["fitment_calc"] = calc
            filtered.append(wheel_copy)

    return filtered


def create_kansei_validation_reward(available_sizes: set[tuple[int, float]]):
    """Create a reward function that validates wheel sizes against Kansei inventory.

    Args:
        available_sizes: Set of (diameter, width) tuples that Kansei actually makes

    Returns:
        Reward function compatible with dspy.Refine
    """
    def reward_fn(args: dict, pred: dspy.Prediction) -> float:
        """Score the response based on whether recommended sizes exist in Kansei catalog."""
        response = pred.response if hasattr(pred, 'response') else str(pred)

        # Extract sizes mentioned in the response
        mentioned_sizes = extract_wheel_sizes_from_response(response)

        if not mentioned_sizes:
            # No sizes mentioned (might be asking a question) - that's fine
            return 1.0

        # Check how many mentioned sizes are valid
        valid_count = sum(1 for size in mentioned_sizes if size in available_sizes)
        total_count = len(mentioned_sizes)

        # Return ratio of valid sizes (1.0 = all valid, 0.0 = none valid)
        return valid_count / total_count if total_count > 0 else 1.0

    return reward_fn


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
    5. generate_response: Create conversational output with validation

    The response generation uses dspy.Refine to ensure recommended wheel
    sizes actually exist in the Kansei catalog.
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

        # Step 5: Generate response (base module - will be wrapped with Refine dynamically)
        self._base_response_generator = dspy.Predict(GenerateFitmentResponse)

        # Note: We create the Refine wrapper dynamically in forward() because
        # the available Kansei sizes vary per query (different bolt patterns)
        self.generate_response = self._base_response_generator

    def retrieve(self, user_input: str) -> RetrievalResult:
        """Run the retrieval phase only (steps 1-4), without generating a response.

        Use this for streaming: call retrieve() to gather context, then stream
        the response via OpenAI directly.  This method is synchronous and
        should be called from ``asyncio.to_thread()`` in async contexts.
        """
        # Step 1: Parse user input
        parsed = self.parse_input(user_input=user_input)

        if not parsed.is_valid_input or str(parsed.is_valid_input).lower() == "false":
            clarification = (
                parsed.clarification_needed or "What vehicle are you working with?"
            )
            return RetrievalResult(
                parsed=self._extract_parsed(parsed),
                specs=None,
                early_response=clarification,
                validation={"valid": False, "reason": "insufficient_input"},
            )

        parsed_info = self._extract_parsed(parsed)

        # Merge trim into model for accurate lookups (e.g. "Civic" + "Type R" → "Civic Type R")
        _trim = parsed_info.get("trim")
        _model = parsed_info.get("model") or ""
        if _trim and _trim.lower() not in _model.lower():
            parsed_info["model"] = f"{_model} {_trim}".strip()

        # Step 2: Resolve vehicle specs (DB first, then web scrape)
        specs = self._resolve_specs(parsed_info)

        if specs is None:
            return RetrievalResult(
                parsed=parsed_info,
                specs=None,
                early_response="I couldn't find wheel specs for that vehicle. Can you provide more details like the year or chassis code?",
                validation={"valid": False, "reason": "specs_not_found"},
            )

        # Step 3: Validate specs for this vehicle
        # Skip LLM validation for trusted sources — the LLM sometimes
        # incorrectly rejects valid numeric ranges (e.g. offset 10-35 for E30 M3).
        # Only use LLM validation for unverified/low-confidence specs.
        is_trusted = (
            specs.get("verified") is True
            or specs.get("source") in ("manual", "knowledge_base")
            or float(specs.get("confidence", 0)) >= 0.85
        )

        if is_trusted:
            validation_result: dict[str, Any] = {
                "is_valid": True,
                "validation_errors": [],
                "corrected_specs": None,
                "suggestions": None,
            }
        else:
            validation_result = self._validate_vehicle_specs(parsed_info, specs)

            if not validation_result["is_valid"]:
                # DB returned wrong specs — try knowledge base / web scrape
                if parsed_info.get("make"):
                    web_result = search_vehicle_specs_web(
                        year=parsed_info.get("year"),
                        make=parsed_info["make"],
                        model=parsed_info.get("model") or "",
                        chassis_code=parsed_info.get("chassis_code"),
                    )
                    if web_result.get("found"):
                        alt_specs = {
                            "bolt_pattern": web_result["bolt_pattern"],
                            "center_bore": web_result["center_bore"],
                            "stud_size": web_result.get("stud_size"),
                            "min_diameter": web_result.get("min_diameter", 15),
                            "max_diameter": web_result.get("max_diameter", 20),
                            "min_width": web_result.get("min_width", 6.0),
                            "max_width": web_result.get("max_width", 10.0),
                            "min_offset": web_result.get("min_offset", -10),
                            "max_offset": web_result.get("max_offset", 50),
                            "source": web_result.get("source", "knowledge_base"),
                            "confidence": web_result.get("confidence", 0.7),
                        }
                        # Knowledge base results are trusted — skip LLM validation
                        if alt_specs.get("source") == "knowledge_base":
                            specs = alt_specs
                            validation_result = {
                                "is_valid": True,
                                "validation_errors": [],
                                "corrected_specs": None,
                                "suggestions": None,
                            }
                        else:
                            alt_validation = self._validate_vehicle_specs(
                                parsed_info, alt_specs
                            )
                            if alt_validation["is_valid"]:
                                specs = alt_specs
                                validation_result = alt_validation

                if not validation_result["is_valid"]:
                    suggestion = validation_result.get("suggestions", "")
                    errors = validation_result.get("validation_errors", [])
                    error_msg = errors[0] if errors else "Invalid vehicle combination"
                    msg = f"**Vehicle Not Found**\n\n{error_msg}"
                    if suggestion:
                        msg += f"\n\n{suggestion}"

                    return RetrievalResult(
                        parsed=parsed_info,
                        specs=specs,
                        early_response=msg,
                        validation=validation_result,
                    )

        # Step 4: Get community fitments + Kansei wheels
        # For classic cars (max_diameter <= 17), filter out extreme setups
        # to avoid showing 19"+ wheels from heavily modified builds
        community_max_diameter = None
        if specs.get("max_diameter") and specs["max_diameter"] <= 17:
            community_max_diameter = specs["max_diameter"]

        try:
            community_fitments = db.search_community_fitments(
                make=parsed_info["make"],
                model=parsed_info["model"],
                year=parsed_info.get("year"),
                fitment_style=parsed_info.get("fitment_style"),
                suspension=parsed_info.get("suspension"),
                max_diameter=community_max_diameter,
            )
        except Exception:
            community_fitments = []

        try:
            kansei_wheels = db.find_kansei_wheels(
                bolt_pattern=specs["bolt_pattern"],
                min_diameter=specs["min_diameter"],
                max_diameter=specs["max_diameter"],
                min_width=specs["min_width"],
                max_width=specs["max_width"],
            )
        except Exception:
            kansei_wheels = []

        validated_wheels = self._validate_fitment_matches(
            specs=specs,
            kansei_wheels=kansei_wheels,
            suspension=parsed_info.get("suspension"),
        )

        # Build set of available Kansei sizes for filtering community fitments
        available_kansei_sizes = set()
        for w in validated_wheels["valid"]:
            d = int(w.get("diameter", 0))
            width = float(w.get("width", 0))
            available_kansei_sizes.add((d, width))

        # Filter community fitments to only show setups that match Kansei sizes
        filtered_community = self._filter_community_by_kansei(
            community_fitments, available_kansei_sizes
        )

        # Build formatted strings for the prompt
        vehicle_summary, specs_summary = self._build_summaries(parsed_info, specs)
        community_str = db.format_fitments_for_prompt(filtered_community)
        kansei_str = db.format_kansei_for_prompt(validated_wheels["valid"])

        # Generate pre-computed recommendations using math
        # Tire sizing now accounts for suspension type (bagged = narrow tires)
        recommended_setups_str = db.generate_recommended_setups(
            validated_wheels["valid"],
            fitment_style=parsed_info.get("fitment_style"),
            suspension=parsed_info.get("suspension"),
        )

        return RetrievalResult(
            parsed=parsed_info,
            specs=specs,
            kansei_wheels=validated_wheels["valid"],
            community_fitments=community_fitments,
            validation={"valid": True, "wheel_validation": validated_wheels},
            vehicle_summary=vehicle_summary,
            specs_summary=specs_summary,
            community_str=community_str,
            kansei_str=kansei_str,
            recommended_setups_str=recommended_setups_str,
        )

    def forward(self, user_input: str) -> dspy.Prediction:
        """Process a user query through the full pipeline.

        Calls retrieve() then generates the response via DSPy with Refine
        to ensure recommended wheel sizes exist in Kansei's catalog.

        For streaming use cases, call retrieve() directly and stream
        the response via OpenAI.
        """
        retrieval = self.retrieve(user_input)

        if retrieval.early_response:
            return dspy.Prediction(
                response=retrieval.early_response,
                parsed=retrieval.parsed,
                specs=retrieval.specs,
                kansei_wheels=retrieval.kansei_wheels,
                community_fitments=retrieval.community_fitments,
                validation=retrieval.validation,
            )

        # Build set of available Kansei sizes for validation
        available_sizes: set[tuple[int, float]] = set()
        for wheel in retrieval.kansei_wheels:
            diameter = int(wheel.get("diameter", 0))
            width = float(wheel.get("width", 0))
            if diameter and width:
                available_sizes.add((diameter, width))

        # Create reward function for this specific query's Kansei inventory
        reward_fn = create_kansei_validation_reward(available_sizes)

        # Wrap response generator with Refine for validation
        # N=3 means up to 3 attempts, threshold=1.0 means all sizes must be valid
        refined_generator = dspy.Refine(
            module=self._base_response_generator,
            N=3,
            reward_fn=reward_fn,
            threshold=1.0,
        )

        # Generate response with validation
        result = refined_generator(
            vehicle_summary=retrieval.vehicle_summary,
            vehicle_specs=retrieval.specs_summary,
            community_fitments=retrieval.community_str,
            kansei_options=retrieval.kansei_str,
            fitment_style=retrieval.parsed.get("fitment_style"),
        )

        return dspy.Prediction(
            response=result.response,
            parsed=retrieval.parsed,
            specs=retrieval.specs,
            kansei_wheels=retrieval.kansei_wheels,
            community_fitments=retrieval.community_fitments,
            validation=retrieval.validation,
        )

    def _extract_parsed(self, parsed: dspy.Prediction) -> dict[str, Any]:
        """Extract parsed values into a clean dictionary."""

        def clean(val: Any) -> Any:
            if val is None or str(val).lower() == "none":
                return None
            if isinstance(val, str):
                # DSPy sometimes appends schema notes to values like:
                # "Honda        # note: the value you produce must adhere..."
                val = val.split("# note:")[0].split("#")[0].strip()
                if not val or val.lower() == "none":
                    return None
                return val
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

    def _resolve_specs(self, parsed: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve vehicle specs from knowledge base, then DB, then web scrape.

        Priority order:
        1. Knowledge base (hardcoded, verified specs for known vehicles)
        2. Database (cached specs from previous lookups)
        3. Web scrape (wheel-size.com for unknown vehicles)

        This ensures known vehicles like E30 M3 always get correct specs
        even if DB has stale/incorrect data.
        """
        model = parsed.get("model") or ""

        # Try knowledge base FIRST (most reliable for known vehicles)
        if parsed.get("make"):
            kb_result = search_vehicle_specs_web(
                year=parsed.get("year"),
                make=parsed["make"],
                model=model,
                chassis_code=parsed.get("chassis_code"),
            )
            # Knowledge base results are high confidence and should be trusted
            if kb_result.get("found") and kb_result.get("source") == "knowledge_base":
                return {
                    "bolt_pattern": kb_result["bolt_pattern"],
                    "center_bore": kb_result["center_bore"],
                    "stud_size": kb_result.get("stud_size"),
                    "year_start": kb_result.get("year_start"),
                    "year_end": kb_result.get("year_end"),
                    "min_diameter": kb_result.get("min_diameter", 15),
                    "max_diameter": kb_result.get("max_diameter", 20),
                    "min_width": kb_result.get("min_width", 6.0),
                    "max_width": kb_result.get("max_width", 10.0),
                    "min_offset": kb_result.get("min_offset", -10),
                    "max_offset": kb_result.get("max_offset", 50),
                    "source": "knowledge_base",
                    "confidence": kb_result.get("confidence", 0.85),
                }

        # Try DB second (cached specs)
        db_specs = None
        try:
            db_specs = db.find_vehicle_specs(
                year=parsed.get("year"),
                make=parsed.get("make"),
                model=model,
                chassis_code=parsed.get("chassis_code"),
            )
        except Exception:
            pass

        if db_specs and db_specs.get("bolt_pattern"):
            return db_specs

        # Not in knowledge base or DB - try web scrape
        if parsed.get("make"):
            web_result = search_vehicle_specs_web(
                year=parsed.get("year"),
                make=parsed["make"],
                model=model,
                chassis_code=parsed.get("chassis_code"),
            )

            if web_result.get("found"):
                # Validate the web result
                if not validate_bolt_pattern(web_result.get("bolt_pattern", "")):
                    return None

                # Save to DB for future lookups
                year_start = parsed.get("year")
                year_end = parsed.get("year")

                try:
                    db.save_vehicle_specs(
                        year_start=year_start,
                        year_end=year_end,
                        make=parsed["make"],
                        model=model or "Unknown",
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
                        source=web_result.get("source", "web_search"),
                        source_url=web_result.get("source_url"),
                        confidence=web_result.get("confidence", 0.8),
                    )
                except Exception:
                    pass  # Don't block retrieval if DB save fails

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
                    "source": web_result.get("source", "web_search"),
                    "confidence": web_result.get("confidence", 0.8),
                }

        return None

    def _validate_vehicle_specs(
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

    def _validate_fitment_matches(
        self,
        specs: dict[str, Any],
        kansei_wheels: list[dict[str, Any]],
        suspension: str | None,
    ) -> dict[str, Any]:
        """Validate which Kansei wheels actually fit using math-based calculations.

        Uses geometry formulas to calculate poke and inner clearance, rather than
        just checking if values fall within ranges. This gives more accurate
        fitment predictions.
        """
        if not kansei_wheels:
            return {
                "valid": [],
                "rejected": [],
                "summary": "No Kansei wheels available for this bolt pattern",
            }

        susp = suspension or "stock"

        # Get OEM specs for math calculations
        oem_width = specs.get("oem_width", specs.get("min_width", 7.0))
        oem_offset = specs.get("oem_offset", (specs.get("min_offset", 20) + specs.get("max_offset", 40)) // 2)

        # Filter wheels using math-based calculations
        valid_wheels = []
        rejected_wheels = []

        for wheel in kansei_wheels:
            offset = wheel.get("offset", 0)
            diameter = wheel.get("diameter", 0)
            width = wheel.get("width", 0)

            rejection_reasons = []

            # Check diameter bounds first (these are hard limits)
            if diameter < specs.get("min_diameter", 15):
                rejection_reasons.append(
                    f'Diameter {diameter}" too small (min {specs.get("min_diameter")}")'
                )
            elif diameter > specs.get("max_diameter", 20):
                rejection_reasons.append(
                    f'Diameter {diameter}" too large (max {specs.get("max_diameter")}")'
                )

            # Use math-based fitment calculation
            fitment_calc = calculate_wheel_fitment(
                wheel_width_inches=width,
                wheel_offset_mm=offset,
                oem_width_inches=oem_width,
                oem_offset_mm=oem_offset,
                suspension=susp,
            )

            # Check if math says it fits
            if not fitment_calc["fits_without_mods"] and fitment_calc["poke_mm"] > 25:
                rejection_reasons.append(
                    f"Too much poke ({fitment_calc['poke_mm']}mm) for {susp} suspension"
                )

            if fitment_calc["inner_change_mm"] > 25:
                rejection_reasons.append(
                    f"Inner clearance issue ({fitment_calc['inner_change_mm']}mm closer to suspension)"
                )

            if rejection_reasons:
                wheel["rejection_reasons"] = rejection_reasons
                rejected_wheels.append(wheel)
            else:
                # Add fitment notes based on math calculations
                notes = []

                # Poke-based notes (consistent with style thresholds)
                poke = fitment_calc["poke_mm"]
                if poke > 20:
                    notes.append(f"aggressive poke ({poke:.0f}mm)")
                elif poke > 10:
                    notes.append(f"mild poke ({poke:.0f}mm)")
                elif poke > -5:
                    notes.append("flush fitment")
                else:
                    notes.append(f"tucked ({abs(poke):.0f}mm inside fender)")

                # Modification notes from math
                if fitment_calc["mods_needed"]:
                    notes.extend(fitment_calc["mods_needed"])

                # Inner clearance notes
                inner = fitment_calc["inner_change_mm"]
                if inner > 10:
                    notes.append(f"check strut clearance ({inner:.0f}mm closer than stock)")

                if diameter == specs.get("max_diameter"):
                    notes.append("maximum recommended diameter")

                wheel["fitment_notes"] = notes
                wheel["fitment_calc"] = fitment_calc
                valid_wheels.append(wheel)

        summary = f"{len(valid_wheels)} wheels fit"
        if rejected_wheels:
            summary += f", {len(rejected_wheels)} incompatible"

        return {
            "valid": valid_wheels,
            "rejected": rejected_wheels,
            "summary": summary,
        }

    def _filter_community_by_kansei(
        self,
        community_fitments: list[dict[str, Any]],
        available_sizes: set[tuple[int, float]],
    ) -> list[dict[str, Any]]:
        """Filter community fitments to only include sizes that Kansei actually makes.

        This prevents the model from seeing community data showing sizes like 18x9.5
        when Kansei only makes 18x8.5 or 18x9.

        Args:
            community_fitments: List of community fitment records
            available_sizes: Set of (diameter, width) tuples that Kansei makes

        Returns:
            Filtered list of fitments that match available Kansei sizes
        """
        if not available_sizes or not community_fitments:
            return community_fitments

        filtered = []
        for fitment in community_fitments:
            front_d = fitment.get("front_diameter")
            front_w = fitment.get("front_width")
            rear_d = fitment.get("rear_diameter")
            rear_w = fitment.get("rear_width")

            # Check if front size is available (or missing)
            front_ok = (
                not front_d or not front_w or
                (int(front_d), float(front_w)) in available_sizes
            )

            # Check if rear size is available (or missing)
            rear_ok = (
                not rear_d or not rear_w or
                (int(rear_d), float(rear_w)) in available_sizes
            )

            if front_ok and rear_ok:
                filtered.append(fitment)

        return filtered

    def _build_summaries(
        self,
        parsed_info: dict[str, Any],
        specs: dict[str, Any],
    ) -> tuple[str, str]:
        """Build formatted vehicle summary and specs summary strings."""
        # Use specific year if provided, otherwise use year range from specs
        if parsed_info.get("year"):
            year_str = str(parsed_info["year"])
        elif specs.get("year_start") and specs.get("year_end"):
            year_start = specs["year_start"]
            year_end = specs["year_end"]
            if year_start == year_end:
                year_str = str(year_start)
            else:
                year_str = f"{year_start}-{year_end}"
        else:
            year_str = ""

        chassis_str = (
            f" ({parsed_info.get('chassis_code')})"
            if parsed_info.get("chassis_code")
            else ""
        )
        vehicle_summary = f"{year_str} {parsed_info.get('make', '')} {parsed_info.get('model', '')}{chassis_str}".strip()

        if parsed_info.get("suspension"):
            vehicle_summary += f" on {parsed_info['suspension']}"

        # Hub bore compatibility check
        hub_ring_note = ""
        center_bore = specs.get("center_bore", 0)
        kansei_bore = 73.1

        if center_bore and center_bore != kansei_bore:
            if center_bore < kansei_bore:
                # Wheel bore larger than hub = hub rings work
                hub_ring_note = f"\nHub rings needed: {kansei_bore}mm → {center_bore}mm"
            else:
                # Wheel bore smaller than hub = INCOMPATIBLE
                hub_ring_note = (
                    f"\n⚠️ Standard Kansei wheels ({kansei_bore}mm bore) are NOT compatible "
                    f"with this vehicle's {center_bore}mm hub. Hub rings will NOT work. "
                    f"Hub-specific SKUs or professional machining required."
                )

        specs_summary = f"""Bolt Pattern: {specs.get("bolt_pattern", "Unknown")}
Center Bore: {center_bore}mm{hub_ring_note}
Wheel Diameter: {specs.get("min_diameter", 15)}" to {specs.get("max_diameter", 20)}"
Width Range: {specs.get("min_width", 6.0)}" to {specs.get("max_width", 10.0)}"
Offset Range: +{specs.get("min_offset", -10)} to +{specs.get("max_offset", 50)}"""

        return vehicle_summary, specs_summary


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
