import os
import shutil

# Manual mapping: slug -> numeric ID for buy-it-now files (no auctionId in HTML)
BUY_IT_NOW_MAP = {
    "buy-it-now-brand-new-hip-hop-releases": 11,
    "buy-it-now-indie-electropop-lolawolf": 20,
    "buy-it-now-international-k-pop-catalog": 17,
    "buy-it-now-platinum-hit-from-zendaya-replay-more": 2,
    "buy-it-now-production-music-in-emmy-winning-series": 7,
    "buy-it-now-rb-pop-catalog-featuring-trey-songz": 1,
}


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    step4_dir = os.path.join(project_dir, "analysis", "old_step_4")
    step3_dir = os.path.join(project_dir, "analysis", "old_step_3")
    output_dir = os.path.join(project_dir, "analysis", "old_step_5")

    os.makedirs(output_dir, exist_ok=True)

    # 1) Copy all 809 files from step_4
    for fname in os.listdir(step4_dir):
        if fname.endswith(".json"):
            shutil.copy2(
                os.path.join(step4_dir, fname),
                os.path.join(output_dir, fname),
            )

    # 2) Add the 6 manually mapped buy-it-now files
    for slug, numeric_id in BUY_IT_NOW_MAP.items():
        src = os.path.join(step3_dir, f"{slug}.json")
        dst = os.path.join(output_dir, f"{numeric_id}.json")
        shutil.copy2(src, dst)

    total = len([f for f in os.listdir(output_dir) if f.endswith(".json")])
    print(f"Done. step_5 contains {total} files (809 from step_4 + 6 manually mapped)")


if __name__ == "__main__":
    main()
