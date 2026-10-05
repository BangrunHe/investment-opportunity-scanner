"""集中配置：目标指数、估值口径、买卖纪律参数。

估值分位统一使用「百分位」单位（0~100），例如 30 表示 30 分位。
蛋卷接口返回的 pe_percentile / pb_percentile 为 0~1 小数，由 fetch 层换算成百分位。
"""

from . import env

env.load_dotenv()

# 蛋卷基金估值中心 JSON 接口（无需浏览器渲染）
DANJUAN_API = "https://danjuanfunds.com/djapi/index_eva/dj"

# 是否信任系统代理。蛋卷为国内站点，默认直连，
# 避免本地代理（如 Clash/v2ray）未启动时请求失败。
TRUST_ENV_PROXY = False

# 目标指数：index_code -> {名称, 类别}
INDICES = {
    "SH000300": {"name": "沪深300", "category": "large_cap"},
    "SH000905": {"name": "中证500", "category": "large_cap"},
    "SH000852": {"name": "中证1000", "category": "large_cap"},
    "SZ399006": {"name": "创业板指", "category": "chinext"},
    "SH000688": {"name": "科创50", "category": "star50"},
}

# 卖出纪律（全类别统一）：
#   分位 > 70 进入卖出区；分位每上穿一个档位（80、90）各卖一次，每次卖出持仓的 30%。
SELL_ZONE = 70.0
SELL_STEPS = [80.0, 90.0]
SELL_FRACTION = 0.30

# 大盘宽基（沪深300/中证500/中证1000）：看 PE 分位，阶梯买入。
# buy_tiers 按阈值升序：分位低于 threshold 即采用对应月投金额（元）。
LARGE_CAP = {
    "metric": "pe",
    "buy_tiers": [(10.0, 2000.0), (20.0, 1000.0), (30.0, 500.0)],
    "pause": 35.0,
}

# 创业板：看 PB 分位，<40 起步 300 元/月，每下降 10 分位 ×1.5（等比）。
CHINEXT = {
    "metric": "pb",
    "buy_zone": 40.0,
    "base_amount": 300.0,
    "step": 10.0,
    "multiplier": 1.5,
    "pause": 50.0,
}

# 科创50：看 PB 分位，<30 起步 500 元/月，每下降 10 分位 ×2（翻倍）。
STAR50 = {
    "metric": "pb",
    "buy_zone": 30.0,
    "base_amount": 500.0,
    "step": 10.0,
    "multiplier": 2.0,
    "pause": 40.0,
}

CATEGORY_CONFIG = {
    "large_cap": LARGE_CAP,
    "chinext": CHINEXT,
    "star50": STAR50,
}


def config_for(index_code: str) -> dict:
    """返回某指数的完整纪律配置（含名称、类别、指标、阈值）。"""
    meta = INDICES[index_code]
    cfg = dict(CATEGORY_CONFIG[meta["category"]])
    cfg["index_code"] = index_code
    cfg["name"] = meta["name"]
    cfg["category"] = meta["category"]
    return cfg


# ---- 多 AI agent 分析（DeepSeek API，OpenAI 兼容） ----
LLM = {
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "temperature": 0.3,
    "max_tokens": 1200,
    "timeout": 60,
}

# ---- 投资限额（风险控制，占位默认值，可按需修改） ----
# max_cumulative_invest: 单指数累计投入上限（元），超过 -> 停止加仓提醒
# max_cycle_weeks: 单次加仓连续周数上限，超过 -> 停止加仓/评估卖出提醒
LIMITS = {
    "large_cap": {"max_cumulative_invest": 50000.0, "max_cycle_weeks": 104},
    "chinext": {"max_cumulative_invest": 30000.0, "max_cycle_weeks": 104},
    "star50": {"max_cumulative_invest": 20000.0, "max_cycle_weeks": 52},
}

# ---- 邮件提醒（网易邮箱 SMTP，可选） ----
EMAIL = {
    "smtp_host": "smtp.163.com",
    "smtp_port": 465,
    "use_ssl": True,
    "username_env": "EMAIL_USERNAME",
    "password_env": "EMAIL_PASSWORD",  # 网易邮箱需使用「授权码」，不是登录密码
    "to_env": "EMAIL_TO",
}

# ---- 个人数据库（Supabase，PostgREST） ----
# 建议使用 service_role key（仅本机/云端安全环境）或设置 RLS 后的受限 anon key。
SUPABASE = {
    "url_env": "SUPABASE_URL",
    "key_env": "SUPABASE_KEY",           # 日常读写 key（publishable 或 service_role）
    "service_key_env": "SUPABASE_SERVICE_KEY",  # 建表/DDL 需 service_role key
    "timeout": 30,
}

# ---- 多模态 OCR（基金持仓截图 -> 结构化） ----
# 视觉模型：阿里云百炼 DashScope（OpenAI 兼容端点），qwen3.8-flash 支持图片输入。
VISION = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "base_url_env": "VISION_BASE_URL",
    "model": "qwen3.8-flash",
    "model_env": "VISION_MODEL",
    "api_key_env": "VISION_API_KEY",
    "temperature": 0.1,
    "max_tokens": 1500,
    "timeout": 90,
}

# ---- 核心-卫星体系与再平衡 ----
PORTFOLIO = {
    "satellite_max_ratio": 0.40,   # 卫星基金总持仓占比上限（<40%）
    "gold_baseline_ratio": 0.25,   # 黄金基准持仓线
    "gold_rebalance_band": 0.07,   # 黄金上下偏移超过 7% 触发再平衡提醒
}

# 行业/卫星基金纪律：参考科创50（PB 分位）
INDUSTRY_DISCIPLINE = "star50"
