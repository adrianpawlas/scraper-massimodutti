"""Parse Massimo Dutti API responses."""
import json
import re
from typing import Any

from config import BASE_PRODUCT_URL, COUNTRY_TO_CURRENCY, IMAGE_BASE_URL


def detect_api_type(data: dict) -> str:
    """Detect API response type: 'products' (full data) or 'grid' (product IDs)."""
    if "products" in data:
        return "products"
    if "gridElements" in data or "productIds" in data:
        return "grid"
    raise ValueError("Unknown API response format")


def extract_product_ids_from_grid(data: dict) -> set[int]:
    """Extract all unique product IDs from grid/category API response."""
    product_ids = set()

    if "productIds" in data:
        product_ids.update(data["productIds"])

    if "sortedProductIds" in data:
        product_ids.update(data["sortedProductIds"])

    if "gridElements" in data:
        for elem in data["gridElements"]:
            if elem.get("type") == "block" and "commercialComponentIds" in elem:
                for cc in elem["commercialComponentIds"]:
                    if isinstance(cc, dict) and "ccId" in cc:
                        product_ids.add(cc["ccId"])
                    elif isinstance(cc, int):
                        product_ids.add(cc)
            if "ccIds" in elem:
                product_ids.update(elem["ccIds"])

    # From result.typeFilter and result.attributeFilter (nested structure)
    result = data.get("result", data)
    if "typeFilter" in result:
        for tf in result["typeFilter"]:
            product_ids.update(tf.get("productIds", []))
    if "attributeFilter" in result:
        for af in result["attributeFilter"]:
            if "values" in af:
                for v in af["values"]:
                    product_ids.update(v.get("productIds", []))

    return product_ids


def get_image_urls_from_product(bundle_summary: dict) -> tuple[str | None, list[str]]:
    """
    Extract main image URL and additional image URLs from product.
    Returns (main_image_url, [additional_urls]).
    """
    main_url = None
    additional_urls = []

    detail = bundle_summary.get("detail", {})
    colors = detail.get("colors", [])

    # Try xmedia first (has full URLs)
    xmedia = detail.get("xmedia", [])
    all_urls = []
    for xm in xmedia:
        for item in xm.get("xmediaItems", []):
            for media in item.get("medias", []):
                url = media.get("url")
                if url and url not in all_urls:
                    all_urls.append(url)

    if all_urls:
        main_url = all_urls[0]
        additional_urls = all_urls[1:]

    # Fallback: build URL from colors[].image.url path
    if not main_url and colors:
        for color in colors:
            img = color.get("image", {})
            path = img.get("url")
            if path:
                # Path format: /2026/V/0/2/p/1223/203/720/1223203720
                # Last part is the image ID - build URL
                parts = path.strip("/").split("/")
                img_id = parts[-1] if parts else None
                if img_id:
                    url = f"{IMAGE_BASE_URL}/assets/public/{img_id[:4]}/{img_id[4:8]}/{img_id}_{{suffix}}.jpg"
                    # Try common suffixes - o1 is typically main product image
                    for suffix in ["o1", "1_1_1", "c"]:
                        candidate = f"{IMAGE_BASE_URL}/is/image/massimodutti/{img_id}_{suffix}"
                        # Simpler: use their CDN format
                        candidate = f"{IMAGE_BASE_URL}/2/3/2/5/4/{img_id}_1_1_1.jpg"
                        break
                    # Massimo Dutti uses: https://static.massimodutti.net/... from xmedia
                    # Without xmedia we'd need to fetch - use first color's path
                    # Build: path format 1223203720, use known pattern
                    ref = path.split("/")[-1]
                    main_url = f"{IMAGE_BASE_URL}/is/image/massimodutti/{ref}_1_1_1"
                    break

    return main_url, additional_urls


def format_price(price_cents: str | int, currency: str) -> str:
    """Convert price from cents to formatted string: 69.95EUR."""
    try:
        cents = int(price_cents)
        amount = cents / 100
        return f"{amount:.2f}{currency}"
    except (ValueError, TypeError):
        return ""


