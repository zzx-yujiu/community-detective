import pandas as pd
import json
import re

file_path = r"d:\新训\第一周\社区侦探项目\社区侦探项目-AI打标.xlsx"
output_path = r"d:\新训\第一周\社区侦探项目\dashboard_data.js"

def clean_views(val):
    if pd.isna(val):
        return 0
    s = str(val)
    nums = re.findall(r'\d+', s)
    return int(nums[0]) if nums else 0

def clean_date(val):
    if pd.isna(val):
        return ""
    return str(val)

try:
    df = pd.read_excel(file_path)
    
    # Map columns
    records = []
    for _, row in df.iterrows():
        record = {
            "title": row.get("帖子标题", ""),
            "url": row.get("帖子链接", ""),
            "author": row.get("作者", ""),
            "publish_time": clean_date(row.get("发布时间")),
            "views": clean_views(row.get("浏览量信息")),
            "content_type": row.get("内容类型", "未分类"),
            "sentiment": row.get("情感标签", "中性")
        }
        records.append(record)
    
    json_str = json.dumps(records, ensure_ascii=False, indent=2)
    js_content = f"const localData = {json_str};\nconsole.log('Local data loaded:', localData.length, 'records');"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(js_content)
    
    print(f"Successfully created {output_path} with {len(records)} records.")

except Exception as e:
    print(f"Error converting: {e}")
