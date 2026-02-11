"""DSPy Signatures for the fitment pipeline.

Each signature defines a clear input/output contract for one step in the pipeline.
"""

from typing import Literal

import dspy


class ParseVehicleInput(dspy.Signature):
    """Parse user input to extract vehicle information.

    The user may provide:
    - Year + Make + Model: "2020 Honda Civic"
    - Chassis code: "E30", "FK8", "S14"
    - Chassis + Model: "E30 M3", "E39 M5"
    - Nicknames: "bimmer", "chevy", "vette"

    CHASSIS CODE RULES (BMW):
    - E30, E36, E46, E90, F30, G20 are CHASSIS codes
    - M3, M5, M4, 325i, 528i are MODEL names
    - "E30 M3" = chassis_code=E30, model=M3, make=BMW
    - "E30" alone = chassis_code=E30, make=BMW, model=None (needs clarification)

    SUSPENSION KEYWORDS:
    - "stock", "factory", "oem" = stock
    - "lowered", "dropped", "lowering springs" = lowered
    - "coilovers", "coils", "slammed" = coilovers
    - "bagged", "air ride", "air suspension" = air
    - "lifted", "leveled" = lifted

    FITMENT STYLE KEYWORDS:
    - "flush", "fitted", "daily" = flush
    - "aggressive", "poke", "stance" = aggressive
    - "tucked", "tuck" = tucked
    - "track", "performance", "grip" = track
    """

    user_input: str = dspy.InputField(desc="Raw user query about wheel fitment")

    # Extracted vehicle info
    year: int | None = dspy.OutputField(
        desc="Vehicle year if explicitly stated (e.g., 2020). None if not mentioned."
    )
    make: str | None = dspy.OutputField(
        desc="Normalized manufacturer name (BMW, Honda, Chevrolet, Toyota, etc.)"
    )
    model: str | None = dspy.OutputField(
        desc="Model name (M3, Civic, Camaro). For BMW, M3/M5 are models, not E30/E36."
    )
    chassis_code: str | None = dspy.OutputField(
        desc="Chassis/platform code if mentioned (E30, E36, FK8, S14, VA). Uppercase."
    )
    trim: str | None = dspy.OutputField(
        desc="Trim level if specified (STI, Type R, GT, Sport)"
    )
    suspension: Literal["stock", "lowered", "coilovers", "air", "lifted"] | None = (
        dspy.OutputField(desc="Suspension type if mentioned. None if not specified.")
    )
    fitment_style: Literal["flush", "aggressive", "tucked", "track"] | None = dspy.OutputField(
        desc="Desired fitment style if mentioned. None if not specified."
    )
    is_valid_input: bool = dspy.OutputField(
        desc="True if we extracted at least make OR chassis_code. False if input is unclear."
    )
    clarification_needed: str | None = dspy.OutputField(
        desc="If is_valid_input=False, explain what info is needed. Otherwise None."
    )


class ValidateVehicleSpecs(dspy.Signature):
    """Validate that the vehicle exists and the specs are correct.

    This is called AFTER we have specs (from DB or web search).
    It validates that the combination is real and specs are reasonable.

    VALIDATION RULES:
    1. Chassis + Model must be valid (E30 only had M3, not M5)
    2. Year must be within production range for that model
    3. Bolt pattern must match known patterns for that vehicle
    4. Specs must be within reasonable ranges

    KNOWN INVALID COMBINATIONS:
    - E30 M5 (E30 only had M3)
    - E36 M5 (E36 only had M3)
    - E30 M4 (M4 didn't exist until 2014)
    - Pre-2015 WRX STI with 5x114.3 (was 5x100 until VA chassis)
    """

    # Input: parsed vehicle info + retrieved specs
    year: int | None = dspy.InputField()
    make: str | None = dspy.InputField()
    model: str | None = dspy.InputField()
    chassis_code: str | None = dspy.InputField()
    trim: str | None = dspy.InputField()

    # Specs to validate (from DB or web search)
    bolt_pattern: str = dspy.InputField(desc="e.g., '5x120', '4x100'")
    center_bore: float = dspy.InputField(desc="Center bore in mm")
    min_diameter: int = dspy.InputField()
    max_diameter: int = dspy.InputField()
    min_width: float = dspy.InputField()
    max_width: float = dspy.InputField()
    min_offset: int = dspy.InputField()
    max_offset: int = dspy.InputField()

    # Outputs
    is_valid: bool = dspy.OutputField(
        desc="True if vehicle exists AND specs are correct for it"
    )
    validation_errors: list[str] = dspy.OutputField(
        desc="List of validation errors if is_valid=False. Empty list if valid."
    )
    corrected_specs: dict | None = dspy.OutputField(
        desc="If specs are wrong but we know correct ones, provide them. Otherwise None."
    )
    suggestions: str | None = dspy.OutputField(
        desc="If invalid, suggest what the user might have meant (e.g., 'Did you mean E39 M5?')"
    )


