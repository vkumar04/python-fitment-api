import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openai import OpenAI

from ..db import fitments as db
from .wheel_size_lookup import OEMSpecs, get_wheel_size_lookup


class StanceType(str, Enum):
    STOCK = "stock"
    FLUSH = "flush"
    AGGRESSIVE = "aggressive"
    TUCKED = "tucked"


class SuspensionMod(str, Enum):
    STOCK = "stock"
    LOWERING_SPRINGS = "lowering_springs"
    COILOVERS = "coilovers"
    AIR_SUSPENSION = "air_suspension"


@dataclass
class VehicleConfig:
    year: int
    make: str
    model: str
    stance: StanceType = StanceType.STOCK
    suspension: SuspensionMod = SuspensionMod.STOCK
    fenders_rolled: bool = False
    fenders_pulled: bool = False
    wheel_spacers_ok: bool = True
    max_spacer_size: int = 20  # mm
    rubbing_acceptable: bool = False
    trimming_acceptable: bool = False


@dataclass
class WheelMatch:
    wheel: dict[str, Any]
    compatibility_score: float
    notes: list[str]
    requires_spacers: bool = False
    spacer_size_front: int = 0
    spacer_size_rear: int = 0
    may_rub: bool = False
    requires_trimming: bool = False


class WheelMatcher:
    # Offset adjustments based on stance goals
    STANCE_OFFSET_RANGES = {
        StanceType.STOCK: (30, 50),  # Higher offset, tucked
        StanceType.TUCKED: (35, 55),  # Even higher offset
        StanceType.FLUSH: (20, 38),  # Moderate offset
        StanceType.AGGRESSIVE: (-10, 25),  # Low offset, poke
    }

    # Additional offset allowance for modifications
    MOD_OFFSET_BONUS = {
        "fenders_rolled": 5,
        "fenders_pulled": 10,
        "coilovers": 3,
        "air_suspension": 5,
    }

    # Common bolt patterns by make
    BOLT_PATTERNS = {
        "Honda": ["5X114.3"],
        "Acura": ["5X114.3"],
        "Toyota": ["5X114.3", "5X100"],
        "Lexus": ["5X114.3"],
        "Subaru": ["5X100", "5X114.3"],
        "Mazda": ["5X114.3"],
        "BMW": ["5X120", "5X112"],
        "Mercedes": ["5X112"],
        "Audi": ["5X112"],
        "Volkswagen": ["5X112", "5X100"],
        "Ford": ["5X114.3", "5X108"],
        "Chevrolet": ["5X120", "6X139.7"],
        "Nissan": ["5X114.3"],
        "Hyundai": ["5X114.3"],
        "Kia": ["5X114.3"],
        "Genesis": ["5X114.3"],
        "Tesla": ["5X114.3", "5X120"],
        "Cadillac": ["5X120"],
        "Dodge": ["5X115"],
    }

    def __init__(self, kansei_data_path: str = "datafiles/kansei_wheels.json") -> None:
        self.kansei_wheels = self._load_kansei_wheels(kansei_data_path)
        self.wheel_size_lookup = get_wheel_size_lookup()

    def _load_kansei_wheels(self, path: str) -> list[dict[str, Any]]:
        """Load Kansei wheel data from JSON."""
        try:
            with open(path) as f:
                return json.load(f)  # type: ignore[no-any-return]
        except FileNotFoundError:
            print(f"Warning: Kansei data not found at {path}")
            return []

    def get_vehicle_fitments(
        self, config: VehicleConfig, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get existing fitments for a vehicle from the RAG database."""
        query = f"{config.year} {config.make} {config.model} wheel fitment"

        # Map stance to fitment style for filtering
        style_map = {
            StanceType.STOCK: None,
            StanceType.TUCKED: "tucked",
            StanceType.FLUSH: "flush",
            StanceType.AGGRESSIVE: "aggressive",
        }

        results = db.search(
            query=query,
            year=config.year,
            make=config.make,
            model=config.model,
            fitment_style=style_map.get(config.stance),
            limit=limit,
        )

        return results

    def _get_oem_specs(self, config: VehicleConfig) -> OEMSpecs | None:
        """Get OEM specs from wheel-size.com lookup."""
        try:
            return self.wheel_size_lookup.lookup(config.year, config.make, config.model)
        except Exception:
            return None

    def _get_bolt_patterns_for_vehicle(
        self, make: str, oem_specs: OEMSpecs | None = None
    ) -> list[str]:
        """Get likely bolt patterns for a vehicle make."""
        # Use OEM specs if available
        if oem_specs and oem_specs.bolt_pattern:
            return [oem_specs.bolt_pattern.upper().replace("X", "X")]
        return self.BOLT_PATTERNS.get(make, ["5X114.3"])

    def _calculate_offset_range(
        self,
        config: VehicleConfig,
        base_fitments: list[dict[str, Any]],
        oem_specs: OEMSpecs | None = None,
    ) -> tuple[int, int]:
        """Calculate acceptable offset range based on config, fitments, and OEM specs."""
        # Start with stance-based range
        min_offset, max_offset = self.STANCE_OFFSET_RANGES[config.stance]

        # Use OEM specs as baseline if available and no fitment data
        if oem_specs and not base_fitments:
            oem_center = (oem_specs.oem_offset_min + oem_specs.oem_offset_max) // 2
            # Adjust stance range based on OEM center
            if config.stance == StanceType.STOCK:
                min_offset = oem_specs.oem_offset_min - 5
                max_offset = oem_specs.oem_offset_max + 5
            elif config.stance == StanceType.FLUSH:
                # Flush is typically 5-15mm lower offset than OEM
                min_offset = oem_specs.oem_offset_min - 15
                max_offset = oem_center
            elif config.stance == StanceType.AGGRESSIVE:
                # Aggressive is 15-30mm lower than OEM
                min_offset = oem_specs.oem_offset_min - 30
                max_offset = oem_specs.oem_offset_min - 5
            elif config.stance == StanceType.TUCKED:
                min_offset = oem_center
                max_offset = oem_specs.oem_offset_max + 10

        # If we have existing fitments, use them to refine
        if base_fitments:
            fitment_offsets = []
            for f in base_fitments:
                meta = f.get("metadata", {})
                front_offset = meta.get("front_offset", 0)
                rear_offset = meta.get("rear_offset", 0)
                if front_offset:
                    fitment_offsets.append(front_offset)
                if rear_offset:
                    fitment_offsets.append(rear_offset)

            if fitment_offsets:
                # Adjust range based on actual fitments
                min_offset = min(min_offset, min(fitment_offsets) - 5)
                max_offset = max(max_offset, max(fitment_offsets) + 5)

        # Apply modification bonuses (allow lower offsets)
        if config.fenders_rolled:
            min_offset -= self.MOD_OFFSET_BONUS["fenders_rolled"]
        if config.fenders_pulled:
            min_offset -= self.MOD_OFFSET_BONUS["fenders_pulled"]
        if config.suspension == SuspensionMod.COILOVERS:
            min_offset -= self.MOD_OFFSET_BONUS["coilovers"]
        if config.suspension == SuspensionMod.AIR_SUSPENSION:
            min_offset -= self.MOD_OFFSET_BONUS["air_suspension"]

        return int(min_offset), int(max_offset)

    def _calculate_size_range(
        self,
        config: VehicleConfig,
        base_fitments: list[dict[str, Any]],
        oem_specs: OEMSpecs | None = None,
    ) -> dict[str, float]:
        """Calculate acceptable wheel size ranges."""
        sizes: dict[str, float] = {
            "diameter_min": 17,
            "diameter_max": 20,
            "width_min": 8.0,
            "width_max": 10.5,
        }

        # Use OEM specs as baseline if available
        if oem_specs and oem_specs.oem_wheel_sizes:
            oem_diameters = []
            oem_widths = []
            for ws in oem_specs.oem_wheel_sizes:
                # Parse "18x8" format
                parts = ws.lower().split("x")
                if len(parts) == 2:
                    try:
                        oem_diameters.append(float(parts[0]))
                        oem_widths.append(float(parts[1]))
                    except ValueError:
                        pass
            if oem_diameters:
                sizes["diameter_min"] = min(oem_diameters) - 1
                sizes["diameter_max"] = max(oem_diameters) + 2
            if oem_widths:
                sizes["width_min"] = min(oem_widths) - 0.5
                sizes["width_max"] = max(oem_widths) + 2.0

        if base_fitments:
            diameters = []
            widths = []
            for f in base_fitments:
                meta = f.get("metadata", {})
                if meta.get("front_diameter"):
                    diameters.append(meta["front_diameter"])
                if meta.get("front_width"):
                    widths.append(meta["front_width"])

            if diameters:
                sizes["diameter_min"] = min(sizes["diameter_min"], min(diameters) - 1)
                sizes["diameter_max"] = max(sizes["diameter_max"], max(diameters) + 1)
            if widths:
                sizes["width_min"] = min(sizes["width_min"], min(widths) - 0.5)
                sizes["width_max"] = max(sizes["width_max"], max(widths) + 1.0)

        return sizes

    def find_matching_wheels(self, config: VehicleConfig) -> list[WheelMatch]:
        """Find Kansei wheels that match the vehicle configuration."""
        matches = []

        # Get existing fitments for reference
        base_fitments = self.get_vehicle_fitments(config)

        # If no fitments in DB, try OEM lookup from wheel-size.com
        oem_specs: OEMSpecs | None = None
        if not base_fitments:
            oem_specs = self._get_oem_specs(config)

        # Determine acceptable parameters
        bolt_patterns = self._get_bolt_patterns_for_vehicle(config.make, oem_specs)
        offset_range = self._calculate_offset_range(config, base_fitments, oem_specs)
        size_range = self._calculate_size_range(config, base_fitments, oem_specs)

        min_offset, max_offset = offset_range

        for wheel in self.kansei_wheels:
            if not wheel.get("in_stock", True):
                continue

            # Check bolt pattern
            wheel_bp = wheel.get("bolt_pattern", "")
            if wheel_bp and wheel_bp not in bolt_patterns:
                continue

            # Check diameter
            diameter = wheel.get("diameter", 0)
            if not (
                size_range["diameter_min"] <= diameter <= size_range["diameter_max"]
            ):
                continue

            # Check width
            width = wheel.get("width", 0)
            if not (size_range["width_min"] <= width <= size_range["width_max"]):
                continue

            # Check offset
            offset = wheel.get("offset", 0)
            notes = []
            requires_spacers = False
            spacer_size = 0
            may_rub = False
            requires_trimming = False

            if offset < min_offset:
                # Too aggressive, may poke
                if config.wheel_spacers_ok:
                    # Could work with higher offset wheel + spacers for flush
                    continue  # Skip, wheel is too aggressive
                else:
                    continue
            elif offset > max_offset:
                # Too tucked, might need spacers to bring it out
                if config.wheel_spacers_ok:
                    spacer_needed = offset - max_offset
                    if spacer_needed <= config.max_spacer_size:
                        requires_spacers = True
                        spacer_size = int(spacer_needed)
                        notes.append(
                            f"Recommend {spacer_size}mm spacers for {config.stance.value} fitment"
                        )
                    else:
                        continue  # Would need too much spacer
                else:
                    continue

            # Calculate compatibility score
            score = 1.0

            # Penalize if spacers needed
            if requires_spacers:
                score -= 0.1 * (spacer_size / 10)

            # Bonus for offset in the sweet spot for stance
            target_offset = (min_offset + max_offset) / 2
            offset_diff = abs(offset - target_offset)
            score -= offset_diff * 0.01

            # Bonus for matching existing fitment patterns
            if base_fitments:
                for f in base_fitments:
                    meta = f.get("metadata", {})
                    if (
                        meta.get("front_diameter") == diameter
                        and abs(meta.get("front_offset", 0) - offset) <= 5
                    ):
                        score += 0.2
                        notes.append("Similar to verified fitment")
                        break

            # Check for potential rubbing based on aggressive specs
            if offset < 20 and width >= 9.5:
                if not config.fenders_rolled and not config.fenders_pulled:
                    may_rub = True
                    notes.append("May rub without fender work")
                    if not config.rubbing_acceptable:
                        score -= 0.3

            # Width considerations
            if width >= 10.5 and not config.fenders_rolled:
                notes.append("Wide wheel - check fender clearance")
                may_rub = True

            score = max(0.1, min(1.0, score))

            matches.append(
                WheelMatch(
                    wheel=wheel,
                    compatibility_score=score,
                    notes=notes,
                    requires_spacers=requires_spacers,
                    spacer_size_front=spacer_size,
                    spacer_size_rear=spacer_size,
                    may_rub=may_rub,
                    requires_trimming=requires_trimming,
                )
            )

        # Sort by compatibility score
        matches.sort(key=lambda m: m.compatibility_score, reverse=True)

        return matches

    def get_recommendation(
        self, config: VehicleConfig, limit: int = 10
    ) -> dict[str, Any]:
        """Get wheel recommendations with AI explanation."""
        matches = self.find_matching_wheels(config)[:limit]

        if not matches:
            return {
                "matches": [],
                "explanation": "No matching Kansei wheels found for your configuration. Try adjusting your stance preference or enabling spacers.",
                "vehicle_fitments": [],
            }

        # Get existing fitments for context
        base_fitments = self.get_vehicle_fitments(config, limit=5)

        # Format matches for display
        formatted_matches = []
        for m in matches:
            formatted_matches.append(
                {
                    "model": m.wheel["model"],
                    "finish": m.wheel["finish"],
                    "size": f"{m.wheel['diameter']}x{m.wheel['width']}",
                    "offset": m.wheel["offset"],
                    "bolt_pattern": m.wheel["bolt_pattern"],
                    "price": m.wheel["price"],
                    "sku": m.wheel["sku"],
                    "url": m.wheel["url"],
                    "score": round(m.compatibility_score, 2),
                    "notes": m.notes,
                    "requires_spacers": m.requires_spacers,
                    "spacer_size": m.spacer_size_front,
                    "may_rub": m.may_rub,
                }
            )

        # Build context for AI explanation
        context = f"""
Vehicle: {config.year} {config.make} {config.model}
Desired stance: {config.stance.value}
Suspension: {config.suspension.value}
Fenders rolled: {config.fenders_rolled}
Fenders pulled: {config.fenders_pulled}
Spacers OK: {config.wheel_spacers_ok} (max {config.max_spacer_size}mm)

Top matching Kansei wheels:
"""
        for i, m in enumerate(formatted_matches[:5], 1):
            context += f"\n{i}. {m['model']} {m['finish']} - {m['size']} ET{m['offset']} ({m['bolt_pattern']}) - ${m['price']}"
            if m["notes"]:
                context += f"\n   Notes: {', '.join(m['notes'])}"

        if base_fitments:
            context += "\n\nExisting verified fitments for reference:"
            for f in base_fitments[:3]:
                context += f"\n- {f.get('document', '')[:200]}"

        # Get AI explanation
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=500,
                messages=[
                    {
                        "role": "system",
                        "content": """You are a wheel fitment expert. Explain the wheel recommendations briefly and clearly.
Focus on: why these wheels fit, any concerns, and which option is best for their goals.
Be concise but helpful. Mention spacers or fender work if needed.""",
                    },
                    {
                        "role": "user",
                        "content": f"Explain these wheel recommendations:\n\n{context}",
                    },
                ],
            )
            explanation = ""
            if response.choices and response.choices[0].message.content:
                explanation = response.choices[0].message.content
        except Exception:
            explanation = "Unable to generate AI explanation."

        # Get OEM specs for response
        oem_specs = self._get_oem_specs(config) if not base_fitments else None

        # Build OEM info dict if available
        oem_info = None
        if oem_specs:
            oem_info = {
                "bolt_pattern": oem_specs.bolt_pattern,
                "center_bore": oem_specs.center_bore,
                "oem_offset_range": f"{oem_specs.oem_offset_min}-{oem_specs.oem_offset_max}",
                "oem_wheel_sizes": oem_specs.oem_wheel_sizes,
                "oem_tire_sizes": oem_specs.oem_tire_sizes,
                "source": "wheel-size.com",
            }

        return {
            "matches": formatted_matches,
            "explanation": explanation,
            "vehicle_fitments": [f.get("document", "") for f in base_fitments[:3]],
            "offset_range": self._calculate_offset_range(
                config, base_fitments, oem_specs
            ),
            "bolt_patterns": self._get_bolt_patterns_for_vehicle(
                config.make, oem_specs
            ),
            "oem_specs": oem_info,
            "data_source": "community_fitments" if base_fitments else "oem_lookup",
        }
