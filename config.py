"""Configuration for Massimo Dutti scraper."""
import os
from pathlib import Path

# Path to API URLs file - paste your API URLs here (one per line)
API_URLS_FILE = Path(__file__).parent / "api_urls.txt"

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://yqawmzggcgpeyaaynrjk.supabase.co")
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlxYXdtemdnY2dwZXlhYXlucmprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTAxMDkyNiwiZXhwIjoyMDcwNTg2OTI2fQ.XtLpxausFriraFJeX27ZzsdQsFv3uQKXBBggoz6P4D4",
)

# Product defaults
SOURCE = "scraper"
BRAND = "Massimo Dutti"
GENDER = "man"
SECOND_HAND = False

# Base URLs for Massimo Dutti
BASE_PRODUCT_URL = "https://www.massimodutti.com"
IMAGE_BASE_URL = "https://static.massimodutti.net"

# Currency mapping by country (ISO 4217)
COUNTRY_TO_CURRENCY = {
    "ROMANIA": "RON",
    "SPAIN": "EUR",
    "PORTUGAL": "EUR",
    "FRANCE": "EUR",
    "ITALY": "EUR",
    "GERMANY": "EUR",
    "UNITED KINGDOM": "GBP",
    "UNITED STATES": "USD",
    "MAINLAND CHINA": "CNY",
    "JAPAN": "JPY",
    "POLAND": "PLN",
    "CZECH REPUBLIC": "CZK",
    "MEXICO": "MXN",
    "TURKEY": "TRY",
    "RUSSIA": "RUB",
    "AUSTRIA": "EUR",
    "BELGIUM": "EUR",
    "NETHERLANDS": "EUR",
    "GREECE": "EUR",
    "SWEDEN": "SEK",
    "NORWAY": "NOK",
    "DENMARK": "DKK",
    "SWITZERLAND": "CHF",
    "HUNGARY": "HUF",
    "BULGARIA": "BGN",
    "CROATIA": "EUR",
    "SLOVENIA": "EUR",
    "SLOVAKIA": "EUR",
    "LITHUANIA": "EUR",
    "LATVIA": "EUR",
    "ESTONIA": "EUR",
    "IRELAND": "EUR",
    "FINLAND": "EUR",
}
