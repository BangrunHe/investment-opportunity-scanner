"""极简 .env 加载器（无第三方依赖）。

从项目根目录的 .env 读取 KEY=VALUE 到 os.environ；
已存在的环境变量不会被覆盖，支持 # 注释与可选引号。
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = PROJECT_ROOT / ".env"


def load_dotenv(path=None) -> bool:
    """加载 .env 文件到环境变量，返回是否成功读取。"""
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        return False

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = _clean(value)
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def _clean(value: str) -> str:
    value = value.strip()
    # 去除行尾注释（简单处理：不在引号内）
    for marker in (" #", "\t#"):
        if marker in value:
            value = value.split(marker, 1)[0].strip()
            break
    # 去除首尾成对引号
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    return value
