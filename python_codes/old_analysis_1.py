import os
import json
import re
from bs4 import BeautifulSoup


def extract_royalties(html_file_path):
    """
    Extract the "What rights are included?" table from an old-format HTML file.

    Returns a dict with "table" and "ascap" keys matching the reference format,
    or None if the rights table is not found.
    """
    with open(html_file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    # ---- Step 1: Locate the rights table ----
    # The heading can be <h3> or <h4> (or any h1-h4)
    heading = soup.find(re.compile(r'h[1-4]'), string=re.compile(
        r'What rights are included', re.IGNORECASE))
    if not heading:
        return None

    # Find the outer <table class="crdt"> (not inner tables)
    table = heading.find_next('table', class_='crdt')
    if not table:
        return None

    result = {"table": [], "ascap": {}}

    # ---- Step 2: Parse the header row ----
    # The header lives in <thead>
    thead = table.find('thead')
    if thead:
        th_cells = thead.find_all('th')
        header_row = []
        for th in th_cells:
            text = th.get_text(strip=True)
            # Non-empty <th> cells hold type names and are "included"
            if text:
                highlighted = [text]
            else:
                highlighted = None
            header_row.append({
                "text": text,
                "highlighted": highlighted,
            })
    else:
        # Fallback if <thead> is missing
        header_row = [
            {"text": "Type", "highlighted": None},
            {"text": "Musical Composition", "highlighted": ["Musical Composition"]},
            {"text": "Sound Recording", "highlighted": None},
        ]

    # Ensure the first cell is always the "Type" label
    # The <thead> often has an empty first <th>; replace it with "Type"
    if len(header_row) > 0:
        if header_row[0]["text"] == "":
            header_row[0]["text"] = "Type"
        else:
            header_row.insert(0, {"text": "Type", "highlighted": None})

    result["table"].append(header_row)

    # ---- Step 3: Parse <tbody> rows ----
    tbody = table.find('tbody')
    if not tbody:
        return None

    rows = tbody.find_all('tr', recursive=False)
    # Expected row count: 4 (copyrights, rights, sources, distributors)

    for row_idx, row in enumerate(rows):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 2:
            continue  # skip malformed rows

        # --- Label cell (always first) ---
        label_cell = cells[0]
        label_text = label_cell.get_text(strip=True)
        # Map label to standardised row-0 label
        if row_idx == 0:
            row_label = "Copyrights Included?"
        elif row_idx == 1:
            row_label = "Royalty Types"
        elif row_idx == 2:
            row_label = "Sources"
        elif row_idx == 3:
            row_label = "Distributors"
        else:
            row_label = label_text  # fallback for unexpected rows

        row_data = [
            {"text": row_label, "highlighted": None}
        ]

        # --- Process MC (col 1) and SR (col 2) ---
        for col_idx in (1, 2):
            if col_idx >= len(cells):
                # Column missing → empty cell
                row_data.append({
                    "text": "\u2014",
                    "highlighted": None,
                })
                continue

            cell = cells[col_idx]
            cell_classes = cell.get('class', [])
            is_not_included = 'not-included' in cell_classes

            if row_idx == 0:
                # ---- Copyrights included? ----
                text = cell.get_text(strip=True)
                if text in ('\u2014', '-', '', '\u2013'):
                    text = '\u2014'
                    highlighted = None
                elif text == 'No':
                    highlighted = ['No']
                else:
                    highlighted = None if is_not_included else ([text] if text else None)
                row_data.append({"text": text, "highlighted": highlighted})

            elif row_idx == 1:
                # ---- Rights / Royalty Types (may have inner table) ----
                inner_table = cell.find('table', class_='crdt inner')
                if inner_table:
                    all_items = []
                    included_items = []
                    for td in inner_table.find_all('td'):
                        item_text = td.get_text(strip=True)
                        if item_text:
                            all_items.append(item_text)
                            td_classes = td.get('class', [])
                            if 'not-included' not in td_classes:
                                included_items.append(item_text)
                    text = ' | '.join(all_items)
                    highlighted = included_items if included_items else None
                else:
                    # Plain cell (no inner table)
                    text = cell.get_text(strip=True)
                    if text in ('\u2014', '-', '', '\u2013'):
                        text = '\u2014'
                        highlighted = None
                    else:
                        highlighted = None if is_not_included else ([text] if text else None)
                row_data.append({"text": text, "highlighted": highlighted})

            elif row_idx == 2:
                # ---- Sources ----
                text = cell.get_text(strip=True)
                if text in ('\u2014', '-', '', '\u2013'):
                    text = '\u2014'
                    highlighted = None
                else:
                    highlighted = None if is_not_included else ([text] if text else None)
                row_data.append({"text": text, "highlighted": highlighted})

            elif row_idx == 3:
                # ---- Distributors ----
                text = cell.get_text(strip=True)
                if text in ('\u2014', '-', '', '\u2013'):
                    text = '\u2014'
                    highlighted = None
                else:
                    highlighted = None if is_not_included else ([text] if text else None)
                row_data.append({"text": text, "highlighted": highlighted})

            else:
                # Fallback for extra rows
                text = cell.get_text(strip=True)
                highlighted = None if is_not_included else ([text] if text else None)
                row_data.append({"text": text, "highlighted": highlighted})

        result["table"].append(row_data)

    # ---- Step 4: ASCAP description ----
    # Check if any distributor cell contains "ASCAP"
    has_ascap = False
    for row in result["table"]:
        for cell in row:
            if 'ASCAP' in cell.get('text', ''):
                has_ascap = True
                break
        if has_ascap:
            break

    if has_ascap:
        # Try to find "About the Royalty Distributor" heading
        dist_heading = soup.find(
            re.compile(r'h[1-4]'),
            string=re.compile(r'About the Royalty Distributor', re.IGNORECASE),
        )
        if dist_heading:
            # Collect all content until the next heading
            paragraphs = []
            links = []
            for sibling in dist_heading.find_next_siblings():
                if sibling.name and re.match(r'h[1-4]', sibling.name):
                    break
                if sibling.name == 'p':
                    paragraphs.append(sibling.get_text(separator=' ', strip=True))
                    for a in sibling.find_all('a'):
                        href = a.get('href')
                        if href:
                            links.append(href)

            if paragraphs:
                result["ascap"] = {
                    "description": ' '.join(paragraphs),
                    "links": links,
                }

    return result


# ========== Batch processing ==========

if __name__ == '__main__':
    input_folder = (
        r"C:\Users\Pratt\Desktop\HKUST-RA\Data Collection Royalty exchange"
        r"\resources\old"
    )
    output_folder = (
        r"C:\Users\Pratt\Desktop\HKUST-RA\Data Collection Royalty exchange"
        r"\analysis\old_step_1"
    )

    os.makedirs(output_folder, exist_ok=True)

    success_count = 0
    skip_count = 0
    error_count = 0

    for filename in sorted(os.listdir(input_folder)):
        if not filename.endswith('.html'):
            continue

        input_path = os.path.join(input_folder, filename)
        output_filename = filename.replace('.html', '.json')
        output_path = os.path.join(output_folder, output_filename)

        print(f"Processing: {filename}")

        try:
            data = extract_royalties(input_path)
            if data:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  \u2713 Saved: {output_filename}")
                success_count += 1
            else:
                print(f"  \u2014 Skipped (no rights table): {filename}")
                skip_count += 1
        except Exception as e:
            print(f"  \u2717 Failed: {filename} - {e}")
            error_count += 1

    print(
        f"\nDone! Success: {success_count}, Skipped: {skip_count}, Errors: {error_count}"
    )
    print(f"Total files: {success_count + skip_count + error_count}")
