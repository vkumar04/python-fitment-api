from typing import Optional

from pydantic import BaseModel


class KanseiWheel(BaseModel):
    id: int
    model: str
    finish: str = ""
    sku: str = ""
    diameter: float
    width: float
    bolt_pattern: str
    wheel_offset: int
    category: str = ""
    url: str = ""
    in_stock: bool = True
    center_bore: float = 73.1  # mm — varies by product line (73.1 street, 106.1 truck)
    weight: Optional[float] = None
