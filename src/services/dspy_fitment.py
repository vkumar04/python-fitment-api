"""DSPy-based fitment assistant with optimized prompts and validation."""

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
        "year": None,  # E39 = 1995-2003, but user didn't specify
        "make": "BMW",
        "model": "528i",
        "trim": "E39",
        "fitment_style": "aggressive",
    },
    {
        "query": "FK8 Civic Type R flush",
        "year": None,  # FK8 = 2017-2021, but user didn't specify
        "make": "Honda",
        "model": "Civic Type R",
        "trim": "FK8",
        "fitment_style": "flush",
    },
    {
        "query": "e30 m3 wheels",
        "year": None,  # E30 M3 = 1986-1991, but user didn't specify
        "make": "BMW",
        "model": "M3",
        "trim": "E30",
        "fitment_style": None,
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
        "year": None,  # MK7 = 2015-2021
        "make": "Volkswagen",
        "model": "Golf R",
        "trim": "MK7",
        "fitment_style": "aggressive",
    },
]


# Simplified signatures - let DSPy optimize the prompts
class ParseVehicleQuery(dspy.Signature):
    """Extract vehicle info from a wheel fitment query. Only extract year if explicitly stated."""

    query: str = dspy.InputField()

    year: int | None = dspy.OutputField(desc="Year if explicitly stated, else None")
    make: str | None = dspy.OutputField(desc="Vehicle manufacturer")
    model: str | None = dspy.OutputField(desc="Vehicle model name")
    trim: str | None = dspy.OutputField(
        desc="Trim level or chassis code (e.g., STI, E39, FK8)"
    )
    fitment_style: str | None = dspy.OutputField(
        desc="aggressive, flush, tucked, or None"
    )


class GenerateFitmentResponse(dspy.Signature):
    """Generate Kansei wheel recommendations. ONLY recommend Kansei brand wheels."""

    vehicle_info: str = dspy.InputField(
        desc="Vehicle details, bolt pattern, center bore"
    )
    fitment_data: str = dspy.InputField(
        desc="Community fitment specs (for reference) and KANSEI WHEELS section"
    )
    user_query: str = dspy.InputField()

    response: str = dspy.OutputField(
        desc="""Generate Kansei wheel recommendations following these rules:

1. ONLY recommend Kansei brand wheels - NEVER mention competitor brands (JNC, TSW, SSR, Work, Enkei, etc.)
2. Use community fitment data to understand what wheel sizes fit, but DO NOT recommend those wheel brands
3. List specific Kansei wheels from the KANSEI WHEELS section with model, size, offset, price, and URL
4. If no Kansei wheels match the bolt pattern, clearly state that
5. Include bolt pattern and center bore in your response
6. If no year was provided, do NOT make up a year
7. Never hallucinate Kansei models that aren't in the provided data"""
    )


class FitmentAssistant(dspy.Module):
    """DSPy module for wheel fitment assistance with validation."""

    def __init__(self) -> None:
        super().__init__()
        # Use ChainOfThought for query parsing (better for complex queries)
        self.parse_query = dspy.ChainOfThought(ParseVehicleQuery)
        # Use Predict for response generation (faster)
        self.generate_response = dspy.Predict(GenerateFitmentResponse)

    def forward(
        self,
        query: str,
        fitment_data: str,
        bolt_pattern: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        trim: str | None = None,
        fitment_style: str | None = None,
    ) -> dspy.Prediction:
        # Parse the query if vehicle info not provided
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
                # Check if year appears in the query
                year_str = str(year)
                if year_str not in query and not any(
                    year_str in part for part in query.split()
                ):
                    # LLM hallucinated a year - remove it
                    year = None

        # Validate year range
        if year is not None and not (1900 <= year <= 2030):
            year = None  # Invalid year, treat as not specified

        # Build vehicle info string
        year_display = str(year) if year else "not specified"
        vehicle_info = f"""Year: {year_display}
Make: {make or "not specified"}
Model: {model or "not specified"}
Trim: {trim or "not specified"}
Fitment Style: {fitment_style or "not specified"}
Bolt Pattern: {bolt_pattern}

IMPORTANT: If year is "not specified", do NOT make up a year in your response."""

        # Generate the fitment response
        result = self.generate_response(
            vehicle_info=vehicle_info,
            fitment_data=fitment_data,
            user_query=query,
        )

        response_text = result.response

        # Post-validation: if no year was provided but response contains a fabricated year
        # Strip out fabricated years from the response
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
                "bolt_pattern": bolt_pattern,
            },
            needs_clarification=False,
        )


def _contains_fabricated_year(response: str, query: str) -> bool:
    """Check if response contains a year that wasn't in the original query."""
    import re

    # Find all 4-digit years in response (1900-2030 range)
    response_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", response))
    query_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", query))

    # If response has years that query doesn't, they might be fabricated
    fabricated = response_years - query_years
    return len(fabricated) > 0


def _remove_fabricated_years(response: str, query: str) -> str:
    """Remove fabricated years from response, especially in the title line."""
    import re

    # Find years in query (these are allowed)
    query_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", query))

    # Find years in response that aren't in query
    response_years = set(re.findall(r"\b(19\d{2}|20[0-2]\d|2030)\b", response))
    fabricated_years = response_years - query_years

    # Remove fabricated years from title lines (e.g., "**1997 BMW 528i**" -> "**BMW 528i**")
    for year in fabricated_years:
        # Remove year from bold title pattern
        response = re.sub(rf"\*\*{year}\s+", "**", response)
        # Remove year from start of lines
        response = re.sub(rf"^{year}\s+", "", response, flags=re.MULTILINE)
        # Remove standalone year references in title context
        response = re.sub(rf"(\*\*[^*]*){year}\s*([^*]*\*\*)", r"\1\2", response)

    return response


def _parse_metric(example: dspy.Example, prediction: dspy.Prediction) -> float:
    """Metric for evaluating query parsing accuracy."""
    score = 0.0
    total = 5.0  # 5 fields to check

    # Check each field
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
    model: str = "openai/gpt-4o-mini",
    optimize: bool = False,
) -> FitmentAssistant:
    """Create and configure a FitmentAssistant with the specified model.

    Args:
        model: The LLM model to use
        optimize: If True, run BootstrapFewShot optimization (slow, do once)
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
            pass  # Use unoptimized if load fails

    return assistant


def _optimize_assistant(assistant: FitmentAssistant, lm: dspy.LM) -> FitmentAssistant:
    """Run BootstrapFewShot optimization on the assistant."""
    # Create training examples
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

    # Create optimizer
    optimizer = dspy.BootstrapFewShot(
        metric=_parse_metric,
        max_bootstrapped_demos=4,
        max_labeled_demos=4,
    )

    # Optimize the parse_query module
    optimized = optimizer.compile(
        assistant.parse_query,
        trainset=trainset,
    )

    # Replace with optimized version
    assistant.parse_query = optimized

    # Save optimized weights
    optimized_path = Path(__file__).parent / "dspy_optimized.json"
    try:
        assistant.save(str(optimized_path))
    except Exception:
        pass

    return assistant


def optimize_and_save(model: str = "openai/gpt-4o-mini") -> None:
    """Run optimization and save the results. Call this once to generate optimized prompts."""
    print("Starting DSPy optimization...")
    lm = dspy.LM(model, max_tokens=512)
    dspy.configure(lm=lm)

    assistant = FitmentAssistant()
    assistant = _optimize_assistant(assistant, lm)

    print("Optimization complete! Optimized weights saved to dspy_optimized.json")
