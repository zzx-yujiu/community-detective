import os
import requests
import json
import re

def load_env(ps1_path):
    with open(ps1_path, "r", encoding="utf-8") as f:
        content = f.read()
    url = re.search(r'\$env:SUPABASE_URL\s*=\s*"([^"]+)"', content).group(1)
    key = re.search(r'\$env:SUPABASE_KEY\s*=\s*"([^"]+)"', content).group(1)
    return url, key

try:
    url, key = load_env("set_supabase_env.ps1")
    print(f"URL: {url}")
    # 隐藏部分 key
    print(f"Key: {key[:10]}...")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    # 尝试读取 '影刀社区帖子' 表
    table_name = "影刀社区帖子"
    api_url = f"{url}/rest/v1/{table_name}?select=*&limit=5"
    
    print(f"\n正在尝试请求: {api_url}")
    response = requests.get(api_url, headers=headers)
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"读取成功，获取到 {len(data)} 条数据")
        if len(data) > 0:
            print("第一条数据示例 (检查字段名):")
            print(json.dumps(data[0], ensure_ascii=False, indent=2))
        else:
            print("警告：返回了空数组。可能是表为空，或者 RLS 策略未开启导致无法读取。")
    else:
        print(f"读取失败: {response.text}")

except Exception as e:
    print(f"发生错误: {e}")
