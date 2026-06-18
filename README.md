# Royalty Exchange Data Collection & Analysis Pipeline
This is the code guide to extract past auction on royaltyexchange.com, and analyze their code.

> **Automated scraping and structured data extraction from [Royalty Exchange](https://auctions.royaltyexchange.com/) — a secondary marketplace for music royalty assets.**
>
> The pipeline crawls auction pages, handles two distinct page formats (new numeric-ID pages and old slug-based pages), extracts financial and categorical data through a multi-stage analysis process, and merges everything into a unified CSV dataset for quantitative analysis and asset pricing research.

---

# English Documentation

## Overview

Royalty Exchange is a marketplace where investors buy and sell rights to music royalty income streams. The platform has undergone a redesign, resulting in **two coexisting page formats** with completely different DOM structures and data sources:

| Format | URL Pattern | Identifier | Data Sources |
|--------|-------------|-----------|--------------|
| **New** | `/orderbook/asset-detail/{id}/` | Numeric ID (e.g., `5986`) | Rendered HTML + REST API JSON |
| **Old** | `/auctions/{slug}/` | Name slug (e.g., `tarquin-collection`) | Rendered HTML (login required) |

The project implements **two parallel processing pipelines** that ultimately converge into a standardized 42-field schema, output as a single CSV file.

### Pipeline Architecture

```
URL_SCRAPE.py                         # Fetch all URLs from sitemap
      │
      ▼
  urls_lastmod.csv                    # URL inventory with timestamps
      │
      ▼
  main.py                             # Read CSV → classify URL → dispatch
      │
      ├── "new" format ───────────────────────────── "old" format
      │                                                    │
  new_1.py (Playwright HTML)                      old_1.py (Login + Playwright HTML)
  new_2.py (REST API JSON)                               │
      │                                                    │
      ├── new_analysis_1.py  (Royalties table)     old_analysis_1.py  (Rights table)
      ├── new_analysis_2.py  (42-field extraction)  old_analysis_2.py  (Overview + auction history)
      ├── new_analysis_3.py  (Merge & fill rows)    old_analysis_3.py  (Merge & fill rows)
      │                                              old_analysis_4.py  (slug → numeric ID)
      │                                              old_analysis_5.py  (Add buy-it-now items)
      │                                                    │
      └──────────── final_output.py ──────────────────────┘
                              │
                              ▼
                       final_output.csv              # Unified dataset
```

---

## Part 1 — URL Generation

**File**: `python_codes/URL_SCRAPE.py`

This module fetches the XML sitemap and extracts all auction page URLs with their last-modified timestamps.

### How It Works

The Royalty Exchange sitemap is a standard XML document at:
```
https://auctions.royaltyexchange.com/sitemap.xml
```

The code uses **Playwright** (a headless browser automation library) to fetch the XML — this ensures the request appears as a real browser visit, avoiding simple bot blocks.

```python
async def fetch_and_save_sitemap(sitemap_url, filename="urls_lastmod.csv"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...'
        )
        page = await context.new_page()
        response = await page.goto(sitemap_url, wait_until="domcontentloaded")
```

Once the XML is fetched, **BeautifulSoup** with the `xml` parser extracts each `<url>` node. A crucial filter is applied — **only URLs that have a `<lastmod>` tag** are kept, ensuring we only track pages with actual modification records.

```python
for url_node in soup.find_all('url'):
    lastmod_node = url_node.find('lastmod')
    if lastmod_node:   # Only keep URLs with lastmod
        loc = url_node.find('loc').text
        lastmod = lastmod_node.text
        data_to_save.append([loc, lastmod])
```

### Output

The result is `urls_lastmod.csv`, a two-column CSV:
```
URL,Last_Modified
https://auctions.royaltyexchange.com/auctions/judge-jury-music-catalog/,2012-09-13
https://auctions.royaltyexchange.com/auctions/tarquin-collection/,2013-03-21
...
```

This CSV serves as the **input manifest** for the main orchestrator.

---

## Part 2 — URL Dispatching & Orchestration

**File**: `python_codes/main.py`

`main.py` is the central scheduler. It reads the URL list, classifies each URL into "new" or "old" format, dispatches scraping tasks, and tracks progress for resumability.

### URL Classification

The `classify_url()` function determines the format by inspecting the URL path:

```python
def classify_url(url: str) -> tuple:
    path = urlparse(url).path
    if re.search(r'/orderbook/(asset-detail|api/listings)/\d+/', path):
        # New format: numeric ID
        match = re.search(r'/(\d+)/?$', path)
        return ("new", match.group(1)) if match else ("old", "")
    else:
        # Old format: name slug
        slug = path.rstrip('/').split('/')[-1]
        return ("old", slug)
```

**Key insight**: The new format pages contain a numeric asset ID in the URL (e.g., `.../asset-detail/5986/`), while old format pages use a human-readable slug (e.g., `.../auctions/tarquin-collection/`). This classification determines the entire downstream processing path.

### Dispatch Logic

```python
if url_type == "new":
    from new.new_1 import scrape_asset_page
    result = await scrape_asset_page(int(id_or_slug), RESOURCES_NEW)
    from new.new_2 import fetch_listing_api
    result2 = fetch_listing_api(int(id_or_slug), RESOURCES_NEW)
else:
    from old.old_1 import scrape_auction_page
    result = await scrape_auction_page(url, RESOURCES_OLD, id_or_slug)
```

For **new** format pages, two data sources are fetched in sequence:
1. The **rendered HTML** (containing the Royalties table rendered by React)
2. The **REST API JSON** (containing structured valuation data)

For **old** format pages, only the rendered HTML is fetched (the old pages don't have a public API), but this requires **authentication**.

### Resumability via Progress Tracking

The orchestrator maintains a `progress.json` file that records completed and failed URLs:

```json
{
  "completed": ["https://..."],
  "failed": {"https://...": "error message"}
}
```

Before processing any URL, the code checks if it already exists in `completed`:

```python
for i, row in enumerate(data_rows, 1):
    url = row[0].strip()
    if url in progress["completed"]:
        continue    # Skip already-processed URLs
```

This design allows the pipeline to be **interrupted and resumed** at any point without re-scraping pages.

---

## Part 3 — New Format Data Analysis

### 3.1 Page Scraping (`new/new_1.py`)

**`scrape_asset_page(asset_id, output_dir)`** uses Playwright to render the dynamic React page.

```python
await page.goto(url, wait_until="domcontentloaded", timeout=60000)
# Critical wait: ensure the Royalties section has been rendered
await page.wait_for_selector('div[name="Royalties"]', state='attached', timeout=30000)
html_content = await page.content()
```

**Why this matters**: The page is a React single-page application. The Royalties data is fetched asynchronously from backend APIs and rendered client-side. Without waiting for `div[name="Royalties"]`, the HTML would be incomplete — missing the most important financial data.

The raw HTML is prettified with BeautifulSoup and saved as `{asset_id}.html`.

### 3.2 API Data Fetching (`new/new_2.py`)

**`fetch_listing_api(asset_id, output_dir)`** calls the internal REST API that powers the page.

```python
url = f"https://auctions.royaltyexchange.com/orderbook/api/listings/{asset_id}/"
params = {
    "include[]": [
        "asset.*",
        "valuation_description.*",
        "offers.*"
    ]
}
response = requests.get(url, params=params, headers={"Accept": "application/json"})
data = response.json()
```

The API response includes everything needed for financial analysis:

```json
{
  "asset": { "name": "...", "sale_history": [...] },
  "valuation": {
    "ltm": 2781.0,
    "lifetime_amount": 15000.0,
    "three_years_average": 5200.0,
    "dollar_age": 8.5,
    "top_income_types": [
      {"name": "STREAMING MECHANICAL", "earnings": 1200.0},
      ...
    ]
  },
  "offers": [{"amount": "11750.00", "state": "filled"}, ...],
  "term": "10 years"
}
```

### 3.3 Analysis Step 1 — Royalties Table Extraction (`new_analysis_1.py`)

This module parses the HTML's `div[name="Royalties"]` section into a structured JSON format. The key challenge is preserving the **highlight semantics** — cells marked with `cell-bold` CSS class indicate that a particular royalty type or distributor is "included" in the asset.

```python
def extract_royalties(html_file_path):
    soup = BeautifulSoup(f.read(), 'html.parser')
    section = soup.find('div', {'name': 'Royalties'})
    # Parse table, tracking which cells are highlighted
    for row in table.find_all('tr'):
        for cell in row.find_all('td'):
            cell_bold = 'cell-bold' in cell.get('class', [])
            # ...
```

The output structure for each cell includes both the raw text and an explicit `highlighted` array:

```json
{
  "table": [
    [{"text": "Type", "highlighted": null},
     {"text": "Musical Composition", "highlighted": ["Musical Composition"]},
     {"text": "Sound Recording", "highlighted": null}],
    ...
  ],
  "ascap": { "description": "...", "links": [...] }
}
```

### 3.4 Analysis Step 2 — 42-Field Factor Extraction (`new_analysis_2.py`)

This is the analytical core of the pipeline. It reads a **Factor List** from `Factor List.xlsx` (41 rows of factor definitions) and extracts each factor value from the API JSON data.

#### Factor List Structure

The XLSX file's "New" sheet defines each factor with:
- `df_name` — column name in the output dataframe
- `json_key` — corresponding key in the API JSON (if direct mapping exists)
- `measure` — description of how the factor is measured
- `notice` — special handling instructions

```python
def read_factor_list(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb['New']
    factors = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        factors.append({
            "df_name": str(row[0]).strip(),
            "json_key": str(row[1]).strip() if row[1] else None,
            "measure": str(row[2]).strip() if row[2] else None,
            "notice": str(row[3]).strip() if row[3] else None,
        })
    return factors
```

#### Extraction Logic by Factor

The `extract_factor()` function uses a **routing pattern** — it dispatches extraction logic based on the factor's `df_name`:

```python
def extract_factor(data, factor):
    df_name = factor["df_name"]

    if df_name == "Sale Price":
        offers = data.get("offers", []) or []
        for offer in offers:
            if offer.get("state") == "filled":
                return float(offer["amount"])
        return float(offers[0]["amount"])  # fallback

    elif df_name == "TracksIncluded":
        track_list = data.get("valuation", {}).get("track_list", []) or []
        return len(track_list)

    elif df_name == "HighestBidLowestBid":
        offers = data.get("offers", []) or []
        amounts = [float(o["amount"]) for o in offers if o.get("amount")]
        return max(amounts) - min(amounts) if len(amounts) >= 2 else 0.0

    elif df_name.startswith("Income_Type_"):
        # Normalize name and match against top_income_types[]
        target_name = normalize_income_type_name(df_name)
        for entry in data.get("valuation", {}).get("top_income_types", []):
            if normalize_income_type_name(entry["name"]) == target_name:
                return entry.get("earnings")
        return None
    # ... more factors
```

**The 27 effective factors** (some rows in the factor list are marked for special handling or set to None):

| Factor | Source | Logic |
|--------|--------|-------|
| Sale Price | `offers[]` | First filled offer amount, fallback to first offer |
| TermRemaining | `term` | Direct string read (e.g., "10 years") |
| TracksIncluded | `valuation.track_list` | Count of tracks |
| NumberOfBids | `offers[]` | Length of offers array |
| HighestBidLowestBid | `offers[]` | Max amount − min amount |
| HasLastTransaction | `asset.sale_history` | 1 if exists, 0 otherwise |
| Income_Type_* (14 types) | `valuation.top_income_types[]` | Match by normalized name → earnings |
| Last12Months | `valuation.ltm` | Direct float |
| EarningsSinceStart | `valuation.lifetime_amount` | Direct float |
| 3YearAverage | `valuation.three_years_average` | Direct float |
| DollarAge | `valuation.dollar_age` | Direct float |

#### Income Type Name Normalization

The `normalize_income_type_name()` function handles inconsistencies between the Factor List names and the actual API response names:

```python
def normalize_income_type_name(raw_name):
    name = raw_name.upper().strip()
    if name.startswith("INCOME_TYPE_"):
        name = name[len("INCOME_TYPE_"):].strip()
    # Fix known typos in the Factor List
    name = name.replace("STREAMINGP ERFORMANCE", "STREAMING PERFORMANCE")
    name = name.replace("STREAMINGS YNCHRONIZATION", "STREAMING SYNCHRONIZATION")
    name = name.replace("SOUNDRECORDING", "SOUND RECORDING")
    name = re.sub(r'\s+', ' ', name)
    return name
```

### 3.5 Analysis Step 3 — Merge & Fill (`new_analysis_3.py`)

The second analysis step leaves rows 28–41 as `null` because those fields require information from the HTML's Royalties table (not available in the API JSON). Step 3 fills them by cross-referencing Step 1's table data.

```python
def fill_rows_28_to_41(step1_data, step2_data, file_exists_in_both):
    result = dict(step2_data)

    # Row 28: Does a copyrights table exist at all?
    result["CopyrightsIncluded_Yes"] = 1 if file_exists_in_both else 0

    # Rows 29–30: Royalty type detection via table header highlights
    row0 = table[0]
    h0_1 = row0[1].get("highlighted")  # Musical Composition column
    h0_2 = row0[2].get("highlighted")  # Sound Recording column
    result["Type_xroyaltyType_MusicalCompositionSoundRecording"] = 1 if (h0_1 and h0_2) else 0
    result["Type_xroyaltyType_SoundRecording"] = 1 if (not h0_1 and h0_2) else 0

    # Rows 31–41: Keyword matching against highlighted cells
    # Distributors → search for "BMI", "ASCAP", "Universal Music Publishing Group", etc.
    # Sources → search for "CD Sales", "TV/Film", "Satellite Radio", "Internet Streaming"
    # Rights → search for "Public Performance", "Sync"
    for cell in table_rows:
        if keyword_in_highlighted(cell, "BMI"):
            result["Distributor_bmi"] = 1
    # ...
```

The `keyword_in_highlighted()` helper performs case-insensitive substring matching against the `highlighted` array of each cell:

```python
def keyword_in_highlighted(cell, keyword):
    highlighted = cell.get("highlighted")
    if highlighted is None:
        return False
    keyword_lower = keyword.lower()
    for item in highlighted:
        if keyword_lower in item.lower():
            return True
    return False
```

---

## Part 4 — Old Format Data Analysis

Old format pages (`/auctions/{slug}/`) require **authentication** and have a completely different HTML structure. The pipeline handles this with a separate processing path.

### 4.1 Login & Page Scraping (`old/old_1.py`)

**`scrape_auction_page(url, output_dir, slug)`** uses Playwright to:

1. **Log in** to the platform with credentials
2. **Navigate** to the target auction page
3. **Wait** for the React-rendered metadata section
4. **Save** the prettified HTML

```python
async def login(context) -> bool:
    page = await context.new_page()
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)  # Wait for React form to mount

    # Fill credentials (Material-UI TextFields)
    await page.fill("#sign-in-email", EMAIL, timeout=5000)
    await page.fill("#sign-in-password", PASSWORD, timeout=5000)
    await page.click('button[type="submit"]', timeout=5000)

    # Wait for redirect away from sign-in page
    await page.wait_for_function(
        "() => !window.location.href.includes('/auth/sign-in')",
        timeout=30000,
    )
    # Verify login success
    if "/auth/sign-in" in page.url:
        return False
    return True
```

After login, the scraper navigates to the auction URL and waits for the critical `#id_tabbed_metadata` element — the container holding all auction data:

```python
await page.goto(url, wait_until="domcontentloaded", timeout=60000)
target_selector = "#id_tabbed_metadata"
await page.wait_for_selector(target_selector, timeout=20000)
```

### 4.2 Analysis Step 1 — Rights Table Extraction (`old_analysis_1.py`)

This module extracts the "What rights are included?" table from old-format HTML. The output format is **compatible** with `new_analysis_1.py`, enabling shared logic downstream.

The page structure is quite different from the new format:

```python
# Old format: find heading first, then locate the table after it
heading = soup.find(re.compile(r'h[1-4]'), string=re.compile(
    r'What rights are included', re.IGNORECASE))
table = heading.find_next('table', class_='crdt')

# New format: direct ID-based lookup
section = soup.find('div', {'name': 'Royalties'})
```

The table has 4 content rows, each with a label column and two data columns (MC = Musical Composition, SR = Sound Recording):

```python
for row_idx, row in enumerate(rows):
    cells = row.find_all('td', recursive=False)
    # Map by position:
    if row_idx == 0:  # Copyrights Included?
    elif row_idx == 1:  # Royalty Types (may contain nested <table>)
    elif row_idx == 2:  # Sources
    elif row_idx == 3:  # Distributors
```

**Nested table handling**: The Rights/Royalty Types cell may contain an inner `<table class="crdt inner">` for items. The code recursively processes this:

```python
inner_table = cell.find('table', class_='crdt inner')
if inner_table:
    all_items = []
    included_items = []
    for td in inner_table.find_all('td'):
        item_text = td.get_text(strip=True)
        if item_text:
            all_items.append(item_text)
            if 'not-included' not in td.get('class', []):
                included_items.append(item_text)
    text = ' | '.join(all_items)
    highlighted = included_items if included_items else None
```

### 4.3 Analysis Step 2 — Overview & Auction History (`old_analysis_2.py`)

This module extracts structured data from the old-format HTML's **Overview table** and **Auction History** section, then assembles them into the same 42-field format as the new pipeline.

#### Overview Table Extraction

The code scans `table.es-overview-table` rows by label text (case-insensitive):

```python
def extract_overview(soup):
    table = soup.find('table', class_='es-overview-table')
    for row in rows:
        label = cells[0].get_text(strip=True).lower()
        value_text = cells[1].get_text(separator=' ', strip=True)

        if 'closing price' in label:
            result["SalePrice"] = parse_currency(value_text)
        elif 'investment term' in label or label.startswith('term:'):
            result["TermRemaining"] = value_text
        elif 'last 12 months' in label or 'past 4 quarter' in label:
            result["Last12Months"] = parse_currency(value_text)
        elif 'dollar age' in label:
            result["DollarAge"] = parse_dollar_age(value_text)
        elif 'track' in label:
            result["TracksIncluded"] = parse_number(value_text)
```

Helper functions handle various text formats:

```python
def parse_currency(text):
    """Strip $ , and parse as float."""
    cleaned = re.sub(r'[$,]', '', text.strip())
    return float(cleaned)

def parse_dollar_age(text):
    """Extract float from '14.02 Years'."""
    m = re.search(r'([\d.]+)\s*Years?', text, re.IGNORECASE)
    return float(m.group(1)) if m else None
```

#### Auction History Extraction

The bids are in an `<ol type="1">` after an `<h3 id="bids_list_header">`:

```python
def extract_auction_history(soup):
    header = soup.find('h3', id='bids_list_header')
    ol = header.find_next_sibling('ol', type="1")
    bid_items = ol.find_all('li', recursive=False)
    result["NumberOfBids"] = len(bid_items)

    amounts = []
    for li in bid_items:
        text = li.get_text(separator=' ', strip=True)
        m = re.search(r'\$([\d,]+(?:\.\d{1,2})?)', text)
        if m:
            amounts.append(float(m.group(1).replace(',', '')))

    result["HighestBidLowestBid"] = max(amounts) - min(amounts) if len(amounts) >= 2 else 0.0
```

#### Output Assembly

The `build_output()` function assembles all extracted data into the unified 42-field schema. Since old-format pages lack certain data (e.g., income type breakdowns, earnings history), those fields are set to `null` and filled in later steps:

```python
def build_output(overview, auction):
    obj = {}
    obj["Sale Price"] = overview["SalePrice"]
    obj["NumberOfBids"] = auction["NumberOfBids"]
    obj["HighestBidLowestBid"] = auction["HighestBidLowestBid"]
    # ... 6 fields from overview, 2 from auction

    # Income type fields: all null (not available in old format)
    for it in income_types:
        obj[f"Income_Type_{it}"] = None

    # Rows 28-41: all null (filled in step 3 from rights table)
    for field in fields_rows_28_to_41:
        obj[field] = None
    return obj
```

### 4.4 Analysis Step 3 — Merge & Fill (`old_analysis_3.py`)

Functionally identical to `new_analysis_3.py`, but with a slightly different approach for type detection. Instead of only looking at table header highlights, it checks whether **content rows have any highlighted cells** in each column:

```python
def column_has_any_highlight(table, col_idx):
    """Check if any content row in the given column has highlighted content."""
    for row_idx in range(1, len(table)):
        cell = row[col_idx] if len(row) > col_idx else None
        if cell and cell.get("highlighted") is not None and len(cell["highlighted"]) > 0:
            return True
    return False

mc_highlighted = column_has_any_highlight(table, 1)  # Column 1 = MC
sr_highlighted = column_has_any_highlight(table, 2)  # Column 2 = SR

result["Type_xroyaltyType_MusicalCompositionSoundRecording"] = 1 if (mc_highlighted and sr_highlighted) else 0
result["Type_xroyaltyType_SoundRecording"] = 1 if (not mc_highlighted and sr_highlighted) else 0
```

### 4.5 Analysis Step 4 — Slug to Numeric ID Mapping (`old_analysis_4.py`)

Old format files use name-based filenames (e.g., `tarquin-collection.json`), while new format files use numeric IDs (e.g., `2783.json`). For the final merge to work, all files must have numeric names.

This step extracts the numeric `auctionId` from the HTML's `dataLayer` JavaScript variable:

```python
def get_auction_id_from_html(html_file_path):
    with open(html_file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    match = re.search(r'auctionId["\']?\s*:\s*["\']?(\d+)', content)
    return match.group(1) if match else None
```

Files are then renamed and copied: `{slug}.json` → `{auctionId}.json`.

### 4.6 Analysis Step 5 — Buy-It-Now Manual Mapping (`old_analysis_5.py`)

Six "Buy It Now" (fixed-price) pages do not have an `auctionId` in their HTML. These are handled via a **hardcoded mapping table**:

```python
BUY_IT_NOW_MAP = {
    "buy-it-now-brand-new-hip-hop-releases": 11,
    "buy-it-now-indie-electropop-lolawolf": 20,
    "buy-it-now-international-k-pop-catalog": 17,
    "buy-it-now-platinum-hit-from-zendaya-replay-more": 2,
    "buy-it-now-production-music-in-emmy-winning-series": 7,
    "buy-it-now-rb-pop-catalog-featuring-trey-songz": 1,
}
```

The step merges 809 auto-mapped files from step 4 with 6 manually mapped files, producing a complete set in step 5.

---

## Part 5 — Final Output Generation

**File**: `python_codes/final_output.py`

### `merge_folders_and_generate_csv()`

This function merges the two pipeline outputs into a single CSV file.

**Step 1 — Folder merge**: Copies all JSON files from `analysis/new_step_3` and `analysis/old_step_5` into `analysis/final/`, handling filename conflicts with `_copy` suffixes.

**Step 2 — Schema validation**: Each JSON file is checked for field consistency against the first file's schema:

```python
if standard_keys is None:
    standard_keys = set(data.keys())  # Use first file as schema reference

current_keys = set(data.keys())
if current_keys != standard_keys:
    missing = standard_keys - current_keys
    extra = current_keys - standard_keys
    print(f"⚠ {json_file.name} schema mismatch: missing {missing}, extra {extra}")
```

**Step 3 — CSV generation**: Files are sorted numerically by filename, and the CSV is written with a fixed column order (filename first, then all data fields):

```python
all_data.sort(key=lambda x: int(Path(x['filename']).stem))

# Build column order
all_keys = ['filename']
for key in field_order:
    if key not in all_keys:
        all_keys.append(key)

with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=all_keys)
    writer.writeheader()
    writer.writerows(all_data)
```

### Final CSV Schema

| Column | Type | Description |
|--------|------|-------------|
| `filename` | str | Asset ID (e.g., `2783.json`) |
| `Sale Price` | float | Closing auction price |
| `TermRemaining` | str | Remaining copyright term (text) |
| `TracksIncluded` | int | Number of tracks in the asset |
| `Fees` | str | Fee description |
| `NumberOfBids` | int | Total bids placed |
| `HighestBidLowestBid` | float | Bid spread (max − min) |
| `HasLastTransaction` | int | 1 if prior sale exists |
| `Income_Type_STREAMING MECHANICAL` | float | 12-month earnings by income type |
| `Income_Type_PERFORMANCE` | float | ... (14 income type columns) |
| ... | ... | |
| `Last12Months` | float | Total trailing 12-month earnings |
| `EarningsSinceStart` | float | Lifetime cumulative earnings |
| `3YearAverage` | float | 3-year average earnings |
| `DollarAge` | float | Weighted dollar age (years) |
| `CopyrightsIncluded_Yes` | int | 1 if copyrights table present |
| `Type_xroyaltyType_MusicalCompositionSoundRecording` | int | 1 if both MC & SR included |
| `Type_xroyaltyType_SoundRecording` | int | 1 if SR only |
| `Rights_Public_Performance` | int | 1 if Public Performance included |
| `Rights_Sync` | int | 1 if Sync rights included |
| `Distributor_universal` | int | 1 if Universal is distributor |
| `Distributor_bmi` | int | 1 if BMI is distributor |
| `Distributor_ascap` | int | 1 if ASCAP is distributor |
| `Distributor_sony` | int | 1 if Sony is distributor |
| `Distributor_warner` | int | 1 if Warner is distributor |
| `Source_cd_sales` | int | 1 if CD sales income source |
| `Source tv_film` | int | 1 if TV/Film income source |
| `Source_ satellite_radio` | int | 1 if Satellite Radio income source |
| `Source_internet_streaming` | int | 1 if Internet Streaming income source |

---

## Key Design Decisions & Technical Highlights

### 1. Dual-Pipeline Architecture

The new and old page formats differ fundamentally in DOM structure, data sources, and access requirements. Rather than building one fragile scraper that handles both, the project implements **independent pipelines** per format, converging only at the final output stage through a shared 42-field schema. This isolation ensures that changes to one format don't break the other.

### 2. Playwright for Dynamic Content

Royalty Exchange is a React SPA — critical data is fetched asynchronously and rendered client-side. Simple HTTP requests (`requests.get()`) would return an empty shell. Playwright (headless Chromium) is used to:
- Execute JavaScript and wait for specific rendered elements
- Handle authentication flows (login forms, cookie banners)
- Capture the fully rendered DOM

The two key wait strategies are:
```python
# New format: wait for Royalties section
await page.wait_for_selector('div[name="Royalties"]', state='attached', timeout=30000)

# Old format: wait for metadata container
await page.wait_for_selector('#id_tabbed_metadata', timeout=20000)
```

### 3. Highlight Semantics as Data

The page tables use CSS classes (`cell-bold`, `not-included`) to indicate which items are included in or excluded from an asset. This is **not just styling** — it's the core signal distinguishing asset composition. The analysis pipeline preserves this semantic by:

1. Recording `highlighted` arrays for each cell
2. Mapping highlight patterns to binary (1/0) factor values
3. Using keyword matching against highlighted text for distributor, source, and rights detection

### 4. Factor-Driven Extraction

The `Factor List.xlsx` file defines **what to extract**, while the code defines **how to extract it**. This separation allows:
- New factors to be added via Excel configuration
- Extraction logic to be developed independently per factor
- Consistent naming across the dataset

### 5. Progressive Data Enrichment

Rows 28–41 cannot be extracted from the API JSON alone (they need the HTML table). The three-step analysis sequence (extract → parse → merge) ensures each step builds on the previous one's output, avoiding circular dependencies and keeping each module focused.

### 6. Resumable Scraping

The `progress.json` mechanism allows the scraping pipeline to be stopped and restarted arbitrarily. This is essential for large-scale data collection where network errors, rate limiting, or timeouts are common.

### 7. Unified ID System

The final dataset uses **numeric IDs** throughout. Old-format slug names are mapped to numeric IDs via the `auctionId` embedded in the HTML (or via manual mapping for buy-it-now items). This ensures consistent keying across all assets.

---

<br>
<hr>
<br>

# 中文文档 (Chinese Documentation)

## 项目概述

本项目自动化抓取 [Royalty Exchange](https://auctions.royaltyexchange.com/) 平台上的音乐版权拍卖数据，将结构化和非结构化的网页信息转化为标准化的结构化数据集，最终以 CSV 格式输出，供后续金融分析、资产定价模型和量化研究使用。

Royalty Exchange 是音乐版权二级市场交易平台，允许投资者买卖音乐版税收益权。网站存在**两种页面格式**——较新的数字 ID 格式和较旧的名称为主格式，两套页面的 DOM 结构与数据来源完全不同，因此本项目的处理流程也相应分轨。

| 格式 | URL 模式 | 标识符 | 数据来源 |
|------|----------|--------|----------|
| **新格式** | `/orderbook/asset-detail/{id}/` | 数字 ID（如 `5986`） | 渲染后的 HTML + REST API JSON |
| **旧格式** | `/auctions/{slug}/` | 名称 slug（如 `tarquin-collection`） | 渲染后的 HTML（需要登录） |

### 管线架构图

```
URL_SCRAPE.py                         # 从 sitemap 获取所有 URL
      │
      ▼
  urls_lastmod.csv                    # URL 清单及时间戳
      │
      ▼
  main.py                             # 读取 CSV → 分类 URL → 分发任务
      │
      ├── "new" 格式 ───────────────────────── "old" 格式
      │                                              │
  new_1.py (Playwright HTML)                 old_1.py (登录 + Playwright HTML)
  new_2.py (REST API JSON)                         │
      │                                              │
      ├── new_analysis_1.py  (Royalties 表格)      old_analysis_1.py  (Rights 表格)
      ├── new_analysis_2.py  (42 字段因子提取)      old_analysis_2.py  (Overview + 拍卖历史)
      ├── new_analysis_3.py  (合并补全 rows)        old_analysis_3.py  (合并补全 rows)
      │                                              old_analysis_4.py  (slug → 数字 ID)
      │                                              old_analysis_5.py  (补充 buy-it-now 项)
      │                                              │
      └──────────── final_output.py ────────────────┘
                              │
                              ▼
                       final_output.csv              # 统一数据集
```

---

## 第一部分 — URL 生成

**文件**: `python_codes/URL_SCRAPE.py`

从 Royalty Exchange 的 XML 站点地图中提取所有拍卖页面的 URL 及其最后修改时间。

### 实现细节

网站提供标准 XML Sitemap 位于 `https://auctions.royaltyexchange.com/sitemap.xml`。代码使用 Playwright 模拟真实浏览器访问（设置合理的 User-Agent），避免被简单的反爬机制拦截。

```python
async def fetch_and_save_sitemap(sitemap_url, filename="urls_lastmod.csv"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 设置真实的浏览器 User-Agent
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...'
        )
        page = await context.new_page()
        response = await page.goto(sitemap_url, wait_until="domcontentloaded")
```

获取 XML 后使用 BeautifulSoup 的 `xml` 解析器提取所有 `<url>` 节点。**关键过滤**：只保留包含 `<lastmod>` 标签的 URL，确保只收录有实际更新记录的页面。

```python
for url_node in soup.find_all('url'):
    lastmod_node = url_node.find('lastmod')
    if lastmod_node:   # 只保留有 lastmod 的 URL
        loc = url_node.find('loc').text
        lastmod = lastmod_node.text
        data_to_save.append([loc, lastmod])
```

### 输出

**`urls_lastmod.csv`** — 两列 CSV 文件，包含所有页面 URL 和最后修改时间，作为后续流程的输入清单。

---

## 第二部分 — URL 分类与任务调度

**文件**: `python_codes/main.py`

主调度器读取 URL 列表，分类每个 URL，分发抓取任务，并记录进度以实现断点续抓。

### URL 分类机制

`classify_url()` 函数通过 URL 路径判断格式类型：

```python
def classify_url(url: str) -> tuple:
    path = urlparse(url).path
    if re.search(r'/orderbook/(asset-detail|api/listings)/\d+/', path):
        # 新格式：路径包含数字 ID
        match = re.search(r'/(\d+)/?$', path)
        return ("new", match.group(1)) if match else ("old", "")
    else:
        # 旧格式：路径以名称 slug 结尾
        slug = path.rstrip('/').split('/')[-1]
        return ("old", slug)
```

**核心区别**：新格式页面 URL 中包含数字资产 ID（如 `/asset-detail/5986/`），而旧格式使用人类可读的名称（如 `/auctions/tarquin-collection/`）。这个分类决定了后续所有的处理路径。

### 分发逻辑

```python
if url_type == "new":
    from new.new_1 import scrape_asset_page
    result = await scrape_asset_page(int(id_or_slug), RESOURCES_NEW)
    from new.new_2 import fetch_listing_api
    result2 = fetch_listing_api(int(id_or_slug), RESOURCES_NEW)
else:
    from old.old_1 import scrape_auction_page
    result = await scrape_auction_page(url, RESOURCES_OLD, id_or_slug)
```

新格式页面抓取**两个数据源**：
1. 渲染后的 HTML（包含 React 渲染的 Royalties 表格）
2. REST API JSON（包含结构化的估值数据）

旧格式页面只抓取渲染后的 HTML（旧页面没有公开 API），但需要**身份认证**。

### 断点续抓

每次处理完一个 URL 都会立即更新 `progress.json`：

```python
progress["completed"].append(url)
save_progress(progress)   # 实时保存
```

再次运行时自动跳过已完成的 URL，支持随时中断和恢复。

---

## 第三部分 — 新格式数据分析

### 3.1 页面抓取 (`new/new_1.py`)

**`scrape_asset_page(asset_id, output_dir)`** 使用 Playwright 渲染 React 动态页面。

```python
await page.goto(url, wait_until="domcontentloaded", timeout=60000)
# 关键等待：确保 Royalties 板块已经渲染完成
await page.wait_for_selector('div[name="Royalties"]', state='attached', timeout=30000)
html_content = await page.content()
```

**为什么这很重要**：该页面是 React SPA，Royalties 数据是通过异步 API 获取并在客户端渲染的。如果没有等待 `div[name="Royalties"]`，保存的 HTML 将缺少最关键的财务数据。

原始 HTML 使用 BeautifulSoup 美化格式后保存为 `{asset_id}.html`。

### 3.2 API 数据拉取 (`new/new_2.py`)

**`fetch_listing_api(asset_id, output_dir)`** 调用驱动页面的内部 REST API。

```python
url = f"https://auctions.royaltyexchange.com/orderbook/api/listings/{asset_id}/"
params = {
    "include[]": [
        "asset.*",                # 资产基本信息
        "valuation_description.*", # 估值详情
        "offers.*"                # 报价记录
    ]
}
response = requests.get(url, params=params, headers={"Accept": "application/json"})
data = response.json()
```

API 返回的 JSON 包含金融分析所需的全部数据：

```json
{
  "asset": { "name": "...", "sale_history": [...] },
  "valuation": {
    "ltm": 2781.0,                        // 近 12 月收益
    "lifetime_amount": 15000.0,            // 生命周期总收益
    "three_years_average": 5200.0,         // 三年平均
    "dollar_age": 8.5,                     // 加权美元年龄
    "top_income_types": [                  // 各收入类型分解
      {"name": "STREAMING MECHANICAL", "earnings": 1200.0}
    ],
    "track_list": ["Track A", "Track B"]   // 曲目列表
  },
  "offers": [{"amount": "11750.00", "state": "filled"}],
  "term": "10 years"
}
```

### 3.3 第一步分析 — Royalties 表格提取 (`new_analysis_1.py`)

解析 HTML 中 `div[name="Royalties"]` 板块的结构化信息。核心挑战是保留**高亮语义**——带有 `cell-bold` CSS 类的单元格表示该版税类型或分发机构在资产中"被包含"。

```python
def extract_royalties(html_file_path):
    soup = BeautifulSoup(f.read(), 'html.parser')
    section = soup.find('div', {'name': 'Royalties'})
    table = section.find('table')

    for row in table.find_all('tr'):
        for cell in row.find_all('td'):
            cell_bold = 'cell-bold' in cell.get('class', [])
            # 如果单元格本身加粗，整个文本都标记为高亮
            # 否则只标记子元素中的加粗部分
```

输出结构为每个单元格同时保留原始文本和明确的高亮标记数组：

```json
{
  "table": [
    [{"text": "Type", "highlighted": null},
     {"text": "Musical Composition", "highlighted": ["Musical Composition"]},
     {"text": "Sound Recording", "highlighted": null}]
  ],
  "ascap": { "description": "...", "links": [...] }
}
```

### 3.4 第二步分析 — 42 字段因子提取 (`new_analysis_2.py`)

这是整个管线的分析核心。从 `Factor List.xlsx` 中读取因子定义清单（Sheet "New"，41 行因子定义），然后从 API JSON 数据中提取每个因子值。

#### 因子清单结构

Excel 文件为每个因子定义三个维度的参数：
- `df_name` — 因子名称（在输出数据框中的列名）
- `json_key` — JSON 中对应的键名
- `measure` — 度量方式说明
- `notice` — 特殊处理说明

```python
def read_factor_list(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb['New']
    factors = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        factors.append({
            "df_name": str(row[0]).strip(),
            "json_key": str(row[1]).strip() if row[1] else None,
            "measure": str(row[2]).strip() if row[2] else None,
            "notice": str(row[3]).strip() if row[3] else None,
        })
    return factors
```

#### 核心因子提取逻辑

`extract_factor()` 函数使用**条件路由模式**——根据因子的 `df_name` 分发到不同的提取逻辑：

```python
def extract_factor(data, factor):
    df_name = factor["df_name"]

    if df_name == "Sale Price":
        offers = data.get("offers", []) or []
        for offer in offers:
            if offer.get("state") == "filled":
                return float(offer["amount"])
        return float(offers[0]["amount"])  # 降级：取第一个报价

    elif df_name == "TracksIncluded":
        track_list = data.get("valuation", {}).get("track_list", []) or []
        return len(track_list)

    elif df_name == "HighestBidLowestBid":
        offers = data.get("offers", []) or []
        amounts = [float(o["amount"]) for o in offers if o.get("amount")]
        return max(amounts) - min(amounts) if len(amounts) >= 2 else 0.0

    elif df_name.startswith("Income_Type_"):
        # 名称归一化后在 top_income_types[] 中匹配
        target_name = normalize_income_type_name(df_name)
        for entry in data.get("valuation", {}).get("top_income_types", []):
            if normalize_income_type_name(entry["name"]) == target_name:
                return entry.get("earnings")
        return None
```

#### 收入类型名称归一化

因子清单中的名称与 API 实际返回的名称存在不一致（如拼写错误、空格不一致），需要进行归一化处理：

```python
def normalize_income_type_name(raw_name):
    name = raw_name.upper().strip()
    if name.startswith("INCOME_TYPE_"):
        name = name[len("INCOME_TYPE_"):].strip()
    # 修正因子清单中的已知拼写错误
    name = name.replace("STREAMINGP ERFORMANCE", "STREAMING PERFORMANCE")
    name = name.replace("STREAMINGS YNCHRONIZATION", "STREAMING SYNCHRONIZATION")
    name = name.replace("SOUNDRECORDING", "SOUND RECORDING")
    name = re.sub(r'\s+', ' ', name)
    return name
```

#### 27 个有效因子对照表

| 因子名称 | API 数据源 | 提取逻辑 |
|----------|-----------|----------|
| Sale Price | `offers[]` | 取第一个 filled 状态的报价金额，降级取第一个报价 |
| TermRemaining | `term` | 直接读取文本（如 "10 years"） |
| TracksIncluded | `valuation.track_list` | 统计曲目数组长度 |
| NumberOfBids | `offers[]` | 报价数组长度 |
| HighestBidLowestBid | `offers[]` | 最高金额 − 最低金额 |
| HasLastTransaction | `asset.sale_history` | 存在为 1，不存在为 0 |
| Income_Type_* (14 种) | `valuation.top_income_types[]` | 按归一化名称匹配 → earnings |
| Last12Months | `valuation.ltm` | 直接读取浮点数 |
| EarningsSinceStart | `valuation.lifetime_amount` | 直接读取浮点数 |
| 3YearAverage | `valuation.three_years_average` | 直接读取浮点数 |
| DollarAge | `valuation.dollar_age` | 直接读取浮点数 |

### 3.5 第三步分析 — 合并补全 (`new_analysis_3.py`)

第二步分析中 rows 28–41 留空（值为 `null`），因为这些字段需要 HTML Royalties 表格中的信息。第三步通过交叉引用第一步的表格数据来补全。

```python
def fill_rows_28_to_41(step1_data, step2_data, file_exists_in_both):
    result = dict(step2_data)

    # Row 28: 判断 Royalties 表格是否存在
    result["CopyrightsIncluded_Yes"] = 1 if file_exists_in_both else 0

    # Rows 29–30: 通过表头高亮判断版税类型
    row0 = table[0]
    h0_1 = row0[1].get("highlighted")  # Musical Composition 列
    h0_2 = row0[2].get("highlighted")  # Sound Recording 列
    result["Type_xroyaltyType_MusicalCompositionSoundRecording"] = 1 if (h0_1 and h0_2) else 0
    result["Type_xroyaltyType_SoundRecording"] = 1 if (not h0_1 and h0_2) else 0

    # Rows 31–41: 对高亮单元格进行关键字匹配
    # 分发机构 → 搜索 "BMI", "ASCAP", "Universal Music Publishing Group" 等
    # 收入来源 → 搜索 "CD Sales", "TV/Film", "Satellite Radio", "Internet Streaming"
    # 权利类型 → 搜索 "Public Performance", "Sync"
```

`keyword_in_highlighted()` 辅助函数对每个单元格的 `highlighted` 数组进行大小写不敏感的模糊匹配：

```python
def keyword_in_highlighted(cell, keyword):
    highlighted = cell.get("highlighted")
    if highlighted is None:
        return False
    keyword_lower = keyword.lower()
    for item in highlighted:
        if keyword_lower in item.lower():
            return True
    return False
```

---

## 第四部分 — 旧格式数据分析

旧格式页面（`/auctions/{slug}/`）需要身份认证，HTML 结构与新格式完全不同。项目通过独立的处理路径来处理。

### 4.1 登录与页面抓取 (`old/old_1.py`)

**`scrape_auction_page(url, output_dir, slug)`** 使用 Playwright：

1. **登录平台**：自动填写登录表单（邮箱 + 密码），提交并等待跳转
2. **导航到目标页面**：访问拍卖页面
3. **等待关键元素**：等待 `#id_tabbed_metadata` 出现
4. **保存 HTML**：格式化后保存

```python
async def login(context) -> bool:
    page = await context.new_page()
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)  # 等待 React 表单挂载

    # 填写 Material-UI TextField 表单
    await page.fill("#sign-in-email", EMAIL, timeout=5000)
    await page.fill("#sign-in-password", PASSWORD, timeout=5000)
    await page.click('button[type="submit"]', timeout=5000)

    # 等待从登录页面跳转
    await page.wait_for_function(
        "() => !window.location.href.includes('/auth/sign-in')",
        timeout=30000,
    )
    if "/auth/sign-in" in page.url:
        return False  # 登录失败
    return True
```

登录后导航到拍卖页面，等待关键容器 `#id_tabbed_metadata`——包含所有拍卖核心数据的 React 渲染区域。

### 4.2 第一步分析 — Rights 表格提取 (`old_analysis_1.py`)

从旧版 HTML 中提取 "What rights are included?" 权利包含表格。输出格式与 `new_analysis_1.py` **完全兼容**，使得下游可以共享处理逻辑。

新旧格式的表格定位方式完全不同：

```python
# 旧格式：先找标题，再定位其后的表格
heading = soup.find(re.compile(r'h[1-4]'), string=re.compile(
    r'What rights are included', re.IGNORECASE))
table = heading.find_next('table', class_='crdt')

# 新格式：通过 ID 直接定位
section = soup.find('div', {'name': 'Royalties'})
```

表格包含 4 个内容行，每行有标签列和两个数据列（MC = 音乐创作权, SR = 录音版权）：

```python
for row_idx, row in enumerate(rows):
    cells = row.find_all('td', recursive=False)
    if row_idx == 0:        # Copyrights Included?
    elif row_idx == 1:       # Royalty Types（可能包含嵌套表格）
    elif row_idx == 2:       # Sources
    elif row_idx == 3:       # Distributors
```

**嵌套表格处理**：Royalty Types 单元格可能包含一个内部 `<table class="crdt inner">`，代码递归处理：

```python
inner_table = cell.find('table', class_='crdt inner')
if inner_table:
    all_items = []
    included_items = []
    for td in inner_table.find_all('td'):
        item_text = td.get_text(strip=True)
        if item_text:
            all_items.append(item_text)
            if 'not-included' not in td.get('class', []):
                included_items.append(item_text)
    text = ' | '.join(all_items)
    highlighted = included_items if included_items else None
```

### 4.3 第二步分析 — Overview 与拍卖历史提取 (`old_analysis_2.py`)

从旧版 HTML 的 Overview 表和拍卖历史中提取结构化数据，组装成与新格式相同的 42 字段格式。

#### Overview 表提取

扫描 `table.es-overview-table` 的每一行，通过标签文本（不区分大小写）定位数据项：

```python
def extract_overview(soup):
    table = soup.find('table', class_='es-overview-table')
    for row in rows:
        label = cells[0].get_text(strip=True).lower()
        value_text = cells[1].get_text(separator=' ', strip=True)

        if 'closing price' in label:
            result["SalePrice"] = parse_currency(value_text)
        elif 'investment term' in label or label.startswith('term:'):
            result["TermRemaining"] = value_text
        elif 'last 12 months' in label or 'past 4 quarter' in label:
            result["Last12Months"] = parse_currency(value_text)
        elif 'dollar age' in label:
            result["DollarAge"] = parse_dollar_age(value_text)
        elif 'track' in label:
            result["TracksIncluded"] = parse_number(value_text)
```

文本解析辅助函数处理各种格式：

```python
def parse_currency(text):
    """去掉 $ 和 , 后解析为浮点数。"""
    cleaned = re.sub(r'[$,]', '', text.strip())
    return float(cleaned)

def parse_dollar_age(text):
    """从 '14.02 Years' 格式中提取年份数值。"""
    m = re.search(r'([\d.]+)\s*Years?', text, re.IGNORECASE)
    return float(m.group(1)) if m else None
```

#### 拍卖历史提取

出价列表位于 `<h3 id="bids_list_header">` 之后的 `<ol type="1">` 中：

```python
def extract_auction_history(soup):
    header = soup.find('h3', id='bids_list_header')
    ol = header.find_next_sibling('ol', type="1")
    bid_items = ol.find_all('li', recursive=False)
    result["NumberOfBids"] = len(bid_items)

    amounts = []
    for li in bid_items:
        text = li.get_text(separator=' ', strip=True)
        m = re.search(r'\$([\d,]+(?:\.\d{1,2})?)', text)
        if m:
            amounts.append(float(m.group(1).replace(',', '')))

    result["HighestBidLowestBid"] = max(amounts) - min(amounts) if len(amounts) >= 2 else 0.0
```

#### 输出拼接

`build_output()` 将所有提取的数据组装为统一的 42 字段字典。旧格式页面缺少某些数据（如收入类型分解、收益历史），这些字段设为 `null` 由后续步骤补全：

```python
def build_output(overview, auction):
    obj = {}
    obj["Sale Price"] = overview["SalePrice"]
    obj["NumberOfBids"] = auction["NumberOfBids"]
    # ... 来自 Overview 的 6 个字段，来自拍卖历史的 2 个字段

    # 收入类型：全部为 null（旧格式无此数据）
    for it in income_types:
        obj[f"Income_Type_{it}"] = None

    # Rows 28-41：全部为 null（在第三步通过权利表格补全）
    for field in fields_rows_28_to_41:
        obj[field] = None
    return obj
```

### 4.4 第三步分析 — 合并补全 (`old_analysis_3.py`)

逻辑与 `new_analysis_3.py` 一致，但类型检测方法略有不同。不是仅看表头高亮，而是检查表格内容行中各列**是否包含任何高亮单元格**：

```python
def column_has_any_highlight(table, col_idx):
    """检查指定列的内容行是否有高亮内容。"""
    for row_idx in range(1, len(table)):
        cell = row[col_idx] if len(row) > col_idx else None
        if cell and cell.get("highlighted") is not None and len(cell["highlighted"]) > 0:
            return True
    return False

mc_highlighted = column_has_any_highlight(table, 1)  # 第 1 列 = 音乐创作权
sr_highlighted = column_has_any_highlight(table, 2)  # 第 2 列 = 录音版权
```

其余关键词搜索逻辑（权利类型、分发机构、收入来源）与新格式相同。

### 4.5 第四步分析 — Slug 到数字 ID 映射 (`old_analysis_4.py`)

旧格式使用名称 slug 作为文件名（如 `tarquin-collection.json`），而新格式使用数字 ID。为统一合并，所有文件必须有数字命名。

从 HTML 的 JavaScript 变量 `dataLayer` 中提取 `auctionId`：

```python
def get_auction_id_from_html(html_file_path):
    with open(html_file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    # 匹配 dataLayer 中的 auctionId 值
    match = re.search(r'auctionId["\']?\s*:\s*["\']?(\d+)', content)
    return match.group(1) if match else None
```

文件重命名复制：`{slug}.json` → `{auctionId}.json`。

### 4.6 第五步分析 — Buy-It-Now 手工映射 (`old_analysis_5.py`)

6 个"一口价"（Buy It Now）页面在 HTML 中没有 `auctionId`。通过**硬编码映射表**处理：

```python
BUY_IT_NOW_MAP = {
    "buy-it-now-brand-new-hip-hop-releases": 11,
    "buy-it-now-indie-electropop-lolawolf": 20,
    "buy-it-now-international-k-pop-catalog": 17,
    "buy-it-now-platinum-hit-from-zendaya-replay-more": 2,
    "buy-it-now-production-music-in-emmy-winning-series": 7,
    "buy-it-now-rb-pop-catalog-featuring-trey-songz": 1,
}
```

步骤将第四步的 809 个自动映射文件与 6 个手工映射文件合并，在第五步产生完整的数据集。

---

## 第五部分 — 最终合并输出

**文件**: `python_codes/final_output.py`

### `merge_folders_and_generate_csv()`

将两个分析管线的最终结果合并为一个统一的 CSV 文件。

**第一步 — 文件夹合并**：将 `analysis/new_step_3` 和 `analysis/old_step_5` 中的所有 JSON 文件复制到 `analysis/final/`，文件名冲突时添加 `_copy` 后缀。

**第二步 — 模式校验**：以第一个文件的字段集合为基准，对比每个 JSON 文件的字段一致性：

```python
if standard_keys is None:
    standard_keys = set(data.keys())

current_keys = set(data.keys())
if current_keys != standard_keys:
    missing = standard_keys - current_keys
    extra = current_keys - standard_keys
    print(f"⚠ {json_file.name} 模式不匹配: 缺少 {missing}, 多余 {extra}")
```

**第三步 — CSV 生成**：按文件名数字排序，按固定列顺序输出：

```python
all_data.sort(key=lambda x: int(Path(x['filename']).stem))

all_keys = ['filename']
for key in field_order:
    if key not in all_keys:
        all_keys.append(key)

with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=all_keys)
    writer.writeheader()
    writer.writerows(all_data)
```

### 最终 CSV 数据字典

| 列名 | 类型 | 说明 |
|------|------|------|
| `filename` | str | 资产 ID 文件名（如 `2783.json`） |
| `Sale Price` | float | 拍卖成交价 |
| `TermRemaining` | str | 版权剩余年限（文本） |
| `TracksIncluded` | int | 包含曲目数 |
| `Fees` | str | 费用说明 |
| `NumberOfBids` | int | 出价总数 |
| `HighestBidLowestBid` | float | 出价差额（最高−最低） |
| `HasLastTransaction` | int | 是否有历史交易（1/0） |
| `Income_Type_STREAMING MECHANICAL` | float | 各收入类型近 12 月收益（共 14 列） |
| `Income_Type_PERFORMANCE` | float | ... |
| ... | ... | |
| `Last12Months` | float | 近 12 个月总收益 |
| `EarningsSinceStart` | float | 生命周期总收益 |
| `3YearAverage` | float | 三年平均收益 |
| `DollarAge` | float | 加权美元年龄（年） |
| `CopyrightsIncluded_Yes` | int | 版权是否包含（1/0） |
| `Type_xroyaltyType_MusicalCompositionSoundRecording` | int | 同时包含 MC+SR（1/0） |
| `Type_xroyaltyType_SoundRecording` | int | 仅包含 SR（1/0） |
| `Rights_Public_Performance` | int | 包含公开表演权（1/0） |
| `Rights_Sync` | int | 包含 Sync 权（1/0） |
| `Distributor_universal` / `_bmi` / `_ascap` / `_sony` / `_warner` | int | 各分发机构是否存在（1/0） |
| `Source_cd_sales` / `tv_film` / `_satellite_radio` / `_internet_streaming` | int | 各收入来源是否存在（1/0） |

---

## 技术要点总结

### 1. 双轨架构

新旧两种页面格式在 DOM 结构、数据来源和访问方式上差异巨大。项目不为两种格式构建一个脆弱的通用抓取器，而是实现**完全独立的处理管线**，只有在最终输出阶段才通过统一的 42 字段格式进行合并。这种隔离确保了一种格式的变更不会影响另一种。

### 2. Playwright 处理动态内容

Royalty Exchange 是 React SPA——关键数据通过异步请求获取并在客户端渲染。简单的 HTTP 请求只能获取空的页面外壳。Playwright（无头 Chromium）实现了：
- 执行 JavaScript 并等待特定元素渲染
- 处理认证流程（登录表单、Cookie 横幅）
- 捕获完整的渲染后 DOM

两个关键的等待策略：
```python
# 新格式：等待 Royalties 板块
await page.wait_for_selector('div[name="Royalties"]', state='attached', timeout=30000)

# 旧格式：等待元数据容器
await page.wait_for_selector('#id_tabbed_metadata', timeout=20000)
```

### 3. 高亮标记语义化

页面表格中的 CSS 类（`cell-bold`、`not-included`）指示某项在资产中"被包含"或"不被包含"。这**不仅仅是样式**——它是区分资产版权构成的核心信号。分析管线通过以下方式保留这一语义：
1. 为每个单元格记录 `highlighted` 数组
2. 将高亮模式映射为二值（1/0）因子值
3. 对高亮文本进行关键字匹配以检测分发机构、收入来源和权利类型

### 4. 因子驱动分析

`Factor List.xlsx` 定义**提取什么**，而代码定义**如何提取**。这种分离实现了：
- 新增因子只需修改 Excel 配置
- 每个因子的提取逻辑可独立开发
- 整个数据集保持一致的命名

### 5. 渐进式数据补全

Rows 28–41 无法仅从 API JSON 中提取（需要 HTML 表格信息）。三步分析序列（提取 → 解析 → 合并）确保每一步都建立在前一步的输出之上，避免循环依赖，使每个模块职责单一。

### 6. 可恢复的抓取

`progress.json` 机制允许抓取管线随时停止和重启。对于大规模数据收集而言，网络错误、限速和超时是常态，这一设计至关重要。

### 7. 统一的 ID 系统

最终数据集全程使用**数字 ID**。旧格式的 slug 名称通过 HTML 中嵌入的 `auctionId`（或针对 buy-it-now 项的手工映射）映射为数字 ID。这确保所有资产具有一致的键值标识。
