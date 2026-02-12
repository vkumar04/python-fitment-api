"""DSPy Signatures for the Kansei Fitment Assistant."""

from typing import Optional

import dspy


class IdentifyVehicle(dspy.Signature):
    """Extract vehicle year, make, model, trim, and chassis context from a user's
    natural language input. If the user provides a VIN, flag it for VIN decoding."""

    user_input: str = dspy.InputField(desc="User's message about their vehicle")
    year: Optional[int] = dspy.OutputField(desc="Vehicle model year")
    make: str = dspy.OutputField(desc="Vehicle manufacturer (e.g., Toyota, Honda)")
    model: str = dspy.OutputField(desc="Vehicle model (e.g., Camry, Civic)")
    trim: Optional[str] = dspy.OutputField(
        desc="Trim level if mentioned (e.g., Sport, SE, Type R, STI, GT, SS, Nismo, N)"
    )
    chassis_code: Optional[str] = dspy.OutputField(
        desc="Chassis code if mentioned (e.g., E30, FK8, ZN6, S550, VA)"
    )
    suspension_type: Optional[str] = dspy.OutputField(
        desc="Suspension type if mentioned: 'stock', 'lowered', 'coilovers', 'air', 'lifted'"
    )
    use_case: Optional[str] = dspy.OutputField(
        desc="Intended use if mentioned: 'daily', 'track', 'show', 'drift', 'off-road'"
    )
    is_vin: bool = dspy.OutputField(desc="True if the input contains a VIN number")
    vin: Optional[str] = dspy.OutputField(desc="The VIN string if detected")


class RecommendWheels(dspy.Signature):
    """Given a vehicle's specs and matching Kansei wheels, produce a personalized
    recommendation with fitment notes. Include poke/flush/tuck stance info using
    labels: flush (±3mm), mild poke/tuck (3-10mm), moderate poke/tuck (10-20mm),
    aggressive/deep tuck (>20mm). Include tire size recommendations and brake
    clearance notes (❌ hard reject, ⚠️ warning) when available.
    Consider the user's stated preferences for style, budget, and use case."""

    vehicle_info: str = dspy.InputField(
        desc="Vehicle year/make/model/trim, OEM specs, chassis code, and brake info"
    )
    matching_wheels: str = dspy.InputField(
        desc="JSON list of compatible Kansei wheels with fitment scores, "
        "poke calculations, tire recommendations, and brake clearance data. "
        "Hub bore is per-wheel (73.1mm street, 106.1mm truck)."
    )
    user_preferences: str = dspy.InputField(
        desc="User's style, budget, use-case, and stance preferences"
    )
    recommendation: str = dspy.OutputField(
        desc="Natural language recommendation with top picks, fitment notes, "
        "tire sizes, poke/stance info, and any brake clearance warnings"
    )
    top_picks: str = dspy.OutputField(desc="JSON array of top 3-5 SKUs with reasoning")


class FitmentQA(dspy.Signature):
    """Answer wheel fitment questions using vehicle specs and Kansei catalog knowledge.
    Be specific about bolt patterns, offsets, hub bore compatibility (per-wheel bore
    varies: 73.1mm street, 106.1mm truck), poke/flush/tuck stance (flush ±3mm,
    mild/moderate/aggressive poke, mild/moderate/deep tuck), tire sizing, and
    brake clearance (❌ hard reject vs ⚠️ warning)."""

    question: str = dspy.InputField(desc="User's fitment question")
    vehicle_context: str = dspy.InputField(desc="Known vehicle information")
    catalog_context: str = dspy.InputField(desc="Relevant Kansei wheel data")
    answer: str = dspy.OutputField(desc="Detailed, accurate fitment answer")
