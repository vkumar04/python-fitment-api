import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup


@dataclass
class KanseiWheel:
    model: str
    finish: str
    sku: str
    diameter: float
    width: float
    bolt_pattern: str
    offset: int
    price: float
    category: str  # "street" or "offroad"
    url: str
    in_stock: bool = True
    weight: float | None = None


def parse_sku(sku: str) -> dict[str, float | int | None]:
    """
    Parse Kansei SKU to extract wheel specs.

    SKU formats:
    - Street: K11S-179018+22 -> K[model][finish]-[diam][width][bolt]+[offset]
    - Truck: K12MB-78560-10 -> K[model][finish]-[diam][width][bolt]-[offset]
    """
    result: dict[str, float | int | None] = {
        "diameter": None,
        "width": None,
        "offset": None,
    }

    # Match patterns like K11S-179018+22 or K12MB-78560-10
    # The size portion encodes diameter and width
    match = re.search(r"-(\d{2})(\d{2})(\d{2})([+-]?\d+)$", sku)
    if match:
        result["diameter"] = int(match.group(1))
        # Width is encoded - need to decode (e.g., 90 = 9.0, 85 = 8.5, 105 = 10.5)
        width_code = int(match.group(2))
        if width_code >= 100:
            result["width"] = width_code / 10
        elif width_code >= 10:
            result["width"] = width_code / 10
        result["offset"] = int(match.group(4))

    return result


def parse_bolt_pattern(bp_str: str) -> tuple[int | None, float | None]:
    """Parse bolt pattern string like '5X120' into (lugs, pcd)."""
    match = re.match(r"(\d+)[Xx](\d+\.?\d*)", bp_str)
    if match:
        return int(match.group(1)), float(match.group(2))
    return None, None


