"""读取飞书多维表格记录 —— 用于排查自动化链路。

前置：.env 已配 FEISHU_APP_ID / FEISHU_APP_SECRET
     （app_token / table_id 默认用当前项目，可用参数覆盖）
用法：
  python tools/feishu_bitable_records.py
"""

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402

APP_TOKEN = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
TABLE_ID = os.environ.get("FEISHU_BITABLE_TABLE_ID", "")


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = config.TRUST_ENV_PROXY
    return s


def get_token() -> str:
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not (app_id and app_secret):
        raise SystemExit("请先在 .env 配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
    data = _session().post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    ).json()
    if not data.get("tenant_access_token"):
        raise SystemExit(f"获取 token 失败：{data}")
    return data["tenant_access_token"]


def main() -> None:
    if not (APP_TOKEN and TABLE_ID):
        raise SystemExit("请先在 .env 配置 FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_TABLE_ID")
    token = get_token()
    resp = _session().get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 20},
        timeout=20,
    )
    data = resp.json()
    print("HTTP", resp.status_code)
    print("接口返回：", json.dumps(data, ensure_ascii=False)[:600])

    if data.get("code") != 0:
        print("\n⚠️ 读取失败。常见原因：")
        print("  · 应用未加为该多维表格的「文档应用」（...→...更多→添加文档应用）")
        print("  · 应用未开通 bitable:app 权限，或权限未随版本发布")
        return

    items = data.get("data", {}).get("items", []) or []
    print(f"\n共 {len(items)} 条记录：")
    for it in items:
        print(f"\n  record_id = {it.get('record_id')}")
        print(f"  fields    = {json.dumps(it.get('fields', {}), ensure_ascii=False)}")


if __name__ == "__main__":
    main()
