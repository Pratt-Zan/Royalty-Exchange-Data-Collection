import os
import requests
import json


def fetch_listing_api(asset_id: int, output_dir: str) -> str:
    """Fetch listing data from Royalty Exchange API and save to JSON file.

    Args:
        asset_id: The asset ID to fetch listing for.
        output_dir: Directory path to save the output JSON file.

    Returns:
        Path to the saved JSON file, or None on failure.
    """
    url = f"https://auctions.royaltyexchange.com/orderbook/api/listings/{asset_id}/"

    params = {
        "include[]": [
            "asset.*",
            "valuation_description.*",
            "offers.*"
        ]
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        print("Status Code:", response.status_code)

        # 转 json
        data = response.json()

        # 打印
        print(json.dumps(data, indent=2, ensure_ascii=False))

        # 保存
        output_path = os.path.join(output_dir, f"{asset_id}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Saved to {output_path}")
        return output_path

    except Exception as e:
        print(f"Error fetching listing for asset {asset_id}: {e}")
        return None


if __name__ == "__main__":
    fetch_listing_api(6498, "resources/new")
