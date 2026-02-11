#!/usr/bin/env python3
"""End-to-end pipeline tests covering spec resolution and fitment retrieval.

Tests:
1. E30 M3 — 5x120, classic car, should get Kansei wheels + recommendations
2. E36 M3 — 5x120, 90s sports car, should get Kansei wheels
3. 2020 Honda Civic — 5x114.3, modern car, should get Kansei wheels
4. Fitment styles: flush, aggressive, square setups
5. No early_response (Vehicle Not Found) on any valid query

Usage:
    OPENAI_API_KEY=... uv run python tests/test_pipeline_e2e.py
"""

import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_vehicle(query: str, expected_bolt: str, expected_make: str):
    """Test a vehicle query through the full pipeline."""
    from src.services.dspy_v2 import create_pipeline

    pipeline = create_pipeline(model="openai/gpt-4o-mini")
    result = pipeline.retrieve(query)

    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print(f"{'='*70}")

    # Check parsed info
    parsed = result.parsed
    print(f"  Parsed: make={parsed.get('make')}, model={parsed.get('model')}, "
          f"chassis={parsed.get('chassis_code')}, year={parsed.get('year')}, "
          f"style={parsed.get('fitment_style')}, suspension={parsed.get('suspension')}")

    # Check for early response (error)
    if result.early_response:
        print(f"  EARLY RESPONSE: {result.early_response}")
        return False, f"Got early_response: {result.early_response}"

    # Check specs
    specs = result.specs
    if not specs:
        print("  FAIL: No specs returned")
        return False, "No specs returned"

    bolt = specs.get("bolt_pattern", "?")
    print(f"  Specs: bolt={bolt}, center_bore={specs.get('center_bore')}, "
          f"diameter={specs.get('min_diameter')}-{specs.get('max_diameter')}, "
          f"width={specs.get('min_width')}-{specs.get('max_width')}, "
          f"offset={specs.get('min_offset')}-{specs.get('max_offset')}")

    if bolt != expected_bolt:
        print(f"  FAIL: Expected bolt pattern {expected_bolt}, got {bolt}")
        return False, f"Wrong bolt pattern: {bolt} != {expected_bolt}"

    if parsed.get("make") != expected_make:
        print(f"  FAIL: Expected make {expected_make}, got {parsed.get('make')}")
        return False, f"Wrong make: {parsed.get('make')} != {expected_make}"

    # Check Kansei wheels
    kansei = result.kansei_wheels
    print(f"  Kansei wheels: {len(kansei)} found")
    if kansei:
        for w in kansei[:3]:
            calc = w.get("fitment_calc", {})
            print(f"    - {w.get('model')} {int(w.get('diameter',0))}x{w.get('width')} "
                  f"+{w.get('offset')} ({calc.get('style', '?')}, "
                  f"poke={calc.get('poke_mm', '?')}mm, "
                  f"verdict={calc.get('verdict', '?')}, "
                  f"confidence={calc.get('confidence', '?')})")

    # Check community fitments
    community = result.community_fitments
    print(f"  Community fitments: {len(community)} found")
    if community:
        for f in community[:3]:
            print(f"    - {f.get('year')} {f.get('make')} {f.get('model')}: "
                  f"{f.get('front_diameter')}x{f.get('front_width')} +{f.get('front_offset')} "
                  f"({f.get('fitment_style', '?')})")

    # Check recommended setups
    if result.recommended_setups_str:
        print(f"  Recommendations preview: {result.recommended_setups_str[:200]}...")
    else:
        print("  Recommendations: (none)")

    # Check vehicle summary
    print(f"  Vehicle summary: {result.vehicle_summary}")
    print(f"  Specs summary: {result.specs_summary[:200]}...")

    # Validate we got actual fitment data
    has_data = len(kansei) > 0 or len(community) > 0
    if not has_data:
        print("  WARNING: No fitment data at all (no Kansei wheels, no community fitments)")
        return False, "No fitment data returned"

    # OEM accuracy assertions for known vehicles (from verified hardcoded registry)
    base_query = query.lower().split("flush")[0].split("aggressive")[0].split("on ")[0].strip()

    if "e30" in base_query and "m3" in base_query:
        oem_w = specs.get("oem_width")
        oem_o = specs.get("oem_offset")
        if oem_w != 7.0:
            print(f"  FAIL: E30 M3 oem_width should be 7.0, got {oem_w}")
            return False, f"E30 M3 wrong oem_width: {oem_w} != 7.0"
        if oem_o != 25:
            print(f"  FAIL: E30 M3 oem_offset should be 25, got {oem_o}")
            return False, f"E30 M3 wrong oem_offset: {oem_o} != 25"
        if specs.get("is_staggered_stock"):
            print("  FAIL: E30 M3 should NOT be staggered")
            return False, "E30 M3 incorrectly marked as staggered"
        print(f"  E30 M3 OEM checks: width={oem_w}, offset={oem_o}, staggered=False ✓")

    elif "e36" in base_query and "m3" in base_query:
        oem_w = specs.get("oem_width")
        oem_o = specs.get("oem_offset")
        if oem_w != 7.5:
            print(f"  FAIL: E36 M3 oem_width should be 7.5, got {oem_w}")
            return False, f"E36 M3 wrong oem_width: {oem_w} != 7.5"
        if oem_o != 41:
            print(f"  FAIL: E36 M3 oem_offset should be 41, got {oem_o}")
            return False, f"E36 M3 wrong oem_offset: {oem_o} != 41"
        if specs.get("is_staggered_stock"):
            print("  FAIL: E36 M3 should NOT be staggered")
            return False, "E36 M3 incorrectly marked as staggered"
        print(f"  E36 M3 OEM checks: width={oem_w}, offset={oem_o}, staggered=False ✓")

    elif "civic" in base_query and "2020" in base_query:
        oem_w = specs.get("oem_width")
        oem_o = specs.get("oem_offset")
        if oem_w is not None and oem_w != 7.0:
            print(f"  FAIL: 2020 Civic oem_width should be 7.0, got {oem_w}")
            return False, f"2020 Civic wrong oem_width: {oem_w} != 7.0"
        if oem_o is not None and oem_o != 45:
            print(f"  FAIL: 2020 Civic oem_offset should be 45, got {oem_o}")
            return False, f"2020 Civic wrong oem_offset: {oem_o} != 45"
        print(f"  2020 Civic OEM checks: width={oem_w}, offset={oem_o} ✓")

    # E39 M5 specific checks: brake clearance + staggered detection
    if "E39" in query and "M5" in query and not any(
        s in query.lower() for s in ("flush", "aggressive", "coil", "lower")
    ):
        brake_min = specs.get("min_brake_clearance_diameter")
        if brake_min is None or brake_min < 17:
            print(f"  FAIL: E39 M5 should have brake clearance >= 17\", got {brake_min}")
            return False, f"E39 M5 missing brake clearance: {brake_min}"

        is_staggered = specs.get("is_staggered_stock")
        if not is_staggered:
            print("  FAIL: E39 M5 should be detected as staggered stock")
            return False, "E39 M5 not detected as staggered"

        # No 17" wheels should be recommended
        for w in kansei:
            if int(w.get("diameter", 0)) < 18:
                print(f"  FAIL: E39 M5 got sub-18\" wheel: {w.get('diameter')}\"")
                return False, f"E39 M5 got {w.get('diameter')}\" wheel (below brake clearance)"

        oem_w = specs.get("oem_width")
        if oem_w is None:
            print("  FAIL: E39 M5 should have oem_width from verified registry")
            return False, "E39 M5 oem_width is None"
        if oem_w != 8.0:
            print(f"  FAIL: E39 M5 oem_width should be 8.0, got {oem_w}")
            return False, f"E39 M5 wrong oem_width: {oem_w} != 8.0"

        oem_rw = specs.get("oem_rear_width")
        if oem_rw != 9.5:
            print(f"  FAIL: E39 M5 oem_rear_width should be 9.5, got {oem_rw}")
            return False, f"E39 M5 wrong oem_rear_width: {oem_rw} != 9.5"

        print(f"  E39 M5 checks: brake_min={brake_min}, staggered={is_staggered}, "
              f"oem_width={oem_w}, oem_rear_width={oem_rw}")

    print("  PASS")
    return True, None


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set, skipping")
        sys.exit(0)

    tests = [
        # (query, expected_bolt_pattern, expected_make)
        # Basic vehicle tests
        ("E30 M3", "5x120", "BMW"),
        ("E36 M3", "5x120", "BMW"),
        ("2020 Honda Civic", "5x114.3", "Honda"),

        # Big brakes / staggered stock (E39 M5)
        ("E39 M5", "5x120", "BMW"),

        # Fitment style tests (square, flush, aggressive)
        ("E30 M3 flush fitment", "5x120", "BMW"),
        ("E30 M3 aggressive stance", "5x120", "BMW"),
        ("2020 Honda Civic flush", "5x114.3", "Honda"),
        ("2020 Honda Civic aggressive", "5x114.3", "Honda"),

        # Suspension type tests
        ("E30 M3 on coilovers", "5x120", "BMW"),
        ("2020 Honda Civic lowered", "5x114.3", "Honda"),
    ]

    passed = 0
    failed = 0
    failures = []

    for query, expected_bolt, expected_make in tests:
        try:
            ok, reason = test_vehicle(query, expected_bolt, expected_make)
            if ok:
                passed += 1
            else:
                failed += 1
                failures.append((query, reason))
        except Exception as e:
            failed += 1
            failures.append((query, str(e)))
            print(f"\n  EXCEPTION: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*70}")
    print(f"Results: {passed}/{passed + failed} passed, {failed} failed")
    if failures:
        print("\nFailures:")
        for query, reason in failures:
            print(f"  - {query}: {reason}")
    print(f"{'='*70}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
