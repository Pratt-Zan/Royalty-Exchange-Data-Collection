import os
import json
import re
import openpyxl


def read_factor_list(xlsx_path):
    """Read Factor List.xlsx Sheet 'New', return list of factor definitions (rows 2-41)."""
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb['New']
    factors = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        df_name = row[0]
        json_key = row[1] if row[1] and str(row[1]).strip() != '\\' else None
        measure = row[2] if row[2] and str(row[2]).strip() != '\\' else None
        notice = row[3] if row[3] else None
        factors.append({
            "df_name": str(df_name).strip() if df_name else "",
            "json_key": str(json_key).strip() if json_key else None,
            "measure": str(measure).strip() if measure else None,
            "notice": str(notice).strip() if notice else None,
            "row": row_idx
        })
    wb.close()
    return factors


def normalize_income_type_name(raw_name):
    """Normalize Income_Type suffix to match top_income_types[].name."""
    name = raw_name.upper().strip()
    # Remove "Income_Type_" prefix if present
    if name.startswith("INCOME_TYPE_"):
        name = name[len("INCOME_TYPE_"):].strip()
    # Fix known typos in the Factor List DF_names
    # "STREAMINGP ERFORMANCE" -> "STREAMING PERFORMANCE"
    name = name.replace("STREAMINGP ERFORMANCE", "STREAMING PERFORMANCE")
    # "STREAMINGS YNCHRONIZATION" -> "STREAMING SYNCHRONIZATION"
    name = name.replace("STREAMINGS YNCHRONIZATION", "STREAMING SYNCHRONIZATION")
    # "SOUNDRECORDING" -> "SOUND RECORDING"
    name = name.replace("SOUNDRECORDING", "SOUND RECORDING")
    # Collapse multiple spaces into single space
    name = re.sub(r'\s+', ' ', name)
    return name


def extract_factor(data, factor):
    """Extract a single factor value from JSON data based on factor definition."""
    df_name = factor["df_name"]
    json_key = factor["json_key"]
    measure = factor["measure"]
    notice = factor["notice"]
    row = factor["row"]

    # Rows 28-41: stored as None (from analysis 1)
    if row >= 28:
        return None

    # Row 5: Fees - no data source
    if df_name == "Fees":
        return None

    # Row 7: NumberOfBiddersForIDBefor e2783 - always None
    if df_name == "NumberOfBiddersForIDBefore2783":
        return None

    # ---- Extraction logic for rows 2-27 ----

    # Sale Price (row 2)
    if df_name == "Sale Price":
        offers = data.get("offers", []) or []
        if not offers:
            return None
        # Look for first filled offer
        for offer in offers:
            if offer.get("state") == "filled":
                return float(offer["amount"])
        # Fallback to first offer
        return float(offers[0]["amount"])

    # TermRemaining (row 3)
    if df_name == "TermRemaining":
        return data.get("term")

    # TracksIncluded (row 4)
    if df_name == "TracksIncluded":
        track_list = data.get("valuation", {}).get("track_list", []) or []
        return len(track_list)

    # NumberOfBids (row 6)
    if df_name == "NumberOfBids":
        offers = data.get("offers", []) or []
        return len(offers)

    # HighestBidLowestBid (row 8)
    if df_name == "HighestBidLowestBid":
        offers = data.get("offers", []) or []
        amounts = []
        for offer in offers:
            try:
                amounts.append(float(offer["amount"]))
            except (ValueError, KeyError, TypeError):
                continue
        if len(amounts) < 2:
            return 0.0
        return max(amounts) - min(amounts)

    # HasLastTransaction (row 9)
    if df_name == "HasLastTransaction":
        sale_history = data.get("asset", {}).get("sale_history", []) or []
        return 1 if sale_history else 0

    # Income_Type_* (rows 10-23)
    if df_name.startswith("Income_Type_"):
        target_name = normalize_income_type_name(df_name)
        income_types = data.get("valuation", {}).get("top_income_types", []) or []
        for entry in income_types:
            actual_name = entry.get("name", "").strip().upper()
            actual_name = re.sub(r'\s+', ' ', actual_name)
            if actual_name == target_name:
                return entry.get("earnings")
        return None

    # Last12Months (row 24)
    if df_name == "Last12Months":
        return data.get("valuation", {}).get("ltm")

    # EarningsSinceStart (row 25)
    if df_name == "EarningsSinceStart":
        return data.get("valuation", {}).get("lifetime_amount")

    # 3YearAverage (row 26)
    if df_name == "3YearAverage":
        return data.get("valuation", {}).get("three_years_average")

    # DollarAge (row 27)
    if df_name == "DollarAge":
        return data.get("valuation", {}).get("dollar_age")

    # Fallback for any unexpected factor
    return None


def main():
    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    xlsx_path = os.path.join(project_dir, "Factor List.xlsx")
    input_dir = os.path.join(project_dir, "resources", "new_original")
    output_dir = os.path.join(project_dir, "analysis", "new_step_2")

    # Read factor list
    factor_list = read_factor_list(xlsx_path)
    print(f"Factor List loaded: {len(factor_list)} factors (rows 2-41)")

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Process JSON files
    total = 0
    errors = 0
    error_files = []

    for filename in sorted(os.listdir(input_dir)):
        if not filename.endswith('.json'):
            continue

        input_path = os.path.join(input_dir, filename)
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            output = {}
            for factor in factor_list:
                output[factor["df_name"]] = extract_factor(data, factor)

            output_path = os.path.join(output_dir, filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            total += 1

        except Exception as e:
            print(f"  ERROR: {filename} - {e}")
            errors += 1
            error_files.append(filename)

    # Summary
    print(f"\nDone.")
    print(f"Processed: {total}")
    print(f"Errors:    {errors}")
    if error_files:
        print("Error files:")
        for ef in error_files:
            print(f"  - {ef}")


if __name__ == "__main__":
    main()