class KanseiScraper:
    BASE_URL = "https://kanseiwheels.com"

    def __init__(self) -> None:
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
            follow_redirects=True,
            timeout=30.0,
        )
        self.wheels: list[KanseiWheel] = []

    def get_collection_products(self, collection_url: str) -> list[str]:
        """Get all product URLs from a collection page."""
        product_urls: list[str] = []
        page = 1

        while True:
            url = f"{self.BASE_URL}{collection_url}?page={page}"
            resp = self.client.get(url)
            soup = BeautifulSoup(resp.text, "lxml")

            # Find product links
            products = soup.select('a[href*="/products/"]')
            new_urls: list[str] = []
            for p in products:
                href = p.get("href")
                if href is None:
                    continue
                href_str = str(href) if not isinstance(href, str) else href
                if "/products/" in href_str and href_str not in product_urls:
                    full_url = (
                        href_str
                        if href_str.startswith("http")
                        else f"{self.BASE_URL}{href_str}"
                    )
                    if full_url not in product_urls and full_url not in new_urls:
                        new_urls.append(full_url)

            if not new_urls:
                break

            product_urls.extend(new_urls)
            page += 1

            # Safety limit
            if page > 20:
                break

        return product_urls

    def scrape_product(self, url: str, category: str) -> list[KanseiWheel]:
        """Scrape a single product page for all variants."""
        wheels: list[KanseiWheel] = []

        try:
            resp = self.client.get(url)
            soup = BeautifulSoup(resp.text, "lxml")

            # Get product title
            title_elem = soup.select_one('h1, .product-title, [class*="title"]')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"

            # Parse model and finish from title (e.g., "TANDEM - Hyper Silver")
            title_parts = title.split(" - ")
            model = title_parts[0].strip() if title_parts else title
            finish = title_parts[1].strip() if len(title_parts) > 1 else ""

            # Try to find JSON-LD data or variant data
            scripts = soup.find_all("script", type="application/json")
            for script in scripts:
                try:
                    script_content = script.string
                    if script_content is None:
                        continue
                    data = json.loads(script_content)
                    if isinstance(data, dict) and "variants" in data:
                        for variant in data["variants"]:
                            wheel = self._parse_variant(
                                variant, model, finish, category, url
                            )
                            if wheel:
                                wheels.append(wheel)
                except (json.JSONDecodeError, TypeError):
                    continue

            # Also look for variant data in script tags
            for script in soup.find_all("script"):
                script_text = script.string
                if script_text and "variants" in script_text:
                    # Try to extract variant JSON
                    match = re.search(
                        r'"variants"\s*:\s*(\[.*?\])', script_text, re.DOTALL
                    )
                    if match:
                        try:
                            variants = json.loads(match.group(1))
                            for variant in variants:
                                wheel = self._parse_variant(
                                    variant, model, finish, category, url
                                )
                                if wheel and wheel.sku not in [w.sku for w in wheels]:
                                    wheels.append(wheel)
                        except json.JSONDecodeError:
                            continue

            # Fallback: parse visible variant options
            if not wheels:
                wheels = self._parse_visible_variants(
                    soup, model, finish, category, url
                )

        except Exception as e:
            print(f"Error scraping {url}: {e}")

        return wheels

    def _parse_variant(
        self, variant: dict[str, Any], model: str, finish: str, category: str, url: str
    ) -> KanseiWheel | None:
        """Parse a variant dict into a KanseiWheel."""
        try:
            sku = variant.get("sku", "")
            title = variant.get("title", "") or variant.get("name", "")
            price = variant.get("price", 0)
            if isinstance(price, int):
                price = price / 100  # Shopify stores cents

            available = variant.get("available", True)

            # Parse size from title (e.g., "18X10.5 | 5X100 | +12")
            diameter: float | None = None
            width: float | None = None
            offset: int | None = None
            bolt_pattern = ""

            # Try to parse from title
            size_match = re.search(r"(\d+)[Xx](\d+\.?\d*)", title)
            if size_match:
                diameter = float(size_match.group(1))
                width = float(size_match.group(2))

            bolt_match = re.search(
                r"(\d+[Xx]\d+\.?\d*)",
                title.replace(size_match.group(0) if size_match else "", ""),
            )
            if bolt_match:
                bolt_pattern = bolt_match.group(1).upper()

            offset_match = re.search(r"([+-]?\d+)\s*$", title)
            if offset_match:
                offset = int(offset_match.group(1))

            # Fallback to SKU parsing
            if not all([diameter, width, offset is not None]):
                sku_specs = parse_sku(sku)
                if diameter is None:
                    diam_val = sku_specs.get("diameter")
                    diameter = float(diam_val) if diam_val is not None else None
                if width is None:
                    width_val = sku_specs.get("width")
                    width = float(width_val) if width_val is not None else None
                if offset is None:
                    offset_val = sku_specs.get("offset")
                    offset = int(offset_val) if offset_val is not None else None

            if diameter is None or width is None or offset is None or not sku:
                return None

            return KanseiWheel(
                model=model,
                finish=finish,
                sku=sku,
                diameter=diameter,
                width=width,
                bolt_pattern=bolt_pattern,
                offset=offset,
                price=float(price),
                category=category,
                url=url,
                in_stock=bool(available),
            )
        except Exception:
            return None

    def _parse_visible_variants(
        self, soup: BeautifulSoup, model: str, finish: str, category: str, url: str
    ) -> list[KanseiWheel]:
        """Parse variants from visible page elements as fallback."""
        wheels: list[KanseiWheel] = []

        # Look for select options or radio buttons with variant info
        options = soup.select('select option, input[type="radio"]')
        for opt in options:
            text = opt.get_text(strip=True) or str(opt.get("value", ""))
            if re.search(r"\d+[Xx]\d+", text):
                # This looks like a size option
                size_match = re.search(r"(\d+)[Xx](\d+\.?\d*)", text)
                if not size_match:
                    continue
                bolt_match = re.search(
                    r"(\d+[Xx]\d+\.?\d*)",
                    text[size_match.end() :],
                )
                offset_match = re.search(r"([+-]?\d+)\s*$", text)

                if size_match and offset_match:
                    sku_attr = opt.get("data-sku")
                    sku_val = str(sku_attr) if sku_attr else f"{model}-{text}"
                    wheels.append(
                        KanseiWheel(
                            model=model,
                            finish=finish,
                            sku=sku_val,
                            diameter=float(size_match.group(1)),
                            width=float(size_match.group(2)),
                            bolt_pattern=bolt_match.group(1).upper()
                            if bolt_match
                            else "",
                            offset=int(offset_match.group(1)),
                            price=0.0,
                            category=category,
                            url=url,
                        )
                    )

        return wheels

    def scrape_all(self) -> list[KanseiWheel]:
        """Scrape all Kansei wheel products."""
        collections = [
            ("/collections/kansei-wheels", "street"),
            ("/collections/kansei-offroad-wheels", "offroad"),
        ]

        all_wheels: list[KanseiWheel] = []
        seen_skus: set[str] = set()

        for collection_url, category in collections:
            print(f"Scraping {category} wheels from {collection_url}...")
            product_urls = self.get_collection_products(collection_url)
            print(f"Found {len(product_urls)} products")

            for url in product_urls:
                # Skip non-wheel products
                if any(
                    x in url.lower()
                    for x in ["cap", "accessory", "accessories", "gel-cap", "lug"]
                ):
                    continue

                wheels = self.scrape_product(url, category)
                for wheel in wheels:
                    if wheel.sku not in seen_skus:
                        all_wheels.append(wheel)
                        seen_skus.add(wheel.sku)

        self.wheels = all_wheels
        return all_wheels

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Convert wheels to list of dicts for storage."""
        return [
            {
                "model": w.model,
                "finish": w.finish,
                "sku": w.sku,
                "diameter": w.diameter,
                "width": w.width,
                "bolt_pattern": w.bolt_pattern,
                "offset": w.offset,
                "price": w.price,
                "category": w.category,
                "url": w.url,
                "in_stock": w.in_stock,
                "weight": w.weight,
            }
            for w in self.wheels
        ]

    def save_to_json(self, filepath: str) -> None:
        """Save scraped wheels to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict_list(), f, indent=2)

    def close(self) -> None:
        self.client.close()


if __name__ == "__main__":
    scraper = KanseiScraper()
    try:
        wheels = scraper.scrape_all()
        print(f"\nScraped {len(wheels)} wheel variants")

        # Save to JSON
        scraper.save_to_json("datafiles/kansei_wheels.json")
        print("Saved to datafiles/kansei_wheels.json")

        # Print sample
        for w in wheels[:5]:
            print(
                f"  {w.model} {w.finish}: {w.diameter}x{w.width} ET{w.offset} {w.bolt_pattern} - ${w.price}"
            )
    finally:
        scraper.close()
