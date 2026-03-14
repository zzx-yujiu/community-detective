import argparse
import os
import re
from typing import Dict, Any, List

import pandas as pd
import requests
from urllib.parse import quote


BASE_FIELD_MAPPING = {
    "帖子ID": "post_id",
    "帖子标题": "title",
    "帖子链接": "url",
    "作者": "author",
    "作者个人页链接": "author_url",
    "帖子内容（文本）": "content",
    "发布时间": "publish_time",
    "浏览量信息": "views",
}

AI_FIELD_MAPPING = {
    "内容类型": "content_type",
    "情感标签": "sentiment",
}


def clean_views(value: Any) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    numbers = re.findall(r"\d+", str(value))
    return int(numbers[0]) if numbers else 0


def format_publish_time(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            return s
        return dt.to_pydatetime().isoformat(sep=" ", timespec="seconds")
    except Exception:
        return s


def build_row_payload(row: pd.Series, columns: List[str], field_mapping: Dict[str, str]) -> Dict[str, Any]:
    payload = {}
    for excel_col, db_field in field_mapping.items():
        if excel_col in columns:
            cell = row[excel_col]
            if db_field == "views":
                payload[db_field] = clean_views(cell)
            elif db_field == "publish_time":
                payload[db_field] = format_publish_time(cell)
            else:
                payload[db_field] = None if pd.isna(cell) else str(cell)
        else:
            payload[db_field] = None
    return payload


def upload_excel(
    excel_path: str,
    supabase_url: str,
    supabase_key: str,
    table_name: str = "community_posts",
    start_row: int = 2,
    batch_size: int = 200,
    upsert: bool = False,
    conflict_column: str = "post_id",
    include_ai_columns: bool = False,
) -> Dict[str, Any]:
    if not excel_path or not isinstance(excel_path, str):
        raise ValueError("Excel文件路径不能为空且必须是字符串类型")
    excel_path = os.path.normpath(excel_path)
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel文件不存在：{excel_path}")
    if not os.path.isfile(excel_path):
        raise ValueError(f"指定路径不是文件：{excel_path}")
    ext = os.path.splitext(excel_path)[1].lower()
    if ext not in [".xlsx", ".xls"]:
        raise ValueError(f"不支持的文件格式：{ext}")

    df = pd.read_excel(excel_path)
    if df.empty:
        raise ValueError("Excel文件为空")

    encoded_table = quote(table_name, safe="")
    api_url = f"{supabase_url}/rest/v1/{encoded_table}"
    if upsert:
        api_url = f"{api_url}?on_conflict={conflict_column}"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal" + (",resolution=merge-duplicates" if upsert else ""),
    }

    success_count = 0
    failed_count = 0
    failed_rows = []
    error_logs = []

    field_mapping = dict(BASE_FIELD_MAPPING)
    if include_ai_columns:
        field_mapping.update(AI_FIELD_MAPPING)

    missing_columns = [c for c in field_mapping.keys() if c not in df.columns]
    if missing_columns:
        error_logs.append(f"警告：Excel缺少列：{missing_columns}")

    if batch_size < 1:
        batch_size = 1

    session = requests.Session()

    def redact(text: str) -> str:
        if not text:
            return ""
        out = str(text)
        if supabase_key:
            out = out.replace(supabase_key, "<REDACTED>")
        out = re.sub(r"eyJ[a-zA-Z0-9_\-\.]+", "<REDACTED_JWT>", out)
        return out

    def post_payload(payload, row_number: int):
        nonlocal success_count, failed_count
        try:
            resp = session.post(api_url, headers=headers, json=payload, timeout=30)
            if resp.status_code in [200, 201]:
                success_count += 1
                return
            failed_count += 1
            failed_rows.append(row_number)
            error_logs.append(f"第{row_number}行上传失败: {resp.status_code} {redact(resp.text)[:300]}")
        except Exception as e:
            failed_count += 1
            failed_rows.append(row_number)
            error_logs.append(f"第{row_number}行上传异常: {str(e)}")

    start_index = max(start_row - 2, 0)
    rows = df.iloc[start_index:]
    cols = df.columns.tolist()

    current_batch = []
    current_batch_rows = []

    for index, row in rows.iterrows():
        excel_row_number = index + 2
        current_batch.append(build_row_payload(row, cols, field_mapping))
        current_batch_rows.append(excel_row_number)

        if len(current_batch) < batch_size:
            continue

        try:
            resp = session.post(api_url, headers=headers, json=current_batch, timeout=60)
            if resp.status_code in [200, 201]:
                success_count += len(current_batch)
            else:
                error_logs.append(f"批量上传失败: {resp.status_code} {redact(resp.text)[:300]}")
                for p, rn in zip(current_batch, current_batch_rows):
                    post_payload(p, rn)
        except Exception as e:
            error_logs.append(f"批量上传异常: {str(e)}")
            for p, rn in zip(current_batch, current_batch_rows):
                post_payload(p, rn)
        current_batch = []
        current_batch_rows = []

    if current_batch:
        try:
            resp = session.post(api_url, headers=headers, json=current_batch, timeout=60)
            if resp.status_code in [200, 201]:
                success_count += len(current_batch)
            else:
                error_logs.append(f"批量上传失败: {resp.status_code} {redact(resp.text)[:300]}")
                for p, rn in zip(current_batch, current_batch_rows):
                    post_payload(p, rn)
        except Exception as e:
            error_logs.append(f"批量上传异常: {str(e)}")
            for p, rn in zip(current_batch, current_batch_rows):
                post_payload(p, rn)

    session.close()

    log_path = ""
    if error_logs:
        log_path = os.path.join(os.path.dirname(excel_path), "upload_errors.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(error_logs))

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "failed_rows": failed_rows,
        "error_logs": error_logs[:20],
        "log_path": log_path,
        "total_processed": success_count + failed_count,
    }

