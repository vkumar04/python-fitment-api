"""On-demand OEM wheel specs lookup from wheel-size.com."""

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup


@dataclass
class OEMSpecs:
    year: int
    make: str
    model: str
    bolt_pattern: str  # e.g., "5x114.3"
    center_bore: float  # e.g., 64.1
    oem_offset_min: int
    oem_offset_max: int
    oem_wheel_sizes: list[str]  # e.g., ["17x7", "18x8"]
    oem_tire_sizes: list[str]  # e.g., ["215/55R16", "235/40R18"]
    stud_size: str  # e.g., "M12x1.5"


class WheelSizeLookup:
    """Fetches OEM wheel specs from wheel-size.com on demand."""

    BASE_URL = "https://www.wheel-size.com"
    CACHE_FILE = Path("datafiles/wheel_size_cache.json")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=True,
            timeout=15.0,
        )
        self.cache = self._load_cache()

    def _load_cache(self) -> dict[str, Any]:
        """Load cached specs from file."""
        if self.CACHE_FILE.exists():
            try:
                with open(self.CACHE_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save_cache(self) -> None:
        """Save cache to file."""
        self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CACHE_FILE, "w") as f:
            json.dump(self.cache, f, indent=2)

    def _cache_key(self, year: int, make: str, model: str) -> str:
        """Generate cache key for a vehicle."""
        return f"{year}_{make.lower()}_{model.lower()}".replace(" ", "_")

    def _normalize_make(self, make: str) -> str:
        """Normalize make name for URL."""
        return make.lower().replace(" ", "-").replace("_", "-")

    def _normalize_model(self, model: str) -> str:
        """Normalize model name for URL."""
        # Remove trim info for base lookup
        model = model.lower()
        # Common trim suffixes to strip for base model lookup
        for suffix in [
            " miata",  # Mazda MX-5 Miata -> mx-5
            " sport",
            " touring",
            " ex",
            " lx",
            " si",
            " type r",
            " type-r",
            " base",
            " premium",
            " limited",
            " se",
            " sel",
            " xle",
            " xse",
        ]:
            if model.endswith(suffix):
                model = model[: -len(suffix)]
                break
        return model.replace(" ", "-").replace("_", "-")

    def lookup(self, year: int, make: str, model: str) -> OEMSpecs | None:
        """Look up OEM specs for a vehicle (thread-safe).

        Checks cache first, then fetches from wheel-size.com if needed.
        The fetch happens outside the lock so slow scrapes don't block
        other threads from reading cached results.
        """
        cache_key = self._cache_key(year, make, model)

        # Check cache (under lock)
        with self._lock:
            if cache_key in self.cache:
                data = self.cache[cache_key]
                if data is None:
                    return None
                return OEMSpecs(**data)

        # Fetch from wheel-size.com (outside lock — may be slow)
        specs = self._fetch_specs(year, make, model)

        # Cache result under lock (double-check another thread didn't populate)
        with self._lock:
            if cache_key not in self.cache:
                if specs:
                    self.cache[cache_key] = {
                        "year": specs.year,
                        "make": specs.make,
                        "model": specs.model,
                        "bolt_pattern": specs.bolt_pattern,
                        "center_bore": specs.center_bore,
                        "oem_offset_min": specs.oem_offset_min,
                        "oem_offset_max": specs.oem_offset_max,
                        "oem_wheel_sizes": specs.oem_wheel_sizes,
                        "oem_tire_sizes": specs.oem_tire_sizes,
                        "stud_size": specs.stud_size,
                    }
                else:
                    self.cache[cache_key] = None
                self._save_cache()

        return specs

    def _fetch_specs(self, year: int, make: str, model: str) -> OEMSpecs | None:
        """Fetch specs from wheel-size.com."""
        make_normalized = self._normalize_make(make)
        model_normalized = self._normalize_model(model)

        url = f"{self.BASE_URL}/size/{make_normalized}/{model_normalized}/{year}/"

        try:
            resp = self.client.get(url)

            # Check for CAPTCHA/bot protection (AWS WAF returns 405 with verification page)
            if resp.status_code == 405 or "Human Verification" in resp.text[:1000]:
                # Site is blocking automated requests
                return None

            if resp.status_code != 200:
                # Try without year to get model page
                url = f"{self.BASE_URL}/size/{make_normalized}/{model_normalized}/"
                resp = self.client.get(url)
                if resp.status_code != 200:
                    return None

            soup = BeautifulSoup(resp.text, "lxml")
            return self._parse_specs(soup, year, make, model)

        except Exception as e:
            print(f"Error fetching wheel-size.com: {e}")
            return None

    def _parse_specs(
        self, soup: BeautifulSoup, year: int, make: str, model: str
    ) -> OEMSpecs | None:
        """Parse OEM specs from the page tables."""
        bolt_pattern = ""
        center_bore = 0.0
        offsets: list[int] = []
        wheel_sizes: list[str] = []
        tire_sizes: list[str] = []
        stud_size = ""

        page_text = soup.get_text()

        # Parse data from tables (primary source)
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                # Process each cell separately for cleaner parsing
                cells = row.find_all(["td", "th"])

                for cell in cells:
                    cell_text = cell.get_text(strip=True)

                    # Extract tire sizes (e.g., "195/50R16", "205/45ZR17")
                    tire_matches = re.findall(r"(\d{3}/\d{2}Z?R\d{2})", cell_text)
                    for tm in tire_matches:
                        if tm not in tire_sizes:
                            tire_sizes.append(tm)

                    # Extract wheel sizes (e.g., "6.5Jx16", "7Jx17", "8Jx18")
                    # Width is typically 5-12 inches
                    wheel_matches = re.findall(
                        r"\b(\d+(?:\.\d)?)[Jj][x×](\d{2})\b", cell_text
                    )
                    for wm in wheel_matches:
                        width = float(wm[0])
                        if 5 <= width <= 12:  # Valid wheel width range
                            size = f"{wm[1]}x{wm[0]}"  # diameter x width
                            if size not in wheel_sizes:
                                wheel_sizes.append(size)

                    # Extract offsets (e.g., "ET45", "ET50")
                    offset_matches = re.findall(r"ET(\d{1,2})\b", cell_text)
                    for om in offset_matches:
                        val = int(om)
                        if 0 <= val <= 60 and val not in offsets:
                            offsets.append(val)

                    # Extract offset ranges (e.g., "43 - 47") - only in offset column
                    # Match pattern like "43 - 47" with spaces around dash
                    range_match = re.match(r"^(\d{2})\s*[-–]\s*(\d{2})$", cell_text)
                    if range_match:
                        val1, val2 = (
                            int(range_match.group(1)),
                            int(range_match.group(2)),
                        )
                        if 0 <= val1 <= 60 and val1 not in offsets:
                            offsets.append(val1)
                        if 0 <= val2 <= 60 and val2 not in offsets:
                            offsets.append(val2)

        # Find bolt pattern from page text (e.g., "4x100", "5x114.3")
        bolt_match = re.search(
            r"\b([456])\s*[x×]\s*(\d{2,3}(?:\.\d)?)\b", page_text, re.I
        )
        if bolt_match:
            pcd = float(bolt_match.group(2))
            if 98 <= pcd <= 170:
                bolt_pattern = f"{bolt_match.group(1)}x{bolt_match.group(2)}"

        # If no bolt pattern found, try common patterns in page
        if not bolt_pattern:
            for pattern in ["4x100", "5x100", "5x114.3", "5x112", "5x120"]:
                if pattern in page_text or pattern.replace("x", "×") in page_text:
                    bolt_pattern = pattern.upper()
                    break

        # Find center bore
        bore_match = re.search(r"(?:CB|bore|hub)[:\s]*(\d{2}\.\d)", page_text, re.I)
        if bore_match:
            center_bore = float(bore_match.group(1))

        # Find stud size (e.g., "M12x1.5")
        stud_match = re.search(r"M(\d{2})[x×](\d\.\d{1,2})", page_text)
        if stud_match:
            stud_size = f"M{stud_match.group(1)}x{stud_match.group(2)}"

        # Need at least some useful data
        if not wheel_sizes and not offsets:
            return None

        # Use default bolt pattern based on make if not found
        if not bolt_pattern:
            make_patterns = {
                "mazda": "4X100",
                "honda": "5X114.3",
                "toyota": "5X114.3",
                "bmw": "5X120",
                "audi": "5X112",
                "volkswagen": "5X112",
            }
            bolt_pattern = make_patterns.get(make.lower(), "5X114.3")

        # Calculate offset range
        offsets = list(set(offsets))  # Remove duplicates
        offset_min = min(offsets) if offsets else 40
        offset_max = max(offsets) if offsets else 50

        return OEMSpecs(
            year=year,
            make=make,
            model=model,
            bolt_pattern=bolt_pattern.upper(),
            center_bore=center_bore,
            oem_offset_min=offset_min,
            oem_offset_max=offset_max,
            oem_wheel_sizes=wheel_sizes[:5],
            oem_tire_sizes=tire_sizes[:5],
            stud_size=stud_size,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()


# Singleton instance (thread-safe)
_lookup_instance: WheelSizeLookup | None = None
_lookup_lock = threading.Lock()


def get_wheel_size_lookup() -> WheelSizeLookup:
    """Get or create the singleton lookup instance (thread-safe)."""
    global _lookup_instance
    if _lookup_instance is None:
        with _lookup_lock:
            if _lookup_instance is None:
                _lookup_instance = WheelSizeLookup()
    return _lookup_instance
