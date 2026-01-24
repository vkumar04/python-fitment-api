from pydantic import BaseModel
from typing import Optional


class FitmentData(BaseModel):
    year: int
    make: str
    model: str
    wheel_brand: Optional[str] = None
    wheel_model: Optional[str] = None
    front_diameter: Optional[float] = None
    front_width: Optional[float] = None
    front_offset: Optional[float] = None
    rear_diameter: Optional[float] = None
    rear_width: Optional[float] = None
    rear_offset: Optional[float] = None
    tire_brand: Optional[str] = None
    tire_model: Optional[str] = None
    front_tire_width: Optional[float] = None
    front_tire_aspect: Optional[float] = None
    front_tire_diameter: Optional[float] = None
    rear_tire_width: Optional[float] = None
    rear_tire_aspect: Optional[float] = None
    rear_tire_diameter: Optional[float] = None
    rubbing: Optional[str] = None
    trimming: Optional[str] = None
    front_wheel_spacers: Optional[str] = None
    rear_wheel_spacers: Optional[str] = None
    front_backspacing: Optional[float] = None
    rear_backspacing: Optional[float] = None
    front_tire_overall_diameter: Optional[str] = None
    rear_tire_overall_diameter: Optional[str] = None
    suspension_type: Optional[str] = None


class FitmentQuery(BaseModel):
    query: str
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    limit: int = 5


class FitmentResponse(BaseModel):
    answer: str
    sources: list[FitmentData]
    confidence: float
