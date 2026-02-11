"""Main DSPy Pipeline for wheel fitment assistance.

This module orchestrates the entire fitment flow:
1. Parse user input → extract vehicle info
2. Resolve specs → check DB, search web if needed, validate
3. Get fitment data → community fitments + Kansei wheels
4. Validate matches → ensure wheels actually fit
5. Generate response → conversational output

The pipeline exposes `retrieve()` for RAG use cases where the caller
streams the final response separately (e.g. via OpenAI streaming).
"""

import json
import logging
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
from .tools import scrape_vehicle_specs, validate_bolt_pattern, validate_center_bore

logger = logging.getLogger(__name__)


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
            or specs.get("source") in ("manual", "dspy_llm_validated")
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

        # Build formatted strings for the prompt
        vehicle_summary, specs_summary = self._build_summaries(parsed_info, specs)
        community_str = db.format_fitments_for_prompt(community_fitments)
        kansei_str = db.format_kansei_for_prompt(validated_wheels["valid"])

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
        )

    def forward(self, user_input: str) -> dspy.Prediction:
        """Process a user query through the full pipeline.

        Calls retrieve() then generates the response via DSPy.
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

        # Generate response via DSPy
        result = self.generate_response(
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
        """Resolve vehicle specs from DB, then LLM, then web scrape cross-validation.

        Priority order:
        1. Database (verified seeds + previously cached LLM/scrape results)
        2. DSPy LLM (SearchVehicleSpecs signature)
        3. Web scrape cross-validation (wheel-size.com, if year available)
        4. Cache result to DB for future lookups
        """
        model = parsed.get("model") or ""

        # Step 1: Try DB first (verified seeds + cached results)
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

        # Step 2: DSPy LLM resolution
        llm_specs = self._resolve_via_llm(parsed)

        # Step 3: Web scrape cross-validation (requires year)
        scrape_specs = None
        year = parsed.get("year")
        if year and parsed.get("make"):
            scrape_specs = scrape_vehicle_specs(
                year=year,
                make=parsed["make"],
                model=model,
            )

        # Step 4: Merge results
        if llm_specs and scrape_specs:
            final_specs = self._cross_validate(llm_specs, scrape_specs)
        elif llm_specs:
            # LLM only — lower confidence, no cross-validation
            final_specs = {**llm_specs, "confidence": 0.60}
        elif scrape_specs:
            # Scrape only — LLM failed
            final_specs = {
                "bolt_pattern": scrape_specs["bolt_pattern"],
                "center_bore": scrape_specs["center_bore"],
                "stud_size": scrape_specs.get("stud_size", ""),
                "min_diameter": scrape_specs.get("min_diameter", 15),
                "max_diameter": scrape_specs.get("max_diameter", 20),
                "min_width": scrape_specs.get("min_width", 6.0),
                "max_width": scrape_specs.get("max_width", 10.0),
                "min_offset": scrape_specs.get("min_offset", -10),
                "max_offset": scrape_specs.get("max_offset", 50),
                "source": "wheel_size_scrape",
                "confidence": 0.70,
            }
        else:
            return None

        # Step 5: Cache to DB for future lookups
        try:
            db.save_vehicle_specs(
                year_start=year,
                year_end=year,
                make=parsed.get("make") or "Unknown",
                model=model or "Unknown",
                chassis_code=parsed.get("chassis_code"),
                bolt_pattern=final_specs["bolt_pattern"],
                center_bore=final_specs["center_bore"],
                stud_size=final_specs.get("stud_size"),
                min_diameter=final_specs.get("min_diameter", 15),
                max_diameter=final_specs.get("max_diameter", 20),
                min_width=final_specs.get("min_width", 6.0),
                max_width=final_specs.get("max_width", 10.0),
                min_offset=final_specs.get("min_offset", -10),
                max_offset=final_specs.get("max_offset", 50),
                source=final_specs.get("source", "dspy_llm"),
                source_url=final_specs.get("source_url"),
                confidence=final_specs.get("confidence", 0.6),
            )
        except Exception:
            pass  # Don't block retrieval if DB save fails

        return final_specs

    def _resolve_via_llm(self, parsed: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve vehicle specs using DSPy SearchVehicleSpecs signature."""
        if not parsed.get("make"):
            return None

        try:
            result = self.search_specs(
                year=parsed.get("year"),
                make=parsed["make"],
                model=parsed.get("model") or "",
                chassis_code=parsed.get("chassis_code"),
                trim=parsed.get("trim"),
            )

            bolt_pattern = str(result.bolt_pattern).strip()
            if not validate_bolt_pattern(bolt_pattern):
                logger.warning("LLM returned invalid bolt pattern: %s", bolt_pattern)
                return None

            center_bore = float(result.center_bore)
            if not validate_center_bore(center_bore):
                logger.warning("LLM returned invalid center bore: %s", center_bore)
                return None

            confidence = min(float(result.confidence), 0.65)

            return {
                "bolt_pattern": bolt_pattern,
                "center_bore": center_bore,
                "stud_size": str(result.stud_size).strip(),
                "oem_diameter": int(result.oem_diameter),
                "min_diameter": int(result.min_diameter),
                "max_diameter": int(result.max_diameter),
                "oem_width": float(result.oem_width),
                "min_width": float(result.min_width),
                "max_width": float(result.max_width),
                "oem_offset": int(result.oem_offset),
                "min_offset": int(result.min_offset),
                "max_offset": int(result.max_offset),
                "source": "dspy_llm",
                "source_url": str(result.source_url).strip(),
                "confidence": confidence,
            }
        except Exception as e:
            logger.warning("DSPy SearchVehicleSpecs failed: %s", e)
            return None

    @staticmethod
    def _cross_validate(
        llm_specs: dict[str, Any],
        scrape_specs: dict[str, Any],
    ) -> dict[str, Any]:
        """Cross-validate LLM specs against web scrape results.

        If bolt patterns agree, trust the LLM ranges (more trim-aware) at
        higher confidence. If they disagree, prefer the scrape for bolt
        pattern (data-driven) at lower confidence.
        """
        llm_bp = llm_specs["bolt_pattern"]
        scrape_bp = scrape_specs["bolt_pattern"]

        if llm_bp == scrape_bp:
            # Agreement — use LLM ranges (more nuanced for trims) with boosted confidence
            return {
                **llm_specs,
                "confidence": 0.80,
                "source": "dspy_llm_validated",
            }
        else:
            # Disagreement — prefer scrape bolt pattern (data-driven)
            logger.warning(
                "Bolt pattern mismatch: LLM=%s, scrape=%s — using scrape",
                llm_bp,
                scrape_bp,
            )
            return {
                "bolt_pattern": scrape_bp,
                "center_bore": scrape_specs["center_bore"],
                "stud_size": scrape_specs.get("stud_size", llm_specs.get("stud_size", "")),
                "min_diameter": scrape_specs.get("min_diameter", 15),
                "max_diameter": scrape_specs.get("max_diameter", 20),
                "min_width": scrape_specs.get("min_width", 6.0),
                "max_width": scrape_specs.get("max_width", 10.0),
                "min_offset": scrape_specs.get("min_offset", -10),
                "max_offset": scrape_specs.get("max_offset", 50),
                "source": "wheel_size_scrape",
                "confidence": 0.70,
            }

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

        # Suspension-based adjustments for offset and width tolerance
        susp = suspension or "stock"
        offset_adjustments = {
            "stock": 0,
            "lowered": -5,
            "coilovers": -10,
            "air": -15,
            "lifted": 5,  # Lifted trucks need more offset
        }
        # Coilovers/air can accommodate wider wheels with proper camber
        width_adjustments = {
            "stock": 0.0,
            "lowered": 0.0,
            "coilovers": 0.5,
            "air": 1.0,
            "lifted": 0.0,
        }

        offset_adj = offset_adjustments.get(susp, 0)
        width_adj = width_adjustments.get(susp, 0.0)
        adjusted_min_offset = min_offset + offset_adj
        base_max_width = specs.get("max_width", 10.0)
        adjusted_max_width = base_max_width + width_adj

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

            # Check width (adjusted for suspension)
            if width < specs.get("min_width", 6.0):
                rejection_reasons.append(
                    f'Width {width}" too narrow (min {specs.get("min_width")}")'
                )
            elif width > adjusted_max_width:
                rejection_reasons.append(
                    f'Width {width}" too wide (max {adjusted_max_width}" on {susp})'
                )

            # Check offset
            if offset < adjusted_min_offset:
                rejection_reasons.append(
                    f"Offset +{offset} too aggressive (min +{adjusted_min_offset} on {susp})"
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
                min_width = specs.get("min_width", 6.0)

                # Width notes (relative to base spec, not adjusted)
                if width > base_max_width:
                    notes.append(
                        f"exceeds stock max width ({base_max_width}\") — "
                        f"OK on {susp} with proper camber"
                    )
                elif width == base_max_width:
                    notes.append("maximum recommended width for stock")
                elif width >= base_max_width - 0.5 and width > min_width:
                    notes.append("near maximum width")

                # Offset notes (relative to base spec, not adjusted)
                if offset < min_offset + 5:
                    if susp in ("coilovers", "air"):
                        notes.append(
                            f"aggressive offset — manageable on {susp}"
                        )
                    else:
                        notes.append("aggressive offset, may need fender work")
                if offset > max_offset - 5:
                    notes.append("conservative fit, good clearance")

                # Width + offset interaction
                if width >= base_max_width - 0.5 and offset < min_offset + 10:
                    if susp in ("coilovers", "air"):
                        notes.append(
                            "wide wheel with aggressive offset — adjust camber and ride height"
                        )
                    else:
                        notes.append(
                            "wide wheel with aggressive offset — fender rolling or pulling likely needed"
                        )

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

        # Hub ring note: Kansei wheels are 73.1mm, vehicle may differ
        hub_ring_note = ""
        center_bore = specs.get("center_bore", 0)
        if center_bore and center_bore != 73.1:
            hub_ring_note = f"\nHub rings needed: 73.1mm (Kansei) → {center_bore}mm (vehicle)"

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