def load_supabase_env_from_ps1(ps1_path: str) -> Dict[str, str]:
    ps1_path = os.path.normpath(ps1_path)
    if not os.path.exists(ps1_path):
        raise FileNotFoundError(f"环境变量脚本不存在：{ps1_path}")
    text = open(ps1_path, "r", encoding="utf-8").read()
    m_url = re.search(r'\$env:SUPABASE_URL\s*=\s*"([^"]+)"', text)
    m_key = re.search(r'\$env:SUPABASE_KEY\s*=\s*"([^"]+)"', text)
    return {
        "url": m_url.group(1).strip() if m_url else "",
        "key": m_key.group(1).strip() if m_key else "",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", required=True)
    parser.add_argument("--url", required=False, default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--key", required=False, default=os.environ.get("SUPABASE_KEY"))
    parser.add_argument("--table", required=False, default="community_posts")
    parser.add_argument("--start-row", required=False, type=int, default=2)
    parser.add_argument("--batch-size", required=False, type=int, default=200)
    parser.add_argument("--upsert", action="store_true")
    parser.add_argument("--conflict-column", required=False, default="post_id")
    parser.add_argument("--env-ps1", required=False, default="")
    parser.add_argument("--include-ai-columns", action="store_true")
    args = parser.parse_args()

    url = args.url
    key = args.key
    if (not url or not key) and args.env_ps1:
        env = load_supabase_env_from_ps1(args.env_ps1)
        url = url or env["url"]
        key = key or env["key"]
    if not url or not key:
        raise ValueError("缺少Supabase URL或Key，请通过参数、环境变量或--env-ps1提供")

    result = upload_excel(
        excel_path=args.excel,
        supabase_url=url,
        supabase_key=key,
        table_name=args.table,
        start_row=args.start_row,
        batch_size=args.batch_size,
        upsert=args.upsert,
        conflict_column=args.conflict_column,
        include_ai_columns=args.include_ai_columns,
    )
    print(result)


if __name__ == "__main__":
    main()
