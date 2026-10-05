"""AI 基金归属指数分类：把基金归类到雪球基金(蛋卷)已有指数，或黄金类。

为避免指数匹配问题，分类时传入雪球全部指数作为可选项，AI 只从中选择 index_code。
"""

import json

from . import config, llm


def available_index_options() -> list:
    """提取雪球基金上的全部指数作为分类可选项，并附加黄金类。"""
    from . import fetch

    records = fetch.fetch_all_indices()
    options = [
        {"index_code": r["index_code"], "name": r["name"]}
        for r in records
        if r.get("index_code")
    ]
    # 黄金类：无指数
    options.append({"index_code": None, "name": "黄金类（黄金/贵金属基金）"})
    return options


def _format_options(options) -> str:
    lines = []
    for o in options:
        code = o.get("index_code") or "null"
        lines.append(f"- {code} : {o.get('name')}")
    return "\n".join(lines)


_SYSTEM = (
    "你是一名基金研究分析师。给定基金代码、名称与「可选指数列表」，"
    "为该基金选出用于估值跟踪的指数。\n"
    "【硬性规则】\n"
    "1. index_code 必须**逐字复制**自「可选指数列表」，严禁使用列表之外的代码。\n"
    "2. 基金实际跟踪的指数可能不在列表里；此时请挑选**行业/主题最接近**的列表内指数作为代理。"
    "参考：「港股通创新药/生物医药」→ 中证医疗或全指医药；「港股通互联网」→ 中国互联；"
    "「半导体/芯片/电子」→ 中证电子；「军工」→ 中证军工；「白酒/食品饮料」→ 中证白酒或国证食品。\n"
    "3. 除黄金类外，index_code 一律不得为 null。\n"
    "4. 黄金/贵金属类基金：index_code 填 null、category 填 gold。\n"
    "只输出 JSON 对象，字段固定为：index_code、index_name、category、confidence、reasoning。\n"
    "category 取值：core（宽基/策略指数基金）、satellite（行业/主题指数基金）、gold（黄金类）。\n"
    "confidence：完全对应填 high；代理匹配填 low。\n"
    "reasoning 中请同时说明「该基金实际跟踪的指数」与「你选了哪个代理指数及原因」。"
)


def classify(fund_code, fund_name, index_options=None, extra_desc="") -> dict:
    """返回 {fund_code, fund_name, index_code, index_name, category, confidence, reasoning}。"""
    if not llm.available():
        return _fallback(fund_code, fund_name)

    if index_options is None:
        index_options = available_index_options()

    prompt = f"基金代码：{fund_code}\n基金名称：{fund_name}"
    if extra_desc:
        prompt += f"\n补充信息：{extra_desc}"
    prompt += "\n\n可选指数列表（index_code : 名称）：\n" + _format_options(index_options)
    prompt += "\n\n请从上面列表中选出一个 index_code 作为该基金的估值跟踪指数。"

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt},
    ]
    result = llm.chat_json(messages)

    result.setdefault("fund_code", fund_code)
    result.setdefault("fund_name", fund_name)
    result.setdefault("category", "satellite")
    result.setdefault("confidence", "low")
    result.setdefault("index_name", "")
    result.setdefault("reasoning", "")

    # 校验 index_code 必须来自可选列表（黄金为 null），并按需回填名称
    result["index_code"] = _validate_code(
        result.get("index_code"), result.get("category"), result.get("index_name"), index_options
    )

    # 若返回了列表外的代码（通常是基金真实跟踪的指数，雪球没有），带纠正信息重试一次
    if not result["index_code"] and result.get("category") != "gold":
        messages.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"你给出的 index_code = {json.dumps(result.get('index_code'), ensure_ascii=False)} "
                    "不在可选列表中。\n请改为从列表中挑选「行业/主题最接近」的那一个作为代理指数，例如：\n"
                    "  · 港股通创新药 / 生物医药 → 中证医疗（SZ399989）或 全指医药（SH000991）\n"
                    "  · 港股通互联网 → 中国互联（CSIH11136）\n"
                    "  · 半导体 / 芯片 → 中证电子（CSI930652）\n"
                    "只输出 JSON，且 index_code 必须是列表里原样存在的代码。"
                ),
            }
        )
        retry = llm.chat_json(messages)
        retry_code = _validate_code(
            retry.get("index_code"),
            retry.get("category") or result.get("category"),
            retry.get("index_name"),
            index_options,
        )
        if retry_code:
            result = {**result, **retry}
            result["index_code"] = retry_code

    if not result.get("index_name") and result.get("index_code"):
        for o in index_options:
            if o.get("index_code") == result["index_code"]:
                result["index_name"] = o.get("name")
                break
    return result


def _validate_code(code, category, index_name, options):
    """确保返回的 index_code 在可选列表内；黄金返回 None；否则按名称兜底匹配。"""
    if category == "gold":
        return None
    valid = {o.get("index_code") for o in options}
    if code in valid:
        return code
    if index_name:
        for o in options:
            n = o.get("name") or ""
            if n and (n in index_name or index_name in n):
                return o.get("index_code")
    return None


def _fallback(fund_code, fund_name) -> dict:
    """无 API key 时按名称关键词粗略归类（需人工确认）。"""
    name = fund_name or ""
    if "黄金" in name or "上海金" in name:
        category, index_code, index_name = "gold", None, ""
    elif any(k in name for k in ("沪深300", "中证500", "中证1000", "创业板", "科创50",
                                 "上证50", "红利", "基本面", "价值", "成长", "宽基", "300", "500")):
        category, index_code, index_name = "core", "", ""
    else:
        category, index_code, index_name = "satellite", "", ""

    return {
        "fund_code": fund_code,
        "fund_name": fund_name,
        "index_code": index_code,
        "index_name": index_name,
        "category": category,
        "confidence": "low",
        "reasoning": "未配置 DEEPSEEK_API_KEY，按名称关键词粗略归类，需人工确认。",
    }


def verify(fund_code, fund_name, category, index_name="") -> dict:
    """AI 检查：校验已有分类是否正确（用于人工确认前的复核）。

    返回 {valid: true/false/None, correct_category, correct_index, reasoning}。
    """
    if not llm.available():
        return {"valid": None, "reasoning": "未配置 DEEPSEEK_API_KEY，无法复核"}

    result = llm.chat_json(
        [
            {
                "role": "system",
                "content": (
                    "你是基金分类复核助手。判断给定基金的分类是否正确。只输出 JSON 对象，字段："
                    "valid（true/false）、correct_category（core/satellite/gold）、"
                    "correct_index（正确的指数名，可为空）、reasoning。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"基金：{fund_code} {fund_name}\n"
                    f"当前分类：category={category}，指数={index_name}\n"
                    "请校验该分类是否正确；若不正确，给出 correct_category 与 correct_index。"
                ),
            },
        ]
    )
    if not isinstance(result, dict):
        return {"valid": None, "reasoning": str(result)}
    result.setdefault("valid", None)
    result.setdefault("reasoning", "")
    return result
