import asyncio
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# --- Constants ---
LOGIN_URL = "https://app.royaltyexchange.com/auth/sign-in"
EMAIL = "<EMAIL>"
PASSWORD = "<PASSWORD>"


# --- Login flow ---
async def _handle_cookie_banner(page) -> None:
    """Accept Termly cookie consent banner if present."""
    try:
        accept_btn = page.locator('button[data-tid="banner-accept"]')
        if await accept_btn.is_visible(timeout=3000):
            await accept_btn.click()
            await page.wait_for_timeout(1000)
            print("Cookie consent accepted")
    except Exception:
        pass


async def login(context) -> bool:
    """Perform login on Royalty Exchange.

    Returns True if login succeeded, False otherwise.
    """
    try:
        page = await context.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        # Wait a bit for dynamic React form to render
        await page.wait_for_timeout(3000)

        # Accept cookie consent banner if present
        await _handle_cookie_banner(page)

        # Email field: id="sign-in-email" (Material-UI TextField, type="text")
        try:
            await page.fill("#sign-in-email", EMAIL, timeout=5000)
        except Exception:
            print("Could not find email field (#sign-in-email) on login page")
            await page.close()
            return False

        # Password field: id="sign-in-password"
        try:
            await page.fill("#sign-in-password", PASSWORD, timeout=5000)
        except Exception:
            print("Could not find password field (#sign-in-password) on login page")
            await page.close()
            return False

        # Submit button: MUI button[type="submit"] with text "Sign In"
        try:
            await page.click('button[type="submit"]', timeout=5000)
        except Exception:
            print("Could not find submit button on login page")
            await page.close()
            return False

        # Wait for navigation away from sign-in page (login processing)
        try:
            await page.wait_for_function(
                "() => !window.location.href.includes('/auth/sign-in')",
                timeout=30000,
            )
        except Exception:
            # If we timeout, check if still on login page (credentials wrong)
            pass

        # Check if we are still on login page (credentials might be wrong)
        current_url = page.url
        if "/auth/sign-in" in current_url:
            page_content = await page.content()
            page_text = await page.evaluate("() => document.body.innerText")
            if "Invalid" in page_text or "incorrect" in page_text.lower():
                print("Login failed: Invalid credentials or login error")
                await page.close()
                return False
            print("Login failed: stayed on sign-in page after submit")
            await page.close()
            return False

        # Login successful
        print("Login successful")
        await page.close()
        return True

    except Exception as e:
        print(f"Login error: {e}")
        return False


async def scrape_auction_page(url: str, output_dir: str, slug: str) -> str:
    os.makedirs(output_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )

        try:
            # Login fresh every time
            print("Logging in...")
            login_success = await login(context)
            if not login_success:
                print("Login failed. Cannot scrape page.")
                return None

            # Navigate to target auction page
            page = await context.new_page()
            
            # 1. 基础页面加载，只等 DOM 树建立，放弃等网络空闲 (networkidle)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # 2. 核心修复：精准狙击包含拍卖核心数据的那个 div 容器
            target_selector = "#id_tabbed_metadata"
            
            try:
                print(f"    Waiting for React to render {target_selector}...")
                # 只要这个带 ID 的 div 出现了，立刻触发下一步
                await page.wait_for_selector(target_selector, timeout=20000)
                
            except Exception as e:
                print(f"    [Warning] Target selector '{target_selector}' did not appear in time. Capturing anyway. Error: {e}")

            # Scrape the page
            html_content = await page.content()
            soup = BeautifulSoup(html_content, "lxml")
            pretty_html = soup.prettify()

            output_path = os.path.join(output_dir, f"{slug}.html")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(pretty_html)

            print(f"HTML content saved to {output_path}")
            return output_path

        except Exception as e:
            print(f"Error during scraping: {e}")
            return None
        finally:
            await browser.close()


if __name__ == "__main__":
    url = "https://auctions.royaltyexchange.com/auctions/tarquin-collection/"
    asyncio.run(
        scrape_auction_page(url, "resources/old", "tarquin-collection-login-test")
    )