class ValidateFitmentMatch(dspy.Signature):
    """Validate that Kansei wheels actually fit the vehicle.

    Takes vehicle specs and Kansei wheel options, returns only wheels that fit.

    FITMENT RULES:
    1. Bolt pattern MUST match exactly
    2. Diameter must be within min_diameter to max_diameter
    3. Width must be within min_width to max_width (adjusted for suspension)
    4. Offset must be within min_offset to max_offset (adjusted for suspension)

    SUSPENSION ADJUSTMENTS:
    - stock: use base offset range
    - lowered: can go 5mm more aggressive (lower offset)
    - coilovers: can go 10mm more aggressive
    - air: can go 15mm more aggressive
    - lifted: may need MORE offset (less poke) for clearance

    FLAG MODIFICATIONS:
    - If wheel fits but is aggressive, note "may require fender rolling"
    - If offset is at the edge, note "may have slight poke" or "may rub on bumps"
    """

    # Vehicle specs
    bolt_pattern: str = dspy.InputField()
    center_bore: float = dspy.InputField()
    min_diameter: int = dspy.InputField()
    max_diameter: int = dspy.InputField()
    min_width: float = dspy.InputField()
    max_width: float = dspy.InputField()
    min_offset: int = dspy.InputField()
    max_offset: int = dspy.InputField()
    suspension: str | None = dspy.InputField(
        desc="stock, lowered, coilovers, air, or lifted"
    )

    # Kansei wheels to validate (JSON string of wheel list)
    kansei_wheels_json: str = dspy.InputField(
        desc="JSON array of Kansei wheel options with diameter, width, offset, model, price, url"
    )

    # Outputs
    valid_wheels_json: str = dspy.OutputField(
        desc="JSON array of wheels that fit, with any notes about fitment"
    )
    rejected_wheels_json: str = dspy.OutputField(
        desc="JSON array of wheels that don't fit, with reason for rejection"
    )
    fitment_summary: str = dspy.OutputField(
        desc="Brief summary: 'X wheels fit perfectly, Y need modifications, Z incompatible'"
    )


class GenerateFitmentResponse(dspy.Signature):
    """Generate a conversational response with wheel recommendations.

    TONE: Friendly car enthusiast, knowledgeable but not condescending.
    Like talking to a friend at a car meet who knows their stuff.

    STRUCTURE:
    1. Acknowledge the vehicle (brief, 1 line)
    2. Key specs (bolt pattern, bore, size limits)
    3. Wheel options (structured, clear)
    4. Recommendation (which option and why)
    5. Single disclaimer at end

    RULES:
    - Get straight to the point - no "Great question!" or "Let me help you"
    - Use markdown formatting (bold for headers, lists for options)
    - Always show BOTH front and rear specs (even if square setup)
    - Include Kansei wheel links when available
    - Mention hub rings if center bore doesn't match (Kansei = 73.1mm)
    - Note suspension requirements honestly
    - If no Kansei wheels fit, say so honestly

    NEVER:
    - Invent specs not in the data
    - Recommend competitor brands
    - Make up Kansei models
    - Use filler phrases
    """

    # Context
    vehicle_summary: str = dspy.InputField(
        desc="Vehicle info: year, make, model, chassis, suspension preference"
    )
    vehicle_specs: str = dspy.InputField(
        desc="Validated specs: bolt pattern, bore, diameter/width/offset ranges"
    )
    community_fitments: str = dspy.InputField(
        desc="Community fitment data (proven setups) or empty if none"
    )
    kansei_options: str = dspy.InputField(
        desc="Validated Kansei wheels that fit, with prices and links"
    )
    fitment_style: str | None = dspy.InputField(
        desc="User's desired style: flush, aggressive, tucked, or None"
    )

    # Output
    response: str = dspy.OutputField(
        desc="Conversational markdown response with wheel recommendations"
    )


