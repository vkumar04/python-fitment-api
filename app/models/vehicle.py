from typing import Optional

from pydantic import BaseModel, model_validator


class VehicleIdentification(BaseModel):
    year: Optional[int] = None
    make: str
    model: str
    trim: Optional[str] = None
    vin: Optional[str] = None


class VehicleSpecs(BaseModel):
    """OEM wheel and chassis specifications for a vehicle."""

    year: int
    make: str
    model: str
    trim: Optional[str] = None
    chassis_code: Optional[str] = None

    bolt_pattern: str
    hub_bore: Optional[float] = None

    # Front/rear split (canonical for staggered setups)
    oem_diameter_front: Optional[float] = None
    oem_diameter_rear: Optional[float] = None
    oem_width_front: Optional[float] = None
    oem_width_rear: Optional[float] = None
    oem_offset_front: Optional[int] = None
    oem_offset_rear: Optional[int] = None

    # Tire specs (OEM)
    oem_tire_front: Optional[str] = None
    oem_tire_rear: Optional[str] = None

    # Brake info
    front_brake_size: Optional[str] = None
    has_bbk: bool = False
    min_wheel_diameter: Optional[float] = None

    # Chassis info
    drive_type: Optional[str] = None
    body_class: Optional[str] = None
    is_staggered_stock: bool = False
    is_performance_trim: bool = False
    suspension_type: str = "stock"

    @model_validator(mode="before")
    @classmethod
    def populate_front_from_legacy(cls, data: dict) -> dict:  # type: ignore[override]
        """Accept legacy oem_diameter/width/offset and store as front fields."""
        if isinstance(data, dict):
            for legacy, front in [
                ("oem_diameter", "oem_diameter_front"),
                ("oem_width", "oem_width_front"),
                ("oem_offset", "oem_offset_front"),
            ]:
                if data.get(legacy) is not None and data.get(front) is None:
                    data[front] = data[legacy]
                # Remove legacy key so it doesn't cause validation errors
                data.pop(legacy, None)
        return data

    @property
    def oem_diameter(self) -> Optional[float]:
        return self.oem_diameter_front

    @property
    def oem_width(self) -> Optional[float]:
        return self.oem_width_front

    @property
    def oem_offset(self) -> Optional[int]:
        return self.oem_offset_front
