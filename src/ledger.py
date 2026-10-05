"""投入台账：记录每期定投，统计累计投入与本次加仓连续周数。"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LEDGER_PATH = DATA_DIR / "ledger.json"


def _load(path=LEDGER_PATH) -> dict:
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save(data, path=LEDGER_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record(index_code: str, weekly_amount: float, date: str, path=LEDGER_PATH) -> dict:
    """记录一次周度定投，返回该指数更新后的台账状态。

    - 当周有买入则累计 total_invested 并 consecutive_buy_weeks +1；
    - 当周无买入则把连续加仓周数清零（本次加仓周期结束）。
    """
    data = _load(path)
    st = data.setdefault(
        index_code,
        {"total_invested": 0.0, "consecutive_buy_weeks": 0, "last_date": None},
    )
    if weekly_amount and weekly_amount > 0:
        st["total_invested"] = round(st["total_invested"] + weekly_amount, 2)
        st["consecutive_buy_weeks"] += 1
    else:
        st["consecutive_buy_weeks"] = 0
    st["last_date"] = date
    _save(data, path)
    return dict(st)
