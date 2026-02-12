"""Async client for the NHTSA vPIC API.

No authentication required. All endpoints return JSON with ?format=json.
"""

import httpx

from app.config import get_settings


class NHTSAClient:
    """Async client for the NHTSA vPIC API."""

    def __init__(self) -> None:
        self.base_url = get_settings().nhtsa_base_url
        self.client = httpx.AsyncClient(timeout=15.0)

    async def decode_vin(self, vin: str) -> dict:
        """Decode a VIN and return vehicle details."""
        url = f"{self.base_url}/vehicles/DecodeVinValues/{vin}?format=json"
        resp = await self.client.get(url)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("Results", [{}])[0]
        return {
            "year": results.get("ModelYear"),
            "make": results.get("Make"),
            "model": results.get("Model"),
            "trim": results.get("Trim"),
            "drive_type": results.get("DriveType"),
            "body_class": results.get("BodyClass"),
            "wheel_size_front": results.get("WheelSizeFront"),
            "wheel_size_rear": results.get("WheelSizeRear"),
            "gvwr": results.get("GVWR"),
        }

    async def get_all_makes(self) -> list[dict]:
        """Get all vehicle makes."""
        url = f"{self.base_url}/vehicles/GetAllMakes?format=json"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json().get("Results", [])

    async def get_models_for_make_year(self, make: str, year: int) -> list[dict]:
        """Get models for a specific make and year."""
        url = (
            f"{self.base_url}/vehicles/GetModelsForMakeYear"
            f"/make/{make}/modelyear/{year}?format=json"
        )
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json().get("Results", [])

    async def close(self) -> None:
        await self.client.aclose()


# Singleton
nhtsa_client = NHTSAClient()
