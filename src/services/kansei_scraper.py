"""Kansei wheel catalog scraper.

Scrapes kanseiwheels.com (Shopify) for the complete wheel catalog.
Uses the Shopify JSON API (/products/{handle}.json) for reliable structured
data, with HTML collection pages only for product discovery.

Captures per-variant: diameter, width, offset, bolt_pattern, price, weight,
    in_stock, sku, barcode
Captures per-product: construction type, brake clearance notes from description
"""

import json
import re
import time
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
    weight: float | None = None  # lbs
    weight_unit: str = "lb"
    barcode: str | None = None
    construction: str | None = None  # "Formlite", etc.
    brake_clearance_notes: str | None = None
    compare_at_price: float | None = None


def parse_sku(sku: str) -> dict[str, float | int | None]:
    """Parse Kansei SKU to extract wheel specs.

    SKU formats:
    - Street: K11S-179018+22 -> K[model][finish]-[diam][width][bolt]+[offset]
    - Truck: K12MB-78560-10 -> K[model][finish]-[diam][width][bolt]-[offset]
    """
    result: dict[str, float | int | None] = {
        "diameter": None,
        "width": None,
        "offset": None,
    }

    match = re.search(r"-(\d{2})(\d{2})(\d{2})([+-]?\d+)$", sku)
    if match:
        result["diameter"] = int(match.group(1))
        width_code = int(match.group(2))
        if width_code >= 10:
            result["width"] = width_code / 10
        result["offset"] = int(match.group(4))

    return result


def parse_bolt_pattern(bp_str: str) -> tuple[int | None, float | None]:
    """Parse bolt pattern string like '5X120' into (lugs, pcd)."""
    match = re.match(r"(\d+)[Xx](\d+\.?\d*)", bp_str)
    if match:
        return int(match.group(1)), float(match.group(2))
    return None, None


def _extract_construction(body_html: str, tags: str) -> str | None:
    """Extract construction type from product description or tags."""
    tags_lower = tags.lower() if tags else ""
    if "formlite" in tags_lower:
        return "Formlite"

    body_lower = body_html.lower() if body_html else ""
    if "formlite" in body_lower:
        return "Formlite"
    if "flow form" in body_lower or "flow-form" in body_lower:
        return "Flow Form"
    if "rotary forged" in body_lower:
        return "Rotary Forged"
    if "cast" in body_lower:
        return "Cast"
    return None


def _extract_brake_clearance_notes(body_html: str) -> str | None:
    """Extract brake clearance claims from product description."""
    if not body_html:
        return None

    body_lower = body_html.lower()
    notes: list[str] = []

    # Look for specific caliper compatibility claims
    brembo_match = re.search(
        r"clears?\s+(?:all\s+)?([^.!<]+(?:brembo|caliper|brake)[^.!<]*)",
        body_lower,
    )
    if brembo_match:
        notes.append(brembo_match.group(0).strip())

    # Look for general brake clearance mentions
    if "brake clearance" in body_lower and not notes:
        clearance_match = re.search(
            r"([^.!<]*brake clearance[^.!<]*)", body_lower
        )
        if clearance_match:
            notes.append(clearance_match.group(1).strip())

    return "; ".join(notes) if notes else None


@dataclass
class ProductMeta:
    """Product-level metadata shared by all variants."""

    model: str
    finish: str
    category: str
    url: str
    construction: str | None
    brake_clearance_notes: str | None


