import csv
import json
import os
import re
import sys
import asyncio
from urllib.parse import urlparse

# Add project root to Python path so 'old/' and 'new/' modules are importable
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

PROGRESS_FILE = "C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\progress.json"
CSV_FILE = "C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\urls_lastmod.csv"
RESOURCES_NEW = "C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\resources\\new"
RESOURCES_OLD = "C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\resources\\old"


def classify_url(url: str) -> tuple:
    """Classify a URL as 'new' (numeric ID) or 'old' (name slug).

    Returns:
        tuple[str, str]: (type, id_or_slug)
            - ("new", "5986") for numeric asset IDs
            - ("old", "tarquin-collection") for name-based slugs
    """
    path = urlparse(url).path
    if re.search(r'/orderbook/(asset-detail|api/listings)/\d+/', path):
        match = re.search(r'/(\d+)/?$', path)
        return ("new", match.group(1)) if match else ("old", "")
    else:
        slug = path.rstrip('/').split('/')[-1]
        return ("old", slug)


def load_progress() -> dict:
    """Load progress from progress.json, or return empty dict."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "failed": {}}


def save_progress(progress: dict) -> None:
    """Save progress dict to progress.json."""
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


async def process_url(row: list, progress: dict) -> None:
    """Process a single CSV row: classify, scrape, track progress."""
    url = row[0]
    if url in progress["completed"]:
        print(f"  SKIP (already completed)")
        return

    url_type, id_or_slug = classify_url(url)
    print(f"  Type: {url_type}, ID/Slug: {id_or_slug}")

    try:
        if url_type == "new":
            from new.new_1 import scrape_asset_page
            result = await scrape_asset_page(int(id_or_slug), RESOURCES_NEW)
            if result is None:
                raise Exception("scrape_asset_page returned None (likely network error)")

            from new.new_2 import fetch_listing_api
            result2 = fetch_listing_api(int(id_or_slug), RESOURCES_NEW)
            if result2 is None:
                print("  WARNING: API call returned None, but HTML was saved")
        else:
            from old.old_1 import scrape_auction_page
            result = await scrape_auction_page(url, RESOURCES_OLD, id_or_slug)
            if result is None:
                raise Exception("scrape_auction_page returned None")

        progress["completed"].append(url)
        print(f"  OK")
    except Exception as e:
        progress["failed"][url] = str(e)
        print(f"  FAILED: {e}")
    finally:
        save_progress(progress)


async def main():
    """Main orchestrator: read CSV, process each URL sequentially."""
    os.makedirs(RESOURCES_NEW, exist_ok=True)
    os.makedirs(RESOURCES_OLD, exist_ok=True)

    progress = load_progress()

    with open(CSV_FILE, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        print("CSV file is empty")
        return

    header = rows[0]
    data_rows = rows[1:]
    total = len(data_rows)
    completed_count = len(progress["completed"])

    print(f"Total URLs to process: {total}")
    print(f"Already completed: {completed_count}")
    print(f"Already failed: {len(progress['failed'])}")
    print()

    for i, row in enumerate(data_rows, 1):
        url = row[0].strip()
        if url in progress["completed"]:
            continue

        print(f"[{i}/{total}] Processing: {url}")
        await process_url(row, progress)
        print()

    final = load_progress()
    print("=" * 50)
    print(f"DONE. Total: {total}, Completed: {len(final['completed'])}, Failed: {len(final['failed'])}")


if __name__ == "__main__":
    asyncio.run(main())
