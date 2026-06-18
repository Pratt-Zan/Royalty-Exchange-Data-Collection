import os
import json
import re


def get_auction_id_from_html(html_file_path):
    """Extract auctionId from dataLayer in old HTML file. Returns None if not found."""
    try:
        with open(html_file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        print(f"    Error reading {os.path.basename(html_file_path)}: {e}")
        return None

    # Pattern: dataLayer=[{"userId":"...","auctionId":"437"}]
    match = re.search(r'auctionId["\']?\s*:\s*["\']?(\d+)', content)
    if match:
        return match.group(1)
    return None


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    html_dir = os.path.join(project_dir, "resources", "old")
    step3_dir = os.path.join(project_dir, "analysis", "old_step_3")
    output_dir = os.path.join(project_dir, "analysis", "old_step_4")

    os.makedirs(output_dir, exist_ok=True)

    html_files = sorted([f for f in os.listdir(html_dir) if f.endswith(".html")])
    total = len(html_files)
    processed = 0
    skipped = 0
    errors = 0

    print(f"Processing {total} HTML files...")
    print()

    for filename in html_files:
        html_path = os.path.join(html_dir, filename)
        slug = filename.replace(".html", "")

        # Step 1: Extract auctionId from HTML
        auction_id = get_auction_id_from_html(html_path)
        if auction_id is None:
            print(f"  SKIP (no auctionId): {filename}")
            skipped += 1
            continue

        # Step 2: Read corresponding step_3 JSON
        step3_path = os.path.join(step3_dir, f"{slug}.json")
        if not os.path.exists(step3_path):
            print(f"  ERROR (no step_3): {filename}")
            errors += 1
            continue

        try:
            with open(step3_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ERROR reading {slug}.json: {e}")
            errors += 1
            continue

        # Step 3: Write to step_4 with auctionId filename
        output_path = os.path.join(output_dir, f"{auction_id}.json")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            processed += 1
        except Exception as e:
            print(f"  ERROR writing {auction_id}.json: {e}")
            errors += 1
            continue

    print(f"\nDone. Total: {total}, Processed: {processed}, Skipped (no auctionId): {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