class KanseiScraper:
    BASE_URL = "https://kanseiwheels.com"

    # Non-wheel product URL fragments to skip
    SKIP_PATTERNS = [
        "cap", "accessory", "accessories", "gel-cap", "lug",
        "banner", "sticker", "hat", "tee", "hoodie", "shirt",
        "apparel", "gear", "soft-goods",
    ]

    def __init__(self) -> None:
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
            follow_redirects=True,
            timeout=30.0,
        )
        self.wheels: list[KanseiWheel] = []
        self._product_meta: dict[str, ProductMeta] = {}

    def get_collection_products(self, collection_url: str) -> list[str]:
        """Get all product URLs from a collection page."""
        product_urls: list[str] = []
        page = 1

        while True:
            url = f"{self.BASE_URL}{collection_url}?page={page}"
            resp = self.client.get(url)
            soup = BeautifulSoup(resp.text, "lxml")

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

            if page > 20:
                break

        return product_urls

    def _get_product_json(self, product_url: str) -> dict[str, Any] | None:
        """Fetch product data from Shopify JSON API."""
        # Extract handle from URL: .../products/kansei-roku-gloss-black -> kansei-roku-gloss-black
        handle = product_url.rstrip("/").split("/products/")[-1]
        # Strip query params
        handle = handle.split("?")[0]

        json_url = f"{self.BASE_URL}/products/{handle}.json"
        try:
            resp = self.client.get(json_url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("product")
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f"  JSON API failed for {handle}: {e}")
        return None

    def scrape_product(self, url: str, category: str) -> list[KanseiWheel]:
        """Scrape a single product using Shopify JSON API."""
        wheels: list[KanseiWheel] = []

        product = self._get_product_json(url)
        if not product:
            print(f"  Skipping {url} (no JSON data)")
            return wheels

        # Parse model and finish from title (e.g., "ROKU - Gloss Black")
        title = product.get("title", "Unknown")
        title_parts = title.split(" - ", 1)
        model = title_parts[0].strip() if title_parts else title
        finish = title_parts[1].strip() if len(title_parts) > 1 else ""

        # Clean model name: strip leading *, size suffixes like '15"'
        model = model.lstrip("*").strip()
        model = re.sub(r'\s*\d+["\u201d]?\s*$', "", model).strip()

        # Extract product-level metadata
        body_html = product.get("body_html", "")
        tags = product.get("tags", "")
        if isinstance(tags, list):
            tags = ", ".join(tags)
        construction = _extract_construction(body_html, tags)
        brake_notes = _extract_brake_clearance_notes(body_html)

        meta = ProductMeta(
            model=model,
            finish=finish,
            category=category,
            url=url,
            construction=construction,
            brake_clearance_notes=brake_notes,
        )

        # Parse each variant
        for variant in product.get("variants", []):
            wheel = self._parse_json_variant(variant, meta)
            if wheel:
                wheels.append(wheel)

        return wheels

    def _parse_json_variant(
        self, variant: dict[str, Any], meta: ProductMeta
    ) -> KanseiWheel | None:
        """Parse a Shopify JSON variant into a KanseiWheel."""
        try:
            sku = variant.get("sku", "")
            title = variant.get("title", "") or variant.get("name", "")
            available = variant.get("available", True)

            # Price — Shopify JSON API returns string like "389.00"
            price_raw = variant.get("price", "0")
            if isinstance(price_raw, str):
                price = float(price_raw)
            elif isinstance(price_raw, int):
                price = price_raw / 100  # Shopify storefront API uses cents
            else:
                price = float(price_raw)

            # Compare-at price (original price before sale)
            compare_raw = variant.get("compare_at_price")
            compare_at: float | None = None
            if compare_raw:
                if isinstance(compare_raw, str):
                    compare_at = float(compare_raw) if float(compare_raw) > 0 else None
                elif isinstance(compare_raw, (int, float)):
                    compare_at = float(compare_raw) if compare_raw > 0 else None

            # Weight — JSON API provides grams and/or weight + weight_unit
            weight_lb: float | None = None
            grams = variant.get("grams")
            if grams and grams > 0:
                weight_lb = round(grams / 453.592, 2)
            elif variant.get("weight") and variant.get("weight_unit") == "lb":
                weight_lb = round(float(variant["weight"]), 2)

            barcode = variant.get("barcode") or None

            # Parse size/bolt/offset from variant title
            # Format: "18X9 | 5X114.3 | 12 | K14B-189012+12"
            # or:     "18X9.5 | 5X114.3 | +22"
            diameter: float | None = None
            width: float | None = None
            offset: int | None = None
            bolt_pattern = ""

            size_match = re.search(r"(\d+)[Xx](\d+\.?\d*)", title)
            if size_match:
                diameter = float(size_match.group(1))
                width = float(size_match.group(2))

            # Bolt pattern — second NxNNN.N pattern in title
            remaining = title.replace(size_match.group(0), "", 1) if size_match else title
            bolt_match = re.search(r"(\d+[Xx]\d+\.?\d*)", remaining)
            if bolt_match:
                bolt_pattern = bolt_match.group(1).upper()

            # Offset — look for +/- number or bare number after bolt pattern
            offset_match = re.search(r"\|\s*([+-]?\d+)\s*(?:\||$)", title)
            if offset_match:
                offset = int(offset_match.group(1))
            else:
                # Try end of string
                offset_end = re.search(r"([+-]\d+)\s*$", title)
                if offset_end:
                    offset = int(offset_end.group(1))

            # Fallback to SKU parsing
            if not all([diameter, width, offset is not None]):
                sku_specs = parse_sku(sku)
                if diameter is None and sku_specs.get("diameter") is not None:
                    diameter = float(sku_specs["diameter"])  # type: ignore[arg-type]
                if width is None and sku_specs.get("width") is not None:
                    width = float(sku_specs["width"])  # type: ignore[arg-type]
                if offset is None and sku_specs.get("offset") is not None:
                    offset = int(sku_specs["offset"])  # type: ignore[arg-type]

            if diameter is None or width is None or offset is None or not sku:
                return None

            return KanseiWheel(
                model=meta.model,
                finish=meta.finish,
                sku=sku,
                diameter=diameter,
                width=width,
                bolt_pattern=bolt_pattern,
                offset=offset,
                price=price,
                category=meta.category,
                url=meta.url,
                in_stock=bool(available),
                weight=weight_lb,
                barcode=barcode,
                construction=meta.construction,
                brake_clearance_notes=meta.brake_clearance_notes,
                compare_at_price=compare_at,
            )
        except Exception:
            return None

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
                if any(x in url.lower() for x in self.SKIP_PATTERNS):
                    continue

                wheels = self.scrape_product(url, category)
                for wheel in wheels:
                    if wheel.sku not in seen_skus:
                        all_wheels.append(wheel)
                        seen_skus.add(wheel.sku)

                # Be polite to Shopify
                time.sleep(0.3)

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
                "barcode": w.barcode,
                "construction": w.construction,
                "brake_clearance_notes": w.brake_clearance_notes,
                "compare_at_price": w.compare_at_price,
            }
            for w in self.wheels
        ]

    def save_to_json(self, filepath: str) -> None:
        """Save scraped wheels to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict_list(), f, indent=2)

    def print_summary(self) -> None:
        """Print a summary of scraped data."""
        models: dict[str, int] = {}
        bolt_patterns: dict[str, int] = {}
        diameters: dict[float, int] = {}
        has_weight = 0

        for w in self.wheels:
            models[w.model] = models.get(w.model, 0) + 1
            bolt_patterns[w.bolt_pattern] = bolt_patterns.get(w.bolt_pattern, 0) + 1
            diameters[w.diameter] = diameters.get(w.diameter, 0) + 1
            if w.weight:
                has_weight += 1

        print(f"\n{'='*60}")
        print(f"Total variants: {len(self.wheels)}")
        print(f"With weight data: {has_weight}/{len(self.wheels)}")
        print(f"\nModels ({len(models)}):")
        for m, count in sorted(models.items()):
            print(f"  {m}: {count} variants")
        print(f"\nBolt patterns ({len(bolt_patterns)}):")
        for bp, count in sorted(bolt_patterns.items(), key=lambda x: -x[1]):
            print(f"  {bp}: {count}")
        print(f"\nDiameters ({len(diameters)}):")
        for d, count in sorted(diameters.items()):
            print(f"  {d}\": {count}")

        # Construction types
        constructions: dict[str, int] = {}
        for w in self.wheels:
            c = w.construction or "unknown"
            constructions[c] = constructions.get(c, 0) + 1
        print("\nConstruction types:")
        for c, count in sorted(constructions.items(), key=lambda x: -x[1]):
            print(f"  {c}: {count}")

        # Brake clearance notes
        brake_models: set[str] = set()
        for w in self.wheels:
            if w.brake_clearance_notes:
                brake_models.add(w.model)
        if brake_models:
            print(f"\nModels with brake clearance claims: {', '.join(sorted(brake_models))}")
        print(f"{'='*60}")

    def close(self) -> None:
        self.client.close()


if __name__ == "__main__":
    scraper = KanseiScraper()
    try:
        wheels = scraper.scrape_all()
        print(f"\nScraped {len(wheels)} wheel variants")

        scraper.print_summary()

        # Save to JSON
        scraper.save_to_json("datafiles/kansei_wheels.json")
        print("\nSaved to datafiles/kansei_wheels.json")

        # Print sample
        print("\nSample wheels:")
        for w in wheels[:5]:
            weight_str = f"{w.weight}lb" if w.weight else "no weight"
            print(
                f"  {w.model} {w.finish}: {w.diameter}x{w.width} ET{w.offset} "
                f"{w.bolt_pattern} - ${w.price} ({weight_str})"
            )
    finally:
        scraper.close()
