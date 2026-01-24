"""DSPy-based fitment assistant with LLM-driven vehicle specs validation."""

from pathlib import Path

import dspy

# Training data for BootstrapFewShot optimization
TRAINING_DATA = [
    # Basic queries with year
    {
        "query": "2020 Honda Civic flush wheels",
        "year": 2020,
        "make": "Honda",
        "model": "Civic",
        "trim": None,
        "fitment_style": "flush",
    },
    {
        "query": "What wheels fit a 2019 BMW M3?",
        "year": 2019,
        "make": "BMW",
        "model": "M3",
        "trim": None,
        "fitment_style": None,
    },
    # Chassis codes (no year in query)
    {
        "query": "e39 528i aggressive fitment",
        "year": None,
        "make": "BMW",
        "model": "528i",
        "trim": "E39",
        "fitment_style": "aggressive",
    },
    {
        "query": "FK8 Civic Type R flush",
        "year": None,
        "make": "Honda",
        "model": "Civic Type R",
        "trim": "FK8",
        "fitment_style": "flush",
    },
    {
        "query": "e30 m3 wheels",
        "year": None,
        "make": "BMW",
        "model": "M3",
        "trim": "E30",
        "fitment_style": None,
    },
    # Invalid chassis+model combos (E30 M5 doesn't exist - parser should still extract correctly)
    {
        "query": "e30 m5 wheels",
        "year": None,
        "make": "BMW",
        "model": "M5",  # M5, not "5 Series" - chassis code E30 + M5
        "trim": "E30",
        "fitment_style": None,
    },
    {
        "query": "e36 m5 aggressive",
        "year": None,
        "make": "BMW",
        "model": "M5",  # M5, not "5 Series"
        "trim": "E36",
        "fitment_style": "aggressive",
    },
    # Nicknames
    {
        "query": "chevy camaro aggressive stance",
        "year": None,
        "make": "Chevrolet",
        "model": "Camaro",
        "trim": None,
        "fitment_style": "aggressive",
    },
    {
        "query": "bimmer 3 series flush fitment",
        "year": None,
        "make": "BMW",
        "model": "3 Series",
        "trim": None,
        "fitment_style": "flush",
    },
    # With year and trim
    {
        "query": "2018 Subaru WRX STI aggressive",
        "year": 2018,
        "make": "Subaru",
        "model": "WRX",
        "trim": "STI",
        "fitment_style": "aggressive",
    },
    {
        "query": "1989 BMW E30 M3 flush wheels",
        "year": 1989,
        "make": "BMW",
        "model": "M3",
        "trim": "E30",
        "fitment_style": "flush",
    },
    # Trucks
    {
        "query": "ford f150 aggressive wheel setup",
        "year": None,
        "make": "Ford",
        "model": "F-150",
        "trim": None,
        "fitment_style": "aggressive",
    },
    # No fitment style
    {
        "query": "2022 Toyota GR86",
        "year": 2022,
        "make": "Toyota",
        "model": "GR86",
        "trim": None,
        "fitment_style": None,
    },
    # Classic cars
    {
        "query": "1978 BMW 2002 wheel options",
        "year": 1978,
        "make": "BMW",
        "model": "2002",
        "trim": None,
        "fitment_style": None,
    },
    {
        "query": "datsun 240z flush",
        "year": None,
        "make": "Datsun",
        "model": "240Z",
        "trim": None,
        "fitment_style": "flush",
    },
    # Tucked style
    {
        "query": "2015 Mazda Miata tucked fitment",
        "year": 2015,
        "make": "Mazda",
        "model": "Miata",
        "trim": None,
        "fitment_style": "tucked",
    },
    # VW
    {
        "query": "mk7 golf r aggressive",
        "year": None,
        "make": "Volkswagen",
        "model": "Golf R",
        "trim": "MK7",
        "fitment_style": "aggressive",
    },
]


class ParseVehicleQuery(dspy.Signature):
    """Extract vehicle info from a wheel fitment query. Only extract year if explicitly stated.

    BMW CHASSIS CODE RULES:
    - When query has "[chassis] [model]" like "e30 m5", extract model=M5, trim=E30
    - E30, E36, E39, E46, E90, F30, G20 are chassis codes, NOT models
    - M3, M5, M4 are models, NOT chassis codes
    - "e30 m5" = make=BMW, model=M5, trim=E30 (NOT model="5 Series")
    - "e39 m5" = make=BMW, model=M5, trim=E39
    - "e30 m3" = make=BMW, model=M3, trim=E30
    """

    query: str = dspy.InputField()

    year: int | None = dspy.OutputField(desc="Year if explicitly stated, else None")
    make: str | None = dspy.OutputField(desc="Vehicle manufacturer")
    model: str | None = dspy.OutputField(
        desc="Vehicle model (M3, M5, Civic, WRX). For BMW, M3/M5/M4 are models, NOT E30/E36"
    )
    trim: str | None = dspy.OutputField(
        desc="Chassis code (E30, E36, E39, FK8) or trim level (STI, Type R)"
    )
    fitment_style: str | None = dspy.OutputField(
        desc="aggressive, flush, tucked, or None"
    )


