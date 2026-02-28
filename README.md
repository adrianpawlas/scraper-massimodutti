# Massimo Dutti Scraper

Scrapes product data from Massimo Dutti API URLs, generates image and text embeddings (768-dim SigLIP), and imports to Supabase.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API URLs**
   - Open `api_urls.txt`
   - Paste your Massimo Dutti API URLs (one per line) — capture from the website's network tab
   - You need at least one **products API** URL (JSON with `"products"` array) for full product data
   - Grid API URLs (JSON with `gridElements` or `productIds`) are optional
   - For local testing, you can use file paths (e.g. `sample1txt`)

3. **Configure Supabase** (optional)
   - Edit `config.py` or set env vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`
   - Default values are pre-configured

## Usage

### Manual run
```bash
python run.py
```

Or with CLI options:
```bash
python -m scraper --skip-embeddings   # Skip embedding generation (faster testing)
python -m scraper --urls "https://..." "https://..."  # Use URLs directly
```

### Automated daily run
GitHub Actions runs the scraper daily at midnight UTC. Setup:

1. **API URLs**: Either commit URLs to `api_urls.txt`, or add secret `API_URLS` (newline-separated URLs)

2. **Supabase** (optional): Default credentials are in `config.py`. To override, add secrets:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`

3. **Manual trigger**: Actions → "Run Massimo Dutti Scraper" → Run workflow

## Output

Products are upserted to the `products` table with:
- `source`: "scraper"
- `brand`: "Massimo Dutti"
- `gender`: "man"
- `image_embedding`: 768-dim from google/siglip-base-patch16-384
- `info_embedding`: 768-dim from SigLIP text encoder
