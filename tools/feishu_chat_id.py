"""获取飞书群 chat_id —— 列出应用机器人所在的群。

前置条件：
  1. .env 里已配置 FEISHU_APP_ID / FEISHU_APP_SECRET
  2. 应用已开启「机器人」能力并**发布版本**
  3. 已把该**应用机器人**加入目标群（群设置 → 群机器人 → 添加机器人 → 选你的应用）
  4. 应用已开通权限：im:chat:readonly

用法：
  python tools/feishu_chat_id.py
"""

import os
import sys
from pathlib import Path

import requests

# 让脚本能直接运行：把项目根目录加入模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402 - 导入以触发 .env 加载

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
CHATS_URL = "https://open.feishu.cn/open-apis/im/v1/chats"


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = config.TRUST_ENV_PROXY
    return s


def get_tenant_token() -> str:
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not (app_id and app_secret):
        raise SystemExit("请先在 .env 配置 FEISHU_APP_ID / FEISHU_APP_SECRET")

    data = _session().post(
        TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    ).json()
    if not data.get("tenant_access_token"):
        raise SystemExit(f"获取 tenant_access_token 失败：{data}")
    return data["tenant_access_token"]


def main() -> None:
    token = get_tenant_token()
    data = _session().get(
        CHATS_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 50},
        timeout=15,
    ).json()

    if data.get("code") != 0:
        raise SystemExit(f"查询群列表失败：{data}")

    items = data.get("data", {}).get("items", []) or []
    if not items:
        print("未查到任何群。请确认：")
        print("  ① 应用已开启「机器人」能力并已发布版本")
        print("  ② 已把该【应用机器人】加入目标群（不是自定义机器人）")
        print("  ③ 应用已开通 im:chat:readonly 权限，且权限已随版本发布生效")
        return

    print(f"应用机器人所在群共 {len(items)} 个：\n")
    for c in items:
        print(f"  群名：{c.get('name')}")
        print(f"  chat_id：{c.get('chat_id')}\n")


if __name__ == "__main__":
    main()