class SearchVehicleSpecs(dspy.Signature):
    """Resolve vehicle wheel specifications from your knowledge.

    CRITICAL SAFETY: Bolt pattern and center bore are PHYSICAL CONSTRAINTS.
    A wrong bolt pattern means the wheel CANNOT physically mount on the hub.
    A wrong center bore causes vibration and potential wheel failure.

    BOLT PATTERN RULES (common mistakes to avoid):
    - BMW E30 base models (318i, 325i): 4x100, center bore 57.1mm
    - BMW E30 M3: 5x120, center bore 72.6mm (DIFFERENT from base E30!)
    - BMW E36/E46/E90/F-series: 5x120, center bore 72.6mm
    - BMW G-series (G20, G80, G82, 2019+): 5x112, center bore 66.5mm (NOT 5x120!)
    - Honda Civic pre-2006: 4x100; 2006+: 5x114.3
    - Honda Civic Type R FK8/FL5: 5x120 (NOT 5x114.3 like regular Civic!)
    - Subaru WRX pre-2015: 5x100; 2015+ VA chassis: 5x114.3
    - Subaru WRX STI pre-2015: 5x114.3; same as 2015+ WRX
    - Toyota 86 / Scion FR-S / Subaru BRZ (ZN6): 5x100
    - Toyota GR86 (ZN8, 2022+): 5x114.3 (changed from 5x100!)
    - Toyota GR Supra A90: 5x112 (BMW platform)
    - Nissan 240SX S13: 4x114.3; S14: 5x114.3
    - Porsche: 5x130

    TRIM MATTERS: Performance trims often have different specs than base models.
    The M3 has different specs from the 325i on the same chassis. The STI has
    different specs from the base WRX on certain generations. Always consider
    the specific trim when resolving specs.

    OFFSET RANGES: Provide safe aftermarket ranges, not just OEM.
    - min_offset: the most aggressive (lowest) offset that fits without
      fender work on stock suspension
    - max_offset: the most conservative (highest) offset before the wheel
      sits too far inboard

    If you are NOT confident about the bolt pattern, set confidence below 0.5.
    """

    year: int | None = dspy.InputField()
    make: str = dspy.InputField()
    model: str = dspy.InputField()
    chassis_code: str | None = dspy.InputField()
    trim: str | None = dspy.InputField(
        desc="Trim level if known (M3, STI, Type R, GT, Sport). Affects specs."
    )

    # What we found
    bolt_pattern: str = dspy.OutputField(desc="e.g., '5x120'")
    center_bore: float = dspy.OutputField(desc="Center bore in mm")
    stud_size: str = dspy.OutputField(desc="e.g., 'M12x1.5'")
    oem_diameter: int = dspy.OutputField(desc="Stock wheel diameter")
    min_brake_clearance_diameter: int = dspy.OutputField(
        desc="Minimum diameter that clears the brake calipers. For cars with big brakes "
        "(e.g. BMW M cars with Brembo, Civic Type R, Subaru STI), this is often 17\" or 18\". "
        "For economy cars with small brakes, this can be as low as 14\"."
    )
    min_diameter: int = dspy.OutputField(desc="Minimum safe diameter (at least min_brake_clearance_diameter)")
    max_diameter: int = dspy.OutputField(desc="Maximum recommended diameter")
    oem_width: float = dspy.OutputField(desc="Stock FRONT wheel width in inches")
    oem_rear_width: float = dspy.OutputField(
        desc="Stock REAR wheel width in inches. Same as oem_width for square setups, "
        "wider for staggered (e.g. E39 M5 is 8.0 front / 9.5 rear)."
    )
    min_width: float = dspy.OutputField(desc="Minimum recommended width")
    max_width: float = dspy.OutputField(desc="Maximum recommended width")
    oem_offset: int = dspy.OutputField(desc="Stock FRONT offset in mm")
    oem_rear_offset: int = dspy.OutputField(
        desc="Stock REAR offset in mm. Same as oem_offset for square setups, "
        "different for staggered (e.g. E39 M5 is +20 front / +22 rear)."
    )
    min_offset: int = dspy.OutputField(desc="Minimum offset (more poke)")
    max_offset: int = dspy.OutputField(desc="Maximum offset (more tuck)")
    is_staggered_stock: bool = dspy.OutputField(
        desc="True if the vehicle came from factory with a staggered setup "
        "(different front/rear wheel sizes). E.g. E39 M5 (18x8/18x9.5), "
        "C6 Corvette (18x8.5/19x10), 370Z (18x8/18x9). False for square setups."
    )
    source_url: str = dspy.OutputField(desc="Primary source URL for this data")
    confidence: float = dspy.OutputField(desc="0.0-1.0 confidence in the data")