class ValidateVehicleSpecs(dspy.Signature):
    """Validate vehicle exists and return accurate wheel specifications.

    You are a vehicle specifications expert. CRITICAL: Check chassis code + model validity FIRST.

    STEP 1 - CHECK IF CHASSIS + MODEL IS VALID:
    If trim contains a BMW chassis code (E30, E36, E39, etc.), verify the model exists for that chassis:
    - E30 M5 = INVALID (E30 only had M3, set vehicle_exists=False)
    - E36 M5 = INVALID (E36 only had M3, set vehicle_exists=False)
    - E30 M4 = INVALID (M4 didn't exist until 2014, set vehicle_exists=False)
    - E30 M3 = VALID
    - E36 M3 = VALID
    - E39 M5 = VALID
    - E28 M5 = VALID
    - E34 M5 = VALID

    STEP 2 - IF VALID, RETURN SPECS:
    Use chassis-specific specs:
    - BMW E30/E21/2002: 4x100, 57.1mm bore, max 17", width 7-8.5"
    - BMW E36-F series: 5x120, 72.6mm bore, max 19"
    - BMW G-series (2019+): 5x112, 66.5mm bore
    - Subaru pre-2015 WRX: 5x100
    - Honda pre-2001 Civic: 4x100
    """

    year: int | None = dspy.InputField(desc="Vehicle year if known")
    make: str | None = dspy.InputField(desc="Vehicle manufacturer")
    model: str | None = dspy.InputField(desc="Vehicle model (M3, M5, Civic, etc.)")
    trim: str | None = dspy.InputField(
        desc="Chassis code or trim (E30, E36, E39, FK8, STI). CHECK THIS FOR VALIDITY."
    )

    vehicle_exists: bool = dspy.OutputField(
        desc="FALSE if chassis+model invalid (E30 M5, E36 M5). TRUE only if combination actually existed."
    )
    invalid_reason: str | None = dspy.OutputField(
        desc="If False: 'The [chassis] never had an [model]. Did you mean [suggestions]?' If True: null"
    )
    bolt_pattern: str = dspy.OutputField(
        desc="Bolt pattern. E30=4x100, E36-F=5x120, G-series=5x112"
    )
    center_bore: float = dspy.OutputField(
        desc="Center bore mm. E30=57.1, E36-F=72.6, G-series=66.5"
    )
    stud_size: str = dspy.OutputField(desc="Lug stud size like 'M12x1.5'")
    max_wheel_diameter: int = dspy.OutputField(
        desc="Max diameter. E30=17, E36=18, modern=19-20"
    )
    min_wheel_diameter: int = dspy.OutputField(
        desc="Min diameter for brake clearance. Usually 15-17"
    )
    typical_width_range: str = dspy.OutputField(
        desc="Width range. E30='7-8.5', modern='8-10'"
    )
    typical_offset_range: str = dspy.OutputField(desc="Offset range like '+25 to +45'")


class GenerateFitmentResponse(dspy.Signature):
    """Generate Kansei wheel recommendations. ONLY recommend Kansei brand wheels."""

    vehicle_info: str = dspy.InputField(
        desc="Vehicle details with validated specs (bolt pattern, center bore, size limits)"
    )
    fitment_data: str = dspy.InputField(
        desc="Community fitment specs (for reference) and KANSEI WHEELS section"
    )
    user_query: str = dspy.InputField()

    response: str = dspy.OutputField(
        desc="""Generate Kansei wheel recommendations following these rules:

1. ONLY recommend Kansei brand wheels - NEVER mention competitor brands
2. Use the VALIDATED SPECS provided - these are accurate for this specific vehicle
3. Only recommend wheel sizes within the max_wheel_diameter limit
4. List specific Kansei wheels from the KANSEI WHEELS section with model, size, offset, price, and URL
5. If no Kansei wheels match the bolt pattern or size constraints, clearly state that
6. If no year was provided, do NOT make up a year
7. Never hallucinate Kansei models that aren't in the provided data"""
    )