def slugify(text: str) -> str:
    """Create URL slug from product name."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:80] if text else "product"


def get_categories_from_attributes(attributes: list[dict]) -> str:
    """Extract category from XTYPEFILTER attributes, comma-separated."""
    categories = []
    for attr in attributes or []:
        if attr.get("type") == "XTYPEFILTER" and attr.get("value"):
            cat = attr["value"].strip()
            if cat and cat not in categories:
                categories.append(cat)
    # Handle compound categories like "Sweaters & Hoodies" -> "Sweaters, Hoodies"
    result = []
    for c in categories:
        if "&" in c:
            result.extend(x.strip() for x in c.split("&") if x.strip())
        else:
            result.append(c)
    return ", ".join(result) if result else ""


def get_description_from_attributes(attributes: list[dict]) -> str:
    """Build description from DESCRIPTION type attributes."""
    parts = []
    for attr in attributes or []:
        if attr.get("type") == "DESCRIPTION" and attr.get("value"):
            parts.append(attr["value"])
    return " | ".join(parts) if parts else ""


def get_gender_from_attributes(attributes: list[dict]) -> str:
    """Extract gender from MAN or WOMAN type attributes. Default 'man'."""
    for attr in attributes or []:
        attr_type = attr.get("type", "")
        if attr_type == "WOMAN":
            return "woman"
        if attr_type == "MAN":
            return "man"
    return "man"


def collect_prices_by_currency(
    bundle_summary: dict,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Collect prices (original) and sale prices by currency from all sizes/colors.
    API: price=current price, oldPrice=original when on sale.
    Returns (original_prices, sale_prices) - price=original, sale=discounted or same.
    """
    original: dict[str, int] = {}  # currency -> original price in cents
    sale: dict[str, int] = {}  # currency -> sale price in cents (discounted or same as original)

    colors = bundle_summary.get("detail", {}).get("colors", [])
    for color in colors:
        for size in color.get("sizes", []):
            country = size.get("country", "")
            currency = COUNTRY_TO_CURRENCY.get(country.upper(), "EUR")

            price_str = size.get("price")
            old_price_str = size.get("oldPrice")

            try:
                price_cents = int(price_str) if price_str else None
                old_cents = int(old_price_str) if old_price_str else None

                if price_cents is not None:
                    if old_cents is not None:
                        original[currency] = old_cents
                        sale[currency] = price_cents
                    else:
                        original[currency] = price_cents
                        sale[currency] = price_cents
            except (ValueError, TypeError):
                pass

    price_formatted = {c: format_price(p, c) for c, p in original.items()}
    sale_formatted = {c: format_price(p, c) for c, p in sale.items()}

    return price_formatted, sale_formatted


def build_product_url(product: dict, bundle_summary: dict, gender: str = "man") -> str:
    """Build product page URL. gender: 'man' or 'woman'."""
    detail = bundle_summary.get("detail", {})
    ref = detail.get("reference") or detail.get("displayReference")
    reference = ""
    if ref:
        base = ref.split("-")[0].replace("/", "")
        reference = base[:12] if base else ""

    name = product.get("name") or product.get("nameEn") or "product"
    slug = slugify(name)

    path = f"{BASE_PRODUCT_URL}/{gender}/clothing"
    if reference:
        return f"{path}/{slug}-c{reference}.html"
    return f"{path}/{slug}.html"


def parse_products_api(data: dict) -> list[dict]:
    """
    Parse products API response into flat product records for DB.
    One record per product (unique by product_url) - bundles share URL.
    """
    products_raw = data.get("products", [])
    records = []
    seen_urls: set[str] = set()

    for product in products_raw:
        if product.get("state") != "visible":
            continue

        bundle_summaries = product.get("bundleProductSummaries", [])
        if not bundle_summaries:
            continue

        # Use first bundle/color variant
        bundle = bundle_summaries[0]
        detail = bundle.get("detail", {})
        colors = detail.get("colors", [])

        main_image, additional_images = get_image_urls_from_product(bundle)

        if not main_image and colors:
            # Build from color image path
            img = colors[0].get("image", {})
            path = img.get("url", "")
            if path:
                img_id = path.split("/")[-1]
                main_image = f"{IMAGE_BASE_URL}/is/image/massimodutti/{img_id}_1_1_1.jpg"

        if not main_image:
            continue

        product_id = product.get("id")
        attributes = product.get("attributes", [])
        gender = get_gender_from_attributes(attributes)
        product_url = build_product_url(product, bundle, gender)

        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        category = get_categories_from_attributes(attributes)
        description = get_description_from_attributes(attributes)

        prices_by_curr, sale_by_curr = collect_prices_by_currency(bundle)

        # Order: EUR first, then USD, then others
        def ordered_prices(d: dict) -> str:
            ordered = []
            for c in ["EUR", "USD"]:
                if c in d:
                    ordered.append(d[c])
            for c, v in d.items():
                if c not in ("EUR", "USD"):
                    ordered.append(v)
            return ",".join(ordered)

        price_str = ordered_prices(prices_by_curr) if prices_by_curr else ""
        sale_str = ordered_prices(sale_by_curr) if sale_by_curr else price_str

        additional_images_str = " , ".join(additional_images) if additional_images else None

        metadata = json.dumps(
            {
                "product_id": product_id,
                "reference": detail.get("reference"),
                "display_reference": detail.get("displayReference"),
                "composition": detail.get("composition"),
                "care": detail.get("care"),
                "attributes": attributes[:20],
            },
            default=str,
        )

        records.append(
            {
                "id": f"massimodutti_{product_id}",
                "product_id": product_id,
                "product_url": product_url,
                "gender": gender,
                "image_url": main_image,
                "additional_images": additional_images_str,
                "title": product.get("name") or product.get("nameEn") or "Unknown",
                "description": description or None,
                "category": category or None,
                "price": price_str or None,
                "sale": sale_str or None,
                "metadata": metadata,
                "raw_product": product,
                "raw_bundle": bundle,
            }
        )

    return records
