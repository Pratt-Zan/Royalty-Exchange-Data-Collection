import os
import json


def keyword_in_highlighted(cell, keyword):
    """Check if keyword exists in any element of cell's highlighted array (substring match, case-insensitive)."""
    highlighted = cell.get("highlighted")
    if highlighted is None:
        return False
    keyword_lower = keyword.lower()
    for item in highlighted:
        if keyword_lower in item.lower():
            return True
    return False


def fill_rows_28_to_41(step1_data, step2_data, file_exists_in_both):
    """Return a copy of step2_data with rows 28-41 filled."""
    result = dict(step2_data)

    # Row 28: CopyrightsIncluded_Yes
    result["CopyrightsIncluded_Yes"] = 1 if file_exists_in_both else 0

    # Default all rows 29-41 to 0
    fields_29_to_41 = [
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
    for key in fields_29_to_41:
        result[key] = 0

    # If no step1_data, return zeros for 29-41
    if step1_data is None:
        return result

    # Try to compute from table
    try:
        table = step1_data.get("table")
        if table is None or len(table) < 5:
            return result

        # Rows 29-30: Type (table[0])
        row0 = table[0]
        cell0_1 = row0[1] if len(row0) > 1 else None
        cell0_2 = row0[2] if len(row0) > 2 else None
        h0_1 = cell0_1.get("highlighted") if cell0_1 else None
        h0_2 = cell0_2.get("highlighted") if cell0_2 else None

        result["Type_xroyaltyType_MusicalCompositionSoundRecording"] = 1 if (h0_1 is not None and h0_2 is not None) else 0
        result["Type_xroyaltyType_SoundRecording"] = 1 if (h0_1 is None and h0_2 is not None) else 0

        # Rows 31-32: Royalty Types (table[2])
        row2 = table[2]
        cell2_1 = row2[1] if len(row2) > 1 else None
        cell2_2 = row2[2] if len(row2) > 2 else None

        result["Rights_Public_Performance"] = 1 if (cell2_1 and keyword_in_highlighted(cell2_1, "Public Performance")) else 0
        result["Rights_Sync"] = 1 if (
            (cell2_1 and keyword_in_highlighted(cell2_1, "Sync")) or
            (cell2_2 and keyword_in_highlighted(cell2_2, "Sync"))
        ) else 0

        # Rows 33-37: Distributors (table[4])
        row4 = table[4]
        cell4_1 = row4[1] if len(row4) > 1 else None
        cell4_2 = row4[2] if len(row4) > 2 else None

        result["Distributor_universal"] = 1 if (
            (cell4_1 and keyword_in_highlighted(cell4_1, "Universal Music Publishing Group")) or
            (cell4_2 and keyword_in_highlighted(cell4_2, "Universal Music Publishing Group"))
        ) else 0
        result["Distributor_bmi"] = 1 if (
            (cell4_1 and keyword_in_highlighted(cell4_1, "BMI")) or
            (cell4_2 and keyword_in_highlighted(cell4_2, "BMI"))
        ) else 0
        result["Distributor_ascap"] = 1 if (
            (cell4_1 and keyword_in_highlighted(cell4_1, "ASCAP")) or
            (cell4_2 and keyword_in_highlighted(cell4_2, "ASCAP"))
        ) else 0
        result["Distributor_sony"] = 1 if (
            (cell4_1 and keyword_in_highlighted(cell4_1, "Sony Music Publishing")) or
            (cell4_2 and keyword_in_highlighted(cell4_2, "Sony Music Publishing"))
        ) else 0
        result["Distributor_warner"] = 1 if (
            (cell4_1 and keyword_in_highlighted(cell4_1, "Warner Music Group")) or
            (cell4_2 and keyword_in_highlighted(cell4_2, "Warner Music Group"))
        ) else 0

        # Rows 38-41: Sources (table[3])
        row3 = table[3]
        cell3_1 = row3[1] if len(row3) > 1 else None
        cell3_2 = row3[2] if len(row3) > 2 else None

        result["Source_cd_sales"] = 1 if (
            (cell3_1 and keyword_in_highlighted(cell3_1, "CD Sales")) or
            (cell3_2 and keyword_in_highlighted(cell3_2, "CD Sales"))
        ) else 0
        result["Source tv_film"] = 1 if (
            (cell3_1 and keyword_in_highlighted(cell3_1, "TV/Film")) or
            (cell3_2 and keyword_in_highlighted(cell3_2, "TV/Film"))
        ) else 0
        result["Source_ satellite_radio"] = 1 if (
            (cell3_1 and keyword_in_highlighted(cell3_1, "Satellite Radio")) or
            (cell3_2 and keyword_in_highlighted(cell3_2, "Satellite Radio"))
        ) else 0
        result["Source_internet_streaming"] = 1 if (
            (cell3_1 and keyword_in_highlighted(cell3_1, "Internet Streaming")) or
            (cell3_2 and keyword_in_highlighted(cell3_2, "Internet Streaming"))
        ) else 0

    except Exception:
        # On any error, rows 29-41 stay 0 (already set)
        pass

    return result


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    step1_dir = os.path.join(project_dir, "analysis", "new_step_1")
    step2_dir = os.path.join(project_dir, "analysis", "new_step_2")
    output_dir = os.path.join(project_dir, "analysis", "new_step_3")

    os.makedirs(output_dir, exist_ok=True)

    # Get all JSON files in step_2 (process ALL step_2 files)
    step2_files = {f for f in os.listdir(step2_dir) if f.endswith(".json")}
    # Get filenames that exist in step_1
    step1_files = {f for f in os.listdir(step1_dir) if f.endswith(".json")}

    total_step2 = len(step2_files)
    success = 0
    errors = 0

    for filename in sorted(step2_files):
        step2_path = os.path.join(step2_dir, filename)
        try:
            with open(step2_path, "r", encoding="utf-8") as f:
                step2_data = json.load(f)
        except Exception as e:
            print(f"  ERROR reading step_2/{filename}: {e}")
            errors += 1
            continue

        file_exists_in_both = filename in step1_files
        step1_data = None
        if file_exists_in_both:
            step1_path = os.path.join(step1_dir, filename)
            try:
                with open(step1_path, "r", encoding="utf-8") as f:
                    step1_data = json.load(f)
            except Exception as e:
                print(f"  WARN: step_1/{filename} read error: {e}")

        filled = fill_rows_28_to_41(step1_data, step2_data, file_exists_in_both)

        output_path = os.path.join(output_dir, filename)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(filled, f, indent=2, ensure_ascii=False)

        success += 1
        if success % 200 == 0:
            print(f"  Progress: {success}/{total_step2} files processed...")

    print(f"\nDone. Processed: {success}, Errors: {errors}")


if __name__ == "__main__":
    main()
