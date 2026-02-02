"""Centralized vehicle and fitment text parsing utilities.

This module is the single source of truth for extracting:
- Fitment style (flush/aggressive/track/tucked)
- Suspension type (stock/lowered/coilovers/air)
- Vehicle info detection (year, make, model, chassis codes)
"""

from typing import Any

# =============================================================================
# KEYWORD CONSTANTS (single source of truth)
# =============================================================================

# Style keywords mapped to normalized values
STYLE_KEYWORDS: dict[str, str] = {
    # Flush/Daily
    "flush": "flush",
    "daily": "flush",
    "conservative": "flush",
    "safe": "flush",
    # Aggressive/Stance
    "aggressive": "aggressive",
    "stance": "aggressive",
    "poke": "aggressive",
    "show": "aggressive",
    # Track/Performance
    "track": "track",
    "performance": "track",
    "grip": "track",
    # Tucked
    "tucked": "tucked",
    "tuck": "tucked",
}

# Suspension keywords mapped to normalized values
SUSPENSION_KEYWORDS: dict[str, str] = {
    # Stock
    "stock": "stock",
    "oem": "stock",
    "factory": "stock",
    # Lowered (springs)
    "lowered": "lowered",
    "springs": "lowered",
    "dropped": "lowered",
    # Coilovers
    "coilovers": "coilovers",
    "coils": "coilovers",
    "slammed": "coilovers",
    # Air/Bagged
    "air": "air",
    "bagged": "air",
    "bags": "air",
    # Lifted
    "lifted": "lifted",
    "leveled": "lifted",
}

# Common chassis codes for vehicle detection
CHASSIS_CODES: set[str] = {
    # BMW
    "e30", "e36", "e46", "e90", "e92", "f30", "f80", "g20", "g80",
    "e39", "e60", "f10", "g30",
    "e34", "e28", "e24",
    "e85", "e86", "z3", "z4",
    # Subaru
    "gc8", "gd", "gdb", "grb", "va", "vb",
    # Honda
    "eg", "ek", "dc2", "dc5", "ap1", "ap2", "fk8", "fl5",
    # Nissan
    "s13", "s14", "s15", "z32", "z33", "z34", "r32", "r33", "r34", "r35",
    # Toyota
    "ae86", "jza80", "a80", "a90", "zn6", "zn8",
    # Mazda
    "na", "nb", "nc", "nd", "fd", "fc",
    # VW
    "mk1", "mk2", "mk3", "mk4", "mk5", "mk6", "mk7", "mk8",
    # Mitsubishi
    "evo", "evo8", "evo9", "evo10", "evox",
    # Ford
    "s197", "s550", "sn95",
    # Lexus
    "is300", "is350", "gs300", "gs350",
}

# Common vehicle makes
MAKES: set[str] = {
    "acura", "alfa", "audi", "bmw", "buick", "cadillac", "chevrolet", "chevy",
    "chrysler", "dodge", "ferrari", "fiat", "ford", "genesis", "gmc", "honda",
    "hyundai", "infiniti", "jaguar", "jeep", "kia", "lamborghini", "lexus",
    "lincoln", "maserati", "mazda", "mclaren", "mercedes", "mini", "mitsubishi",
    "nissan", "porsche", "ram", "scion", "subaru", "suzuki", "tesla", "toyota",
    "volkswagen", "vw", "volvo",
}


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def extract_style(text: str) -> str | None:
    """Extract fitment style from text using word boundary matching.

    Args:
        text: User input text (e.g., "flush wheels for my GTI")

    Returns:
        Normalized style string (flush/aggressive/track/tucked) or None

    Examples:
        >>> extract_style("I want flush fitment")
        'flush'
        >>> extract_style("aggressive stance look")
        'aggressive'
        >>> extract_style("hello")
        None
    """
    text_lower = text.lower()
    for word in text_lower.split():
        # Remove punctuation from word
        word_clean = word.strip(".,!?")
        if word_clean in STYLE_KEYWORDS:
            return STYLE_KEYWORDS[word_clean]
    return None


def extract_suspension(text: str) -> str | None:
    """Extract suspension type from text using word boundary matching.

    Args:
        text: User input text (e.g., "on coilovers")

    Returns:
        Normalized suspension string (stock/lowered/coilovers/air/lifted) or None

    Examples:
        >>> extract_suspension("running coilovers")
        'coilovers'
        >>> extract_suspension("on bags")
        'air'
        >>> extract_suspension("hello")
        None
    """
    text_lower = text.lower()
    for word in text_lower.split():
        word_clean = word.strip(".,!?")
        if word_clean in SUSPENSION_KEYWORDS:
            return SUSPENSION_KEYWORDS[word_clean]
    return None


def has_vehicle_info(text: str) -> bool:
    """Check if text contains vehicle identifying information.

    Looks for:
    - 4-digit years (1980-2030)
    - Chassis codes (e30, s14, mk7, etc.)
    - Vehicle makes (bmw, honda, etc.)

    Args:
        text: User input text

    Returns:
        True if vehicle info detected, False otherwise
    """
    text_lower = text.lower()
    words = text_lower.split()

    for word in words:
        word_clean = word.strip(".,!?")

        # Check for year (4 digits between 1980-2030)
        if word_clean.isdigit() and len(word_clean) == 4:
            year = int(word_clean)
            if 1980 <= year <= 2030:
                return True

        # Check for chassis codes
        if word_clean in CHASSIS_CODES:
            return True

        # Check for makes
        if word_clean in MAKES:
            return True

    return False


def extract_all(text: str) -> dict[str, Any]:
    """Extract all fitment-related info from text.

    Convenience function that extracts style, suspension, and vehicle detection
    in one call.

    Args:
        text: User input text

    Returns:
        Dict with keys: style, suspension, has_vehicle
    """
    return {
        "style": extract_style(text),
        "suspension": extract_suspension(text),
        "has_vehicle": has_vehicle_info(text),
    }
