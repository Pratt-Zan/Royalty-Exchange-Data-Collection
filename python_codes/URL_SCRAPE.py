import asyncio
import csv
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def fetch_and_save_sitemap(sitemap_url, filename="urls_lastmod.csv"):
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        print(f"正在访问: {sitemap_url}")
        
        try:
            response = await page.goto(sitemap_url, wait_until="domcontentloaded")
            
            if response and response.ok:
                xml_content = await response.text()
                soup = BeautifulSoup(xml_content, 'xml')
                
                # 准备存储数据的列表
                data_to_save = []
                
                # 遍历所有 url 节点
                for url_node in soup.find_all('url'):
                    lastmod_node = url_node.find('lastmod')
                    # 仅提取带有 lastmod 的项
                    if lastmod_node:
                        loc = url_node.find('loc').text if url_node.find('loc') else ""
                        lastmod = lastmod_node.text
                        data_to_save.append([loc, lastmod])
                
                # 执行保存操作
                if data_to_save:
                    save_to_csv(data_to_save, filename)
                    print(f"\n✅ 抓取完成！")
                    print(f"📁 结果已保存至: {filename}")
                    print(f"📊 总计记录数: {len(data_to_save)}")
                else:
                    print("❌ 未发现带有 lastmod 的 URL。")
            else:
                print(f"访问失败，状态码: {response.status if response else '未知'}")
                
        except Exception as e:
            print(f"发生错误: {e}")
        finally:
            await browser.close()

def save_to_csv(data, filename):
    """将数据写入 CSV 文件"""
    header = ['URL', 'Last_Modified']
    with open(filename, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)  # 写入表头
        writer.writerows(data)    # 写入所有行

async def main():
    target_url = "https://auctions.royaltyexchange.com/sitemap.xml"
    await fetch_and_save_sitemap(target_url)

if __name__ == "__main__":
    asyncio.run(main())