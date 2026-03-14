import json
import os
import requests

AP_CONTENT_URL = "https://power-api.yingdao.com/oapi/power/v1/rest/flow/dd093840-4bac-4af8-afc0-23d8ac46f666/execute"
AP_SENTIMENT_URL = "https://power-api.yingdao.com/oapi/power/v1/rest/flow/4aad96bc-b721-4475-90b4-46a7d6e6f6d8/execute"


def test_one(name: str, url: str, token: str, text: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"input": {"input_text_0": text}}
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    body_text = response.text
    try:
        body_json = response.json()
    except Exception:
        body_json = {"raw": body_text[:500]}
    return {
        "name": name,
        "status_code": response.status_code,
        "ok": response.ok,
        "body": body_json,
    }


def main():
    token = os.environ.get("AP_TOKEN", "").strip()
    if not token:
        raise ValueError("缺少 AP_TOKEN 环境变量")

    sample_text = "影刀RPA 自动化方案实践分享，流程稳定，效率显著提升。"
    results = [
        test_one("content", AP_CONTENT_URL, token, sample_text),
        test_one("sentiment", AP_SENTIMENT_URL, token, sample_text),
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
