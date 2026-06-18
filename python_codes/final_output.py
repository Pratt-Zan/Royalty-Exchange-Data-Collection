import os
import json
import csv
import shutil
from pathlib import Path

def merge_folders_and_generate_csv(folder1, folder2, output_folder, csv_file):
    """
    合并两个文件夹并生成CSV文件到指定位置
    
    Args:
        folder1: 第一个文件夹路径
        folder2: 第二个文件夹路径
        output_folder: 输出文件夹路径（存放合并后的文件）
        csv_file: CSV文件完整路径（单独的位置）
    """
    # 1. 合并文件夹
    print(f"开始合并文件夹...")
    os.makedirs(output_folder, exist_ok=True)
    
    for folder in [folder1, folder2]:
        if os.path.exists(folder):
            for file in os.listdir(folder):
                src = os.path.join(folder, file)
                dst = os.path.join(output_folder, file)
                if os.path.isfile(src):
                    if os.path.exists(dst):
                        name, ext = os.path.splitext(file)
                        dst = os.path.join(output_folder, f"{name}_copy{ext}")
                    shutil.copy2(src, dst)
    
    print("文件夹合并完成")
    
    # 2. 处理JSON文件并生成CSV
    json_files = list(Path(output_folder).glob('*.json'))
    if not json_files:
        print("没有找到JSON文件")
        return
    
    print(f"找到 {len(json_files)} 个JSON文件，开始处理...")
    
    all_data = []
    standard_keys = None
    error_count = 0
    field_order = []  # 用于记录字段顺序
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if standard_keys is None:
                standard_keys = set(data.keys())
                # 记录第一个JSON文件的字段顺序
                field_order = list(data.keys())
            
            current_keys = set(data.keys())
            if current_keys != standard_keys:
                missing = standard_keys - current_keys
                extra = current_keys - standard_keys
                print(f"⚠ {json_file.name} 格式不一致")
                if missing:
                    print(f"  缺少: {missing}")
                if extra:
                    print(f"  多余: {extra}")
                error_count += 1
            # 正确的就不打印任何信息
            
            data['filename'] = json_file.name
            all_data.append(data)
            
        except Exception as e:
            print(f"✗ 读取 {json_file.name} 失败: {e}")
            error_count += 1
    
    # 3. 生成CSV到指定位置
    if not all_data:
        print("没有有效数据生成CSV")
        return
    
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)
    
    # 按文件名中的数字排序（假设文件名是数字.json，如 1.json, 2.json, 10.json）
    def extract_number(filename):
        try:
            return int(Path(filename).stem)
        except ValueError:
            # 如果文件名不是纯数字，按字符串排序
            return filename
    
    all_data.sort(key=lambda x: extract_number(x['filename']))
    
    # 构建列顺序：filename 在第一列，其他列按照第一个JSON文件的顺序
    all_keys = ['filename']
    # 将第一个JSON文件的字段顺序添加进来（排除filename，因为它是后来添加的）
    for key in field_order:
        if key not in all_keys:
            all_keys.append(key)
    
    # 如果有其他JSON文件有多余的字段，也加在后面
    for data in all_data:
        for key in data.keys():
            if key not in all_keys:
                all_keys.append(key)
    
    with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(all_data)
    
    print(f"\n完成! 共生成 {len(all_data)} 行数据到: {csv_file}")
    if error_count > 0:
        print(f"警告: {error_count} 个文件格式不一致")

# 使用示例
if __name__ == "__main__":
    merge_folders_and_generate_csv(
        folder1="C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\analysis\\new_step_3",
        folder2="C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\analysis\\old_step_5",
        output_folder="C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\analysis\\final",
        csv_file="C:\\Users\\Pratt\\Desktop\\HKUST-RA\\Data Collection Royalty exchange\\final_output.csv"
    )