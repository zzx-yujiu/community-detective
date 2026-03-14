import os
import json
import requests

API_URL = "https://power-api.yingdao.com/oapi/power/v1/rest/flow/4aad96bc-b721-4475-90b4-46a7d6e6f6d8/execute"
TOKEN = os.environ.get("AP_TOKEN", "")

def query(text):
    if not TOKEN:
        raise ValueError("Missing AP_TOKEN")
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"input": {"input_text_0": text}}
    response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    sample = "示例文本"
    result = query(sample)
    print(json.dumps(result, ensure_ascii=False, indent=2))
