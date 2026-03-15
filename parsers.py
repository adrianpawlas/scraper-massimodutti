"""Parse Massimo Dutti API responses."""
import json
import re
from typing import Any

from config import (
    BASE_PRODUCT_URL,
    COUNTRY_TO_CURRENCY,
    IMAGE_BASE_URL,
    PRODUCT_URL_LOCALE,
)


def detect_api_type(data: dict) -> str:
    """Detect API response type: 'products' (full data) or 'grid' (product IDs)."""
    if "products" in data or "productsArray" in data:
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


# Only use full CDN URLs (assets/public with -c/-o1/-t suffixes)
ASSETS_PUBLIC_PREFIX = f"{IMAGE_BASE_URL}/assets/public/"


def get_image_urls_from_product(bundle_summary: dict) -> tuple[str | None, list[str]]:
    """
    Extract main image URL and additional image URLs from product.
    Only uses full CDN URLs: static.massimodutti.net/assets/public/.../-c/-o1/-t
    Returns (main_image_url, [additional_urls]).
    """
    main_url = None
    additional_urls = []

    detail = bundle_summary.get("detail", {})
    xmedia = detail.get("xmedia", [])

    # Collect only full assets/public URLs. Prefer -o1 (exact, not o14/o15), fallback -o3
    all_urls: list[str] = []
    o1_url: str | None = None
    o3_url: str | None = None
    for xm in xmedia:
        for item in xm.get("xmediaItems", []):
            for media in item.get("medias", []):
                url = media.get("url")
                if not url or not url.startswith(ASSETS_PUBLIC_PREFIX):
                    continue
                if url in all_urls:
                    continue
                # Exact -o1: -o1/ or -o1. (avoids -o14, -o15)
                if "-o1/" in url or "-o1." in url:
                    o1_url = url
                elif "-o3/" in url or "-o3." in url:
                    o3_url = url
                all_urls.append(url)

    if not all_urls:
        return None, []

    # Prefer -o1 for main, then -o3, then -c, then -t, then first valid
    if o1_url:
        main_url = o1_url
        additional_urls = [u for u in all_urls if u != o1_url]
    elif o3_url:
        main_url = o3_url
        additional_urls = [u for u in all_urls if u != o3_url]
    else:
        for suffix in ("-c", "-t"):
            for u in all_urls:
                if suffix in u:
                    main_url = u
                    additional_urls = [x for x in all_urls if x != u]
                    break
            if main_url:
                break
        if not main_url:
            main_url = all_urls[0]
            additional_urls = all_urls[1:]

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


# Terms suggesting women's products (category/name)
_WOMAN_TERMS = frozenset(
    w.lower()
    for w in (
        "woman", "women", "ladies", "lady", "female",
        "skirt", "skirts", "dress", "dresses", "blouse", "blouses",
        "heels", "pumps", "handbag", "handbags", "bra", "bralette",
        "maternity", "mum", "girl", "girls",
    )
)


def get_gender_from_attributes(
    attributes: list[dict],
    category: str = "",
    title: str = "",
) -> str:
    """Extract gender from MAN/WOMAN attributes, else infer from category/title."""
    for attr in attributes or []:
        attr_type = attr.get("type", "")
        if attr_type == "WOMAN":
            return "woman"
        if attr_type == "MAN":
            return "man"

    # Infer from category and title when no explicit attribute
    combined = f"{category} {title}".lower()
    words = set(re.findall(r"\w+", combined))
    if words & _WOMAN_TERMS:
        return "woman"
    return "man"


# EUR countries - prefer for price lookup; fallback to any country
EUR_COUNTRIES = frozenset(
    c for c, curr in COUNTRY_TO_CURRENCY.items() if curr == "EUR"
)


def collect_prices_eur(
    bundle_summary: dict,
) -> tuple[str | None, str | None]:
    """
    Collect prices in EUR. API: price=current, oldPrice=original when on sale.
    Takes first available price (prefer EUR countries), treats as EUR cents.
    Returns (normal_price_eur, sale_price_eur | None).
    - normal_price: original/regular price in EUR (e.g. 69.95EUR)
    - sale_price: discounted price when on sale (oldPrice exists), else None
    """
    original_cents: int | None = None
    sale_cents: int | None = None
    found_eur = False

    colors = bundle_summary.get("detail", {}).get("colors", [])
    # First pass: try EUR countries
    for color in colors:
        for size in color.get("sizes", []):
            country = (size.get("country") or "").upper()
            if country not in EUR_COUNTRIES:
                continue

            price_str = size.get("price")
            old_price_str = size.get("oldPrice")

            try:
                price_cents = int(price_str) if price_str else None
                old_cents = int(old_price_str) if old_price_str else None

                if price_cents is not None:
                    if old_cents is not None:
                        original_cents = old_cents
                        sale_cents = price_cents
                    else:
                        original_cents = price_cents
                        sale_cents = None
                    found_eur = True
                    break
            except (ValueError, TypeError):
                pass
        if found_eur:
            break

    # Fallback: take first price from any country
    if original_cents is None:
        for color in colors:
            for size in color.get("sizes", []):
                price_str = size.get("price")
                old_price_str = size.get("oldPrice")
                try:
                    price_cents = int(price_str) if price_str else None
                    old_cents = int(old_price_str) if old_price_str else None

                    if price_cents is not None:
                        if old_cents is not None:
                            original_cents = old_cents
                            sale_cents = price_cents
                        else:
                            original_cents = price_cents
                            sale_cents = None
                        break
                except (ValueError, TypeError):
                    pass
            if original_cents is not None:
                break

    if original_cents is None:
        return None, None

    price_str = format_price(original_cents, "EUR")
    sale_str = format_price(sale_cents, "EUR") if sale_cents is not None else None
    return price_str, sale_str


def build_product_url(
    product: dict, bundle_summary: dict, product_id: int, gender: str = "man"
) -> str:
    """Build product page URL: be/en/{slug}-l{ref}?pelement={product_id}."""
    detail = bundle_summary.get("detail", {})
    ref = detail.get("reference") or detail.get("displayReference") or ""
    ref_clean = ref.split("-")[0].replace("/", "").strip() if ref else ""
    if len(ref_clean) < 8:
        ref_clean = ref_clean.zfill(8)

    name = product.get("name") or product.get("nameEn") or "product"
    slug = slugify(name)

    base = f"{BASE_PRODUCT_URL}/{PRODUCT_URL_LOCALE}"
    if ref_clean:
        return f"{base}/{slug}-l{ref_clean}?pelement={product_id}"
    return f"{base}/{slug}?pelement={product_id}"


def parse_products_api(data: dict, gender_override: str | None = None) -> list[dict]:
    """
    Parse products API response into flat product records for DB.
    One record per product (unique by product_url) - bundles share URL.
    gender_override: if provided, forces this gender for all products.
    """
    products_raw = data.get("productsArray", data.get("products", []))
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

        if not main_image:
            continue

        product_id = product.get("id")
        attributes = product.get("attributes", [])
        category = get_categories_from_attributes(attributes)
        title = product.get("name") or product.get("nameEn") or ""
        detected_gender = get_gender_from_attributes(attributes, category=category, title=title)
        final_gender = gender_override if gender_override else detected_gender
        product_url = build_product_url(product, bundle, product_id, final_gender)

        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        description = get_description_from_attributes(attributes)

        price_str, sale_str = collect_prices_eur(bundle)

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
                "gender": final_gender,
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