class FitmentAssistant(dspy.Module):
    """DSPy module for wheel fitment assistance with LLM-driven validation."""

    def __init__(self) -> None:
        super().__init__()
        # Step 1: Parse the query
        self.parse_query = dspy.ChainOfThought(ParseVehicleQuery)
        # Step 2: Validate vehicle and get accurate specs (chain of thought for reasoning)
        self.validate_specs = dspy.ChainOfThought(ValidateVehicleSpecs)
        # Step 3: Generate response
        self.generate_response = dspy.Predict(GenerateFitmentResponse)

    def forward(
        self,
        query: str,
        fitment_data: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        trim: str | None = None,
        fitment_style: str | None = None,
    ) -> dspy.Prediction:
        # Step 1: Parse the query if vehicle info not provided
        if not any([year, make, model]):
            parsed = self.parse_query(query=query)
            year = parsed.year if parsed.year and str(parsed.year) != "None" else None
            make = parsed.make if parsed.make and str(parsed.make) != "None" else None
            model = (
                parsed.model if parsed.model and str(parsed.model) != "None" else None
            )
            trim = parsed.trim if parsed.trim and str(parsed.trim) != "None" else None
            fitment_style = (
                parsed.fitment_style
                if parsed.fitment_style and str(parsed.fitment_style) != "None"
                else None
            )

            # Validate: year should only be set if it was in the original query
            if year is not None:
                year_str = str(year)
                if year_str not in query and not any(
                    year_str in part for part in query.split()
                ):
                    year = None

        # Validate year range
        if year is not None and not (1900 <= year <= 2030):
            year = None

        # Step 2: Validate vehicle and get accurate specs via LLM
        specs = self.validate_specs(
            year=year,
            make=make,
            model=model,
            trim=trim,
        )

        # Check if vehicle is invalid
        vehicle_exists = specs.vehicle_exists
        if isinstance(vehicle_exists, str):
            vehicle_exists = vehicle_exists.lower() == "true"

        if not vehicle_exists:
            invalid_reason = (
                specs.invalid_reason or "This vehicle combination does not exist."
            )
            return dspy.Prediction(
                response=f"**Vehicle Not Found**\n\n{invalid_reason}",
                parsed={
                    "year": year,
                    "make": make,
                    "model": model,
                    "trim": trim,
                    "fitment_style": fitment_style,
                },
                specs=None,
                vehicle_exists=False,
                needs_clarification=True,
            )

        # Extract validated specs
        bolt_pattern = str(specs.bolt_pattern) if specs.bolt_pattern else "Unknown"
        center_bore = float(specs.center_bore) if specs.center_bore else 0.0
        max_diameter = int(specs.max_wheel_diameter) if specs.max_wheel_diameter else 20
        min_diameter = int(specs.min_wheel_diameter) if specs.min_wheel_diameter else 15
        width_range = (
            str(specs.typical_width_range) if specs.typical_width_range else "7-9"
        )
        offset_range = (
            str(specs.typical_offset_range)
            if specs.typical_offset_range
            else "+20 to +45"
        )
        stud_size = str(specs.stud_size) if specs.stud_size else "M12x1.5"

        # Build vehicle info string with validated specs
        year_display = str(year) if year else "not specified"
        vehicle_info = f"""Year: {year_display}
Make: {make or "not specified"}
Model: {model or "not specified"}
Trim/Chassis: {trim or "not specified"}
Fitment Style: {fitment_style or "not specified"}

VALIDATED SPECS (use these - they are accurate for this vehicle):
- Bolt Pattern: {bolt_pattern}
- Center Bore: {center_bore}mm
- Stud Size: {stud_size}
- Wheel Diameter: {min_diameter}" to {max_diameter}" (DO NOT recommend larger than {max_diameter}")
- Typical Width: {width_range}"
- Typical Offset: {offset_range}

IMPORTANT: If year is "not specified", do NOT make up a year in your response.
IMPORTANT: Only recommend wheels up to {max_diameter}" diameter for this vehicle."""

        # Step 3: Generate the fitment response
        result = self.generate_response(
            vehicle_info=vehicle_info,
            fitment_data=fitment_data,
            user_query=query,
        )

        response_text = result.response

        # Post-validation: strip fabricated years
        if year is None and _contains_fabricated_year(response_text, query):
            response_text = _remove_fabricated_years(response_text, query)

        return dspy.Prediction(
            response=response_text,
            parsed={
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "fitment_style": fitment_style,
            },
            specs={
                "bolt_pattern": bolt_pattern,
                "center_bore": center_bore,
                "stud_size": stud_size,
                "max_wheel_diameter": max_diameter,
                "min_wheel_diameter": min_diameter,
                "typical_width_range": width_range,
                "typical_offset_range": offset_range,
            },
            vehicle_exists=True,
            needs_clarification=False,
        )


