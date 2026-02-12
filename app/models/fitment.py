from typing import Optional

from pydantic import BaseModel

from app.models.wheel import KanseiWheel


class TireRecommendation(BaseModel):
    size: str  # e.g. "225/40R18"
    width_mm: int
    aspect_ratio: int
    sidewall_mm: float
    overall_diameter_mm: float
    oem_diameter_diff_pct: float
    width_description: str  # e.g. "slightly stretched", "ideal match"


class PokeCalculation(BaseModel):
    poke_mm: float
    description: str  # e.g. "+5mm (mild poke — usually fine on stock)"
    stance_label: str  # "deep tuck", "moderate tuck", "mild tuck", "flush", "mild poke", "moderate poke", "aggressive"


class FitmentResult(BaseModel):
    wheel: KanseiWheel
    fitment_score: float  # 0.0 - 1.0 compatibility score
    offset_delta: int  # mm difference from OEM
    diameter_delta: float  # inch difference from OEM
    notes: list[str]  # Fitment warnings/tips
    tire_recommendation: Optional[TireRecommendation] = None
    poke: Optional[PokeCalculation] = None
    setup_type: str = "square"  # "square" or "staggered"
    position: str = "both"  # "front", "rear", or "both"
    brake_clearance_ok: bool = True
    brake_clearance_note: Optional[str] = None
    mods_needed: list[str] = []
    confidence: str = "medium"  # "high", "medium", "low"
    confidence_reason: str = ""


class FitmentResponse(BaseModel):
    vehicle_year: int
    vehicle_make: str
    vehicle_model: str
    vehicle_trim: Optional[str] = None
    bolt_pattern: str
    chassis_code: Optional[str] = None
    hub_bore_mm: Optional[float] = None
    hub_ring_status: Optional[str] = None
    suspension_type: str = "stock"
    is_staggered_stock: bool = False
    recommendations: list[FitmentResult]
    total_options: int
    ai_summary: str  # DSPy-generated natural language summary
