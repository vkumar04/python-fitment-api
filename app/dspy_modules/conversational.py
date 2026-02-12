"""DSPy ReAct agent for conversational fitment assistance.

Combines vehicle identification, NHTSA lookup, catalog search,
and AI-powered recommendation into a single conversational agent.
"""

import dspy

from app.config import get_settings
from app.dspy_modules.signatures import FitmentQA, IdentifyVehicle, RecommendWheels
from app.tools.nhtsa_tools import (
    decode_vin,
    find_kansei_fitment,
    get_models_for_make_year,
    lookup_vehicle,
)


class FitmentAgentSignature(dspy.Signature):
    """You are the Kansei Wheels fitment assistant. When a user mentions a vehicle:
    1. Call lookup_vehicle to get bolt pattern, hub bore, and OEM specs.
    2. Call find_kansei_fitment with year, make, model, trim to get scored compatible wheels.
       This automatically filters out incompatible wheels (bore too small, bolt mismatch)
       and includes poke/stance info, tire recommendations, and brake clearance warnings.
       For staggered-stock vehicles it also returns matched front/rear pairings.
    3. Present the top-scoring wheels with their fitment notes.

    EVERY wheel recommendation MUST include ALL of these fields — no exceptions, no abbreviating:
    - Bolt pattern (e.g. 5x120)
    - Hub bore (e.g. 73.1mm) and whether hub-centric rings are needed
    - Wheel size (diameter x width), offset, and finish
    - Poke/stance calculation and any modification notes
    - Tire recommendation

    For staggered pairings, list BOTH front and rear wheels with FULL specs for each.
    Each wheel in the pair is a separate purchase — the buyer needs complete info for both.

    Never recommend a wheel that was filtered out by the fitment engine."""

    user_message: str = dspy.InputField(
        desc="The user's message about their vehicle or fitment question"
    )
    conversation_history: str = dspy.InputField(
        desc="Previous conversation messages for context"
    )
    response: str = dspy.OutputField(
        desc="Helpful response with specific Kansei wheel recommendations. "
        "EVERY option MUST list: bolt pattern, hub bore, wheel size, offset, finish, "
        "poke calculation, tire recommendation, and mods needed. "
        "For staggered pairings, show full specs for BOTH front AND rear wheels."
    )


class KanseiFitmentAgent(dspy.Module):
    """ReAct-based conversational agent for Kansei wheel fitment.

    Uses tools to look up vehicle info, search the catalog, and
    produce personalized wheel recommendations.
    """

    def __init__(self) -> None:
        super().__init__()
        self.identify = dspy.ChainOfThought(IdentifyVehicle)
        self.recommend = dspy.ChainOfThought(RecommendWheels)
        self.qa = dspy.ChainOfThought(FitmentQA)
        self.agent = dspy.ReAct(
            FitmentAgentSignature,
            tools=[
                lookup_vehicle,
                find_kansei_fitment,
                decode_vin,
                get_models_for_make_year,
            ],
            max_iters=8,
        )

    def forward(
        self, user_message: str, conversation_history: str = ""
    ) -> dspy.Prediction:
        """Process a user message through the fitment agent."""
        return self.agent(
            user_message=user_message,
            conversation_history=conversation_history,
        )


def _configure_dspy() -> None:
    """Configure DSPy with the LM from settings."""
    settings = get_settings()
    lm = dspy.LM(settings.dspy_lm_model, max_tokens=1024)
    dspy.configure(lm=lm)


# Lazy singleton
_agent: KanseiFitmentAgent | None = None


def get_fitment_agent() -> KanseiFitmentAgent:
    """Get or create the singleton fitment agent."""
    global _agent
    if _agent is None:
        _configure_dspy()
        _agent = KanseiFitmentAgent()
    return _agent
