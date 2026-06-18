# Make sure to install: pip install playwright beautifulsoup4 lxml
import asyncio
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def scrape_asset_page(asset_id: int, output_dir: str) -> str | None:
    # Use async_playwright() to enter async mode
    url = f"https://auctions.royaltyexchange.com/orderbook/asset-detail/{asset_id}/"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{asset_id}.html")

    async with async_playwright() as p:
        
        # Launch browser in headless mode
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        
        # Set context
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        # Create new page
        page = await context.new_page()
        
        print(f"Loading dynamic page: {url} ...")
        print("Waiting for JavaScript to render...")
        
        try:
            # 1. Loading
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 2. Waiting for Royalties section to appear
            print("正在等待网页渲染 Royalties 数据板块...")
            await page.wait_for_selector('div[name="Royalties"]', state='attached', timeout=30000)
            print("成功捕捉到 Royalties 板块！")

            # 3. Gain the html content
            html_content = await page.content()
            
            # Use BeautifulSoup to prettify HTML
            soup = BeautifulSoup(html_content, 'lxml')
            pretty_html = soup.prettify()
            
            # Save prettified HTML
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(pretty_html)
            
            print(f"HTML content saved to [{output_file}]")
            
            return output_file
            
        except Exception as e:
            print(f"Error loading page: {e}")
            return None
            
        finally:
            # Ensure browser closes
            await browser.close()
            print("Browser closed.")

# ==========================================
# Main execution area
# ==========================================
async def main():
    result = await scrape_asset_page(5986, "resources/new")
    
    if result:
        print(f"\nSuccessfully saved to: {result}")
    else:
        print("\nFailed to scrape asset page")

if __name__ == "__main__":
    asyncio.run(main())