"""Main Massimo Dutti scraper - fetches APIs, extracts products, embeds, imports to Supabase."""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from supabase import create_client

from config import (
    API_URLS_FILE,
    BRAND,
    GENDER,
    SECOND_HAND,
    SOURCE,
    SUPABASE_ANON_KEY,
    SUPABASE_URL,
)
from embeddings import get_image_embedding, get_text_embedding
from parsers import detect_api_type, parse_products_api, extract_product_ids_from_grid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def load_api_urls(file_path: Path) -> list[str]:
    """Load API URLs from file, one per line, ignoring empty lines and comments."""
    if not file_path.exists():
        return []

    urls = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def fetch_json(url_or_path: str) -> Optional[dict]:
    """Fetch JSON from URL or load from local file path."""
    path = Path(url_or_path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to load file %s: %s", path, e)
            return None

    try:
        resp = requests.get(
            url_or_path,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Failed to fetch %s: %s", url_or_path[:80], e)
        return None


def build_info_text(record: dict) -> str:
    """Build concatenated text for info_embedding."""
    parts = [
        record.get("title", ""),
        record.get("description", ""),
        record.get("category", ""),
        record.get("gender", ""),
        record.get("price", ""),
        record.get("sale", ""),
    ]
    metadata = record.get("metadata")
    if metadata:
        try:
            m = json.loads(metadata)
            if isinstance(m, dict):
                parts.append(json.dumps(m, default=str))
        except (json.JSONDecodeError, TypeError):
            parts.append(str(metadata))
    return " ".join(str(p) for p in parts if p).strip()


def record_to_db_row(record: dict, image_embedding: list[float] | None, info_embedding: list[float] | None) -> dict:
    """Convert parsed record to Supabase products table row."""
    row = {
        "id": record["id"],
        "source": SOURCE,
        "product_url": record["product_url"],
        "image_url": record["image_url"],
        "brand": BRAND,
        "title": record["title"],
        "description": record.get("description"),
        "category": record.get("category"),
        "gender": GENDER,
        "metadata": record.get("metadata"),
        "size": None,
        "second_hand": SECOND_HAND,
        "country": None,
        "tags": None,
        "other": None,
        "price": record.get("price"),
        "sale": record.get("sale"),
        "additional_images": record.get("additional_images"),
        "affiliate_url": None,
        "compressed_image_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if image_embedding:
        row["image_embedding"] = image_embedding
    if info_embedding:
        row["info_embedding"] = info_embedding

    return row


def run_scraper(api_urls: Optional[list[str]] = None, skip_embeddings: bool = False) -> dict:
    """
    Run the full scrape: fetch APIs, parse products, generate embeddings, import to Supabase.
    Returns stats dict with counts.
    """
    urls = api_urls or load_api_urls(API_URLS_FILE)
    if not urls:
        logger.warning("No API URLs found. Paste URLs in %s (one per line)", API_URLS_FILE)
        return {"products_parsed": 0, "products_imported": 0, "errors": 0}

    all_records: dict[str, dict] = {}  # id -> record (dedupe by id)

    for url in urls:
        logger.info("Fetching %s", url[:90])
        data = fetch_json(url)
        if not data:
            continue

        try:
            api_type = detect_api_type(data)
        except ValueError as e:
            logger.warning("Skipping URL (unknown format): %s", e)
            continue

        if api_type == "products":
            records = parse_products_api(data)
            for r in records:
                all_records[r["id"]] = r
            logger.info("Parsed %d products from products API", len(records))
        elif api_type == "grid":
            ids = extract_product_ids_from_grid(data)
            logger.info("Found %d product IDs in grid API (need products API for full data)", len(ids))

    if not all_records:
        logger.warning("No product records to import. Ensure at least one 'products' type API URL.")
        return {"products_parsed": 0, "products_imported": 0, "errors": 0}

    supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    imported = 0
    errors = 0

    for i, (pid, record) in enumerate(all_records.items(), 1):
        logger.info("Processing %d/%d: %s", i, len(all_records), record["title"][:50])

        image_embedding = None
        info_embedding = None

        if not skip_embeddings:
            image_embedding = get_image_embedding(record["image_url"])
            if not image_embedding:
                logger.warning("No image embedding for %s", pid)

            info_text = build_info_text(record)
            info_embedding = get_text_embedding(info_text)
            if not info_embedding:
                logger.warning("No info embedding for %s", pid)

        row = record_to_db_row(record, image_embedding, info_embedding)

        try:
            supabase.table("products").upsert(row, on_conflict="id").execute()
            imported += 1
        except Exception as e:
            logger.error("Failed to upsert %s: %s", pid, e)
            errors += 1

    logger.info("Done. Imported %d, errors %d", imported, errors)
    return {"products_parsed": len(all_records), "products_imported": imported, "errors": errors}


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Massimo Dutti scraper")
    parser.add_argument("--urls", nargs="*", help="API URLs (overrides api_urls.txt)")
    parser.add_argument("--skip-embeddings", action="store_true", help="Skip embedding generation (faster)")
    args = parser.parse_args()

    run_scraper(api_urls=args.urls, skip_embeddings=args.skip_embeddings)


if __name__ == "__main__":
    main()
