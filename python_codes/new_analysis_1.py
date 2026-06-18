import os
import json
from bs4 import BeautifulSoup

def extract_royalties(html_file_path):
    with open(html_file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    
    # 找到 Royalties 板块
    section = soup.find('div', {'name': 'Royalties'})
    if not section:
        return None
    
    result = {"table": [], "ascap": {}}
    
    # 提取表格
    table = section.find('table')
    if table:
        # 表头
        # headers = [th.get_text(strip=True) for th in table.find_all('th')]
        # result["table"].append(headers)
        header_row = []
        for th in table.find_all('th'):
            text = th.get_text(strip=True)
            cell_bold = 'cell-bold' in th.get('class', [])
            highlighted = [text] if cell_bold else None
            header_row.append({
                "text": text,
                "highlighted": highlighted
            })
        result["table"].append(header_row)
        
        # 表格内容
        for row in table.find_all('tr')[1:]:
            row_data = []
            for cell in row.find_all('td'):
                # 检查 cell 本身是否有 cell-bold 类
                cell_bold = 'cell-bold' in cell.get('class', [])
                
                # 检查子元素中的 cell-bold
                child_bold_spans = cell.find_all(class_='cell-bold')
                child_bold_texts = [span.get_text(strip=True) for span in child_bold_spans]
                
                # 合并：如果 cell 本身加粗，整个文本都标记；否则只标记子元素中的加粗部分
                if cell_bold:
                    highlighted = [cell.get_text(strip=True)]
                else:
                    highlighted = child_bold_texts if child_bold_texts else None
                
                # 获取所有文本
                text = cell.get_text(separator=' | ', strip=True)
                
                row_data.append({
                    "text": text,
                    "highlighted": highlighted
                })
            if row_data:
                result["table"].append(row_data)
    
    # 提取 ASCAP 信息
    ascap_div = section.find('div', class_='jss120')
    if ascap_div:
        links = ascap_div.find_all('a')
        result["ascap"] = {
            "description": ascap_div.get_text(separator=' ', strip=True),
            "links": [link.get('href') for link in links]
        }
    
    return result

# ========== 批量处理 ==========

# 配置路径
input_folder = "C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\resources\\new_original"
output_folder = "C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\analysis\\new_step_1"

# 确保输出文件夹存在
os.makedirs(output_folder, exist_ok=True)

# 遍历所有 html 文件
success_count = 0
fail_count = 0

for filename in os.listdir(input_folder):
    if filename.endswith('.html'):
        input_path = os.path.join(input_folder, filename)
        output_filename = filename.replace('.html', '.json')
        output_path = os.path.join(output_folder, output_filename)
        
        print(f"正在处理: {filename}")
        
        try:
            data = extract_royalties(input_path)
            if data:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  ✓ 已保存: {output_filename}")
                success_count += 1
            else:
                print(f"  ✗ 未找到 Royalties 板块: {filename}")
                fail_count += 1
        except Exception as e:
            print(f"  ✗ 处理失败: {filename} - {e}")
            fail_count += 1

print(f"\n完成！成功: {success_count}, 失败: {fail_count}")