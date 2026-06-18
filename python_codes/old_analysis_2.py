"""
old_analysis_2.py — Extract numeric/text data from old-format HTML files' Overview tables
and Auction History. Output JSON to analysis/old_step_2/.

Each output file matches the new_step_2/2783.json format: 42 fields dictionary.
Rows 28-41 are set to null (they come from step_1 via step_3).
"""

import os
import json
import re
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
INPUT_FOLDER = (
    r"C:\Users\Pratt\Desktop\HKUST-RA\Data Collection Royalty exchange"
    r"\resources\old"
)
OUTPUT_FOLDER = (
    r"C:\Users\Pratt\Desktop\HKUST-RA\Data Collection Royalty exchange"
    r"\analysis\old_step_2"
)


# ---------------------------------------------------------------------------
# Helper: safe float extraction
# ---------------------------------------------------------------------------
def parse_currency(text):
    """Strip $ , and parse as float. Returns None on failure."""
    if not text:
        return None
    cleaned = re.sub(r'[$,]', '', text.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_number(text):
    """Extract the first integer from a string. Returns None on failure."""
    if not text:
        return None
    m = re.search(r'(\d[\d,]*)', text)
    if m:
        cleaned = m.group(1).replace(',', '')
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def parse_dollar_age(text):
    """Extract float from strings like '14.02 Years' or '8.54 Years'."""
    if not text:
        return None
    m = re.search(r'([\d.]+)\s*Years?', text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Overview table extraction (label-based)
# ---------------------------------------------------------------------------
def extract_overview(soup):
    """
    Scan the es-overview-table rows by label text (case-insensitive).
    Returns a dict with keys: SalePrice, TermRemaining, Fees, Last12Months,
    DollarAge, TracksIncluded.
    """
    result = {
        "SalePrice": None,
        "TermRemaining": None,
        "TracksIncluded": None,
        "Fees": None,
        "Last12Months": None,
        "DollarAge": None,
    }

    table = soup.find('table', class_='es-overview-table')
    if not table:
        return result

    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 2:
            continue

        label = cells[0].get_text(strip=True).lower()
        value_cell = cells[1]
        # Value cell may contain a <p> wrapper; get the joined text
        value_text = value_cell.get_text(separator=' ', strip=True)

        # --- Closing Price / Sale Price ---
        if 'closing price' in label:
            parsed = parse_currency(value_text)
            if parsed is not None:
                result["SalePrice"] = parsed

        # --- Investment Term / Term ---
        elif 'investment term' in label or label.startswith('term:'):
            result["TermRemaining"] = value_text

        # --- Fees / Buyer Fees ---
        elif 'fees' in label or 'buyer fee' in label:
            result["Fees"] = value_text

        # --- Last 12 Months / Past 4 Quarters ---
        elif 'last 12 months' in label or 'past 4 quarter' in label:
            parsed = parse_currency(value_text)
            if parsed is not None:
                result["Last12Months"] = parsed

        # --- Dollar Age ---
        elif 'dollar age' in label:
            result["DollarAge"] = parse_dollar_age(value_text)

        # --- Track / Track List ---
        elif 'track' in label:
            # Try to extract a number (e.g. "13 Tracks", "Track List (24)")
            parsed = parse_number(value_text)
            if parsed is not None:
                result["TracksIncluded"] = parsed

    return result


# ---------------------------------------------------------------------------
# Auction history extraction
# ---------------------------------------------------------------------------
def extract_auction_history(soup):
    """
    Find <h3 id="bids_list_header">, get the next <ol type="1"> sibling,
    count <li> elements (= NumberOfBids), extract dollar amounts to compute
    HighestBidLowestBid.
    """
    result = {
        "NumberOfBids": 0,
        "HighestBidLowestBid": 0.0,
    }

    header = soup.find('h3', id='bids_list_header')
    if not header:
        return result

    # The bids <ol> is the next <ol> sibling after the header
    ol = header.find_next_sibling('ol', type="1")
    if not ol:
        return result

    bid_items = ol.find_all('li', recursive=False)
    result["NumberOfBids"] = len(bid_items)

    # Extract dollar amounts from each <li>
    amounts = []
    for li in bid_items:
        text = li.get_text(separator=' ', strip=True)
        m = re.search(r'\$([\d,]+(?:\.\d{1,2})?)', text)
        if m:
            cleaned = m.group(1).replace(',', '')
            try:
                amounts.append(float(cleaned))
            except ValueError:
                pass

    if len(amounts) >= 2:
        result["HighestBidLowestBid"] = max(amounts) - min(amounts)
    else:
        result["HighestBidLowestBid"] = 0.0

    return result


# ---------------------------------------------------------------------------
# Build the 42-field output dictionary
# ---------------------------------------------------------------------------
def build_output(overview, auction):
    """
    Combine all extracted data into the 42-field format matching
    analysis/new_step_2/2783.json.
    """
    obj = {}

    # Row 1: Sale Price
    obj["Sale Price"] = overview["SalePrice"]

    # Row 2: TermRemaining
    obj["TermRemaining"] = overview["TermRemaining"]

    # Row 3: TracksIncluded
    obj["TracksIncluded"] = overview["TracksIncluded"]

    # Row 4: Fees
    obj["Fees"] = overview["Fees"]

    # Row 5: NumberOfBids
    obj["NumberOfBids"] = auction["NumberOfBids"]

    # Row 6: NumberOfBiddersForIDBefore2783
    obj["NumberOfBiddersForIDBefore2783"] = 1

    # Row 7: HighestBidLowestBid
    obj["HighestBidLowestBid"] = auction["HighestBidLowestBid"]

    # Row 8: HasLastTransaction
    obj["HasLastTransaction"] = 1

    # Rows 9-21: All Income_Type_* → null (14 fields)
    income_types = [
        "STREAMING MECHANICAL",
        "STREAMINGP ERFORMANCE",
        "STREAMINGS YNCHRONIZATION",
        "MECHANICAL",
        "PERFORMANCE",
        "OTHER",
        "SOUNDRECORDING",
        "SYNCHRONIZATION",
        "DOWNLOAD MECHANICAL",
        "PRINT",
        "DOWNLOAD PERFORMANCE",
        "MECHANICAL PERFORMANCE",
        "PROFIT PARTICIPATION",
        "RADIO",
    ]
    for it in income_types:
        obj[f"Income_Type_{it}"] = None

    # Row 22: Last12Months
    obj["Last12Months"] = overview["Last12Months"]

    # Rows 23-24: fixed null
    obj["EarningsSinceStart"] = None
    obj["3YearAverage"] = None

    # Row 25: DollarAge
    obj["DollarAge"] = overview["DollarAge"]

    # Rows 28-41: all null (these come from step_1 via step_3)
    fields_rows_28_to_41 = [
        "CopyrightsIncluded_Yes",
        "Type_xroyaltyType_MusicalCompositionSoundRecording",
        "Type_xroyaltyType_SoundRecording",
        "Rights_Public_Performance",
        "Rights_Sync",
        "Distributor_universal",
        "Distributor_bmi",
        "Distributor_ascap",
        "Distributor_sony",
        "Distributor_warner",
        "Source_cd_sales",
        "Source tv_film",
        "Source_ satellite_radio",
        "Source_internet_streaming",
    ]
    for field in fields_rows_28_to_41:
        obj[field] = None

    return obj


# ---------------------------------------------------------------------------
# Process a single HTML file
# ---------------------------------------------------------------------------
def process_file(html_path):
    """Return the 42-field dict or None on failure."""
    try:
        with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
    except Exception as e:
        print(f"    Error reading file: {e}")
        return None

    # Overview extraction (wrapped in try/except)
    try:
        overview = extract_overview(soup)
    except Exception as e:
        print(f"    Error extracting overview: {e}")
        overview = {
            "SalePrice": None,
            "TermRemaining": None,
            "TracksIncluded": None,
            "Fees": None,
            "Last12Months": None,
            "DollarAge": None,
        }

    # Auction history extraction (wrapped in try/except)
    try:
        auction = extract_auction_history(soup)
    except Exception as e:
        print(f"    Error extracting auction history: {e}")
        auction = {
            "NumberOfBids": 0,
            "HighestBidLowestBid": 0.0,
        }

    return build_output(overview, auction)


# ---------------------------------------------------------------------------
# Main batch processing
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    all_files = sorted([
        f for f in os.listdir(INPUT_FOLDER)
        if f.endswith('.html')
    ])

    total = len(all_files)
    success_count = 0
    error_count = 0

    print(f"Processing {total} files...")
    print(f"Input:  {INPUT_FOLDER}")
    print(f"Output: {OUTPUT_FOLDER}")
    print()

    for idx, filename in enumerate(all_files, start=1):
        input_path = os.path.join(INPUT_FOLDER, filename)
        output_filename = filename.replace('.html', '.json')
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)

        print(f"[{idx}/{total}] {filename}")

        try:
            data = process_file(input_path)
            if data is not None:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                success_count += 1
            else:
                # process_file returns None on read error; write a fallback
                data = build_output(
                    {"SalePrice": None, "TermRemaining": None, "TracksIncluded": None,
                     "Fees": None, "Last12Months": None, "DollarAge": None},
                    {"NumberOfBids": 0, "HighestBidLowestBid": 0.0},
                )
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                error_count += 1
                print(f"    Wrote fallback (read error)")
        except Exception as e:
            print(f"    Failed: {e}")
            # Write fallback anyway so all files have a corresponding JSON
            data = build_output(
                {"SalePrice": None, "TermRemaining": None, "TracksIncluded": None,
                 "Fees": None, "Last12Months": None, "DollarAge": None},
                {"NumberOfBids": 0, "HighestBidLowestBid": 0.0},
            )
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            error_count += 1

        # Progress indicator
        if idx % 100 == 0:
            print(f"  --- Progress: {idx}/{total} files processed ---")

    print()
    print(f"Done! Total: {total}, Success: {success_count}, Errors: {error_count}")
