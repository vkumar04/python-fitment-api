"""Enums for fitment-related constants."""

from enum import Enum


class FitmentStyle(str, Enum):
    """Wheel fitment styles based on offset and stance."""

    AGGRESSIVE = "aggressive"
    FLUSH = "flush"
    TUCKED = "tucked"

    @classmethod
    def from_string(cls, value: str | None) -> "FitmentStyle | None":
        """Convert string to enum, returning None if invalid."""
        if not value:
            return None
        try:
            return cls(value.lower())
        except ValueError:
            return None


class FitmentSetup(str, Enum):
    """Wheel setup configuration."""

    SQUARE = "square"
    STAGGERED = "staggered"


class SuspensionType(str, Enum):
    """Suspension types for filtering fitments."""

    STOCK = "stock"
    LOWERED = "lowered"
    COILOVERS = "coilovers"
    AIR = "air"
    LIFTED = "lifted"

    @classmethod
    def from_string(cls, value: str | None) -> "SuspensionType | None":
        """Convert string to enum, handling common variations."""
        if not value:
            return None
        value_lower = value.lower()
        mappings = {
            "stock": cls.STOCK,
            "stock suspension": cls.STOCK,
            "lowered": cls.LOWERED,
            "lowering springs": cls.LOWERED,
            "coilovers": cls.COILOVERS,
            "coils": cls.COILOVERS,
            "air": cls.AIR,
            "air suspension": cls.AIR,
            "air ride": cls.AIR,
            "bagged": cls.AIR,
            "lifted": cls.LIFTED,
            "lift kit": cls.LIFTED,
            "leveling kit": cls.LIFTED,
        }
        return mappings.get(value_lower)


class DataSource(str, Enum):
    """Source of fitment data in responses."""

    EXACT = "exact"
    SIMILAR = "similar"
    LLM_KNOWLEDGE = "llm_knowledge"
    GREETING = "greeting"
    INVALID_VEHICLE = "invalid_vehicle"
    CLARIFICATION = "clarification"


# Offset thresholds for fitment style classification
AGGRESSIVE_OFFSET_THRESHOLD = 15
FLUSH_OFFSET_THRESHOLD = 25
TUCKED_OFFSET_THRESHOLD = 40
AGGRESSIVE_WIDTH_THRESHOLD = 9.0

# Poke threshold
POKE_OFFSET_THRESHOLD = 20