def _contains_fabricated_year(response: str, query: str) -> bool:
    """Check if response contains a year that wasn't in the original query."""
    import re

    response_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", response))
    query_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", query))
    fabricated = response_years - query_years
    return len(fabricated) > 0


def _remove_fabricated_years(response: str, query: str) -> str:
    """Remove fabricated years from response, especially in the title line."""
    import re

    query_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", query))
    response_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", response))
    fabricated_years = response_years - query_years

    for year in fabricated_years:
        response = re.sub(rf"\*\*{year}\s+", "**", response)
        response = re.sub(rf"^{year}\s+", "", response, flags=re.MULTILINE)
        response = re.sub(rf"(\*\*[^*]*){year}\s*([^*]*\*\*)", r"\1\2", response)

    return response


def _parse_metric(example: dspy.Example, prediction: dspy.Prediction) -> float:
    """Metric for evaluating query parsing accuracy."""
    score = 0.0
    total = 5.0

    if example.year == prediction.year:
        score += 1.0
    elif example.year is None and prediction.year is None:
        score += 1.0

    if example.make and prediction.make:
        if example.make.lower() == str(prediction.make).lower():
            score += 1.0
    elif example.make is None and (
        prediction.make is None or str(prediction.make) == "None"
    ):
        score += 1.0

    if example.model and prediction.model:
        if (
            example.model.lower() in str(prediction.model).lower()
            or str(prediction.model).lower() in example.model.lower()
        ):
            score += 1.0
    elif example.model is None and (
        prediction.model is None or str(prediction.model) == "None"
    ):
        score += 1.0

    if example.trim and prediction.trim:
        if (
            example.trim.lower() in str(prediction.trim).lower()
            or str(prediction.trim).lower() in example.trim.lower()
        ):
            score += 1.0
    elif example.trim is None and (
        prediction.trim is None or str(prediction.trim) == "None"
    ):
        score += 1.0

    if example.fitment_style and prediction.fitment_style:
        if example.fitment_style.lower() == str(prediction.fitment_style).lower():
            score += 1.0
    elif example.fitment_style is None and (
        prediction.fitment_style is None or str(prediction.fitment_style) == "None"
    ):
        score += 1.0

    return score / total


def create_fitment_assistant(
    model: str = "openai/gpt-4o",
    optimize: bool = False,
) -> FitmentAssistant:
    """Create and configure a FitmentAssistant with the specified model.

    Uses gpt-4o for better accuracy on vehicle specs (bolt patterns, center bore, etc.)
    """
    lm = dspy.LM(model, max_tokens=512)
    dspy.configure(lm=lm)

    assistant = FitmentAssistant()

    if optimize:
        assistant = _optimize_assistant(assistant, lm)

    # Try to load optimized weights if they exist
    optimized_path = Path(__file__).parent / "dspy_optimized.json"
    if optimized_path.exists():
        try:
            assistant.load(str(optimized_path))
        except Exception:
            pass

    return assistant


def _optimize_assistant(assistant: FitmentAssistant, lm: dspy.LM) -> FitmentAssistant:
    """Run BootstrapFewShot optimization on the assistant."""
    trainset = [
        dspy.Example(
            query=d["query"],
            year=d["year"],
            make=d["make"],
            model=d["model"],
            trim=d["trim"],
            fitment_style=d["fitment_style"],
        ).with_inputs("query")
        for d in TRAINING_DATA
    ]

    optimizer = dspy.BootstrapFewShot(
        metric=_parse_metric,
        max_bootstrapped_demos=4,
        max_labeled_demos=4,
    )

    optimized = optimizer.compile(
        assistant.parse_query,
        trainset=trainset,
    )

    assistant.parse_query = optimized

    optimized_path = Path(__file__).parent / "dspy_optimized.json"
    try:
        assistant.save(str(optimized_path))
    except Exception:
        pass

    return assistant


def optimize_and_save(model: str = "openai/gpt-4o-mini") -> None:
    """Run optimization and save the results."""
    print("Starting DSPy optimization...")
    lm = dspy.LM(model, max_tokens=512)
    dspy.configure(lm=lm)

    assistant = FitmentAssistant()
    assistant = _optimize_assistant(assistant, lm)

    print("Optimization complete! Optimized weights saved to dspy_optimized.json")
