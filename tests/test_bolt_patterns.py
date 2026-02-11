#!/usr/bin/env python3
"""Test 50 vehicles with validated bolt patterns.

Uses the DSPy pipeline's spec resolution to verify bolt patterns
for known vehicles. These should all resolve from the DB seed data.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
)

# 50 vehicles with known correct bolt patterns
VEHICLES = [
    # Japanese - Honda/Acura
    ("Honda", 2020, "Civic Si", "5x114.3"),
    ("Honda", 2022, "Accord", "5x114.3"),
    ("Honda", 1999, "Civic", "4x100"),
    ("Acura", 2021, "TLX", "5x114.3"),
    ("Acura", 2019, "NSX", "5x120"),
    # Japanese - Toyota/Lexus
    ("Toyota", 2022, "GR86", "5x100"),
    ("Toyota", 2020, "Supra", "5x112"),
    ("Toyota", 2021, "Camry", "5x114.3"),
    ("Toyota", 2022, "GR Corolla", "5x114.3"),
    ("Lexus", 2021, "IS350", "5x114.3"),
    # Japanese - Nissan/Infiniti
    ("Nissan", 2020, "370Z", "5x114.3"),
    ("Nissan", 2023, "Z", "5x114.3"),
    ("Nissan", 2019, "GT-R", "5x114.3"),
    ("Infiniti", 2020, "Q60", "5x114.3"),
    # Japanese - Subaru
    ("Subaru", 2022, "WRX", "5x114.3"),
    ("Subaru", 2021, "WRX STI", "5x114.3"),
    ("Subaru", 2014, "BRZ", "5x100"),
    ("Subaru", 2012, "WRX", "5x100"),
    # Japanese - Mazda
    ("Mazda", 1990, "Miata", "4x100"),
    ("Mazda", 2019, "MX-5", "4x100"),
    ("Mazda", 2021, "Mazda3", "5x114.3"),
    # Japanese - Mitsubishi
    ("Mitsubishi", 2015, "Lancer Evolution", "5x114.3"),
    # German - BMW
    ("BMW", 2023, "M4", "5x112"),
    ("BMW", 2018, "M4", "5x120"),
    ("BMW", 2021, "M3", "5x112"),
    ("BMW", 2017, "M3", "5x120"),
    ("BMW", 1989, "M3", "5x120"),  # E30 M3 uses 5x120 (NOT 4x100 like base E30)
    ("BMW", 1984, "M6", "5x120"),
    ("BMW", 2020, "330i", "5x112"),
    ("BMW", 2017, "340i", "5x120"),
    # German - Mercedes
    ("Mercedes-Benz", 2021, "C63 AMG", "5x112"),
    ("Mercedes-Benz", 2020, "E350", "5x112"),
    # German - Audi
    ("Audi", 2021, "RS5", "5x112"),
    ("Audi", 2020, "S4", "5x112"),
    # German - VW/Porsche
    ("Volkswagen", 2021, "Golf R", "5x112"),
    ("Volkswagen", 2019, "GTI", "5x112"),
    ("Porsche", 2021, "911", "5x130"),
    ("Porsche", 2020, "Cayman", "5x130"),
    # American - Ford
    ("Ford", 2020, "Mustang GT", "5x114.3"),
    ("Ford", 2022, "F-150", "6x135"),
    ("Ford", 2021, "Focus RS", "5x108"),
    # American - Chevy/Dodge
    ("Chevrolet", 2021, "Camaro SS", "5x120"),
    ("Chevrolet", 2022, "Corvette C8", "5x120"),
    ("Chevrolet", 2021, "Silverado", "6x139.7"),
    ("Dodge", 2021, "Challenger", "5x115"),
    ("Dodge", 2020, "Charger", "5x115"),
    # Electric
    ("Tesla", 2021, "Model 3", "5x114.3"),
    ("Tesla", 2021, "Model S", "5x120"),
    ("Tesla", 2022, "Model Y", "5x114.3"),
]


def test_all_bolt_patterns():
    """Test that all 50 vehicles resolve correct bolt patterns via the pipeline."""
    from src.services.dspy_v2 import create_pipeline

    pipeline = create_pipeline(model="openai/gpt-4o-mini")
    failures = []

    for make, year, model, expected in VEHICLES:
        result = pipeline.retrieve(f"{year} {make} {model}")
        bolt_pattern = (
            result.specs.get("bolt_pattern", "Unknown") if result.specs else "Unknown"
        )
        if bolt_pattern.upper() != expected.upper():
            failures.append(
                f"{year} {make} {model}: got {bolt_pattern}, expected {expected}"
            )

    if failures:
        pytest.fail(
            f"{len(failures)}/{len(VEHICLES)} bolt pattern mismatches:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )


def main():
    """Run bolt pattern test standalone (outside pytest)."""
    from src.services.dspy_v2 import create_pipeline

    pipeline = create_pipeline(model="openai/gpt-4o-mini")
    passed = 0
    failed = 0
    failures = []

    print("Testing 50 vehicles...")
    print("=" * 70)

    for make, year, model, expected in VEHICLES:
        result = pipeline.retrieve(f"{year} {make} {model}")
        bolt_pattern = (
            result.specs.get("bolt_pattern", "Unknown") if result.specs else "Unknown"
        )
        match = bolt_pattern.upper() == expected.upper()

        if match:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
            failures.append((make, year, model, expected, bolt_pattern))

        print(f"{status} {year} {make} {model}: {bolt_pattern} (expected: {expected})")

    print("=" * 70)
    print(f"Results: {passed}/{len(VEHICLES)} passed, {failed} failed")

    if failures:
        print("\nFailures:")
        for make, year, model, expected, got in failures:
            print(f"  - {year} {make} {model}: got {got}, expected {expected}")


if __name__ == "__main__":
    main()
