-- ============================================================
-- 01_init.sql — 从零初始化（空白项目执行一次）
-- 建表 + 规则参数 + 定时任务扩展
-- 在 Supabase SQL Editor 执行
-- ============================================================

-- ===== 动态库 第一层：周维度持仓（时间+持仓匹配，用于收益曲线） =====
create table if not exists public.holding_snapshots (
  id                bigint generated always as identity primary key,
  week              text not null,           -- 周划分（周一到周日），如 "2026-09-14~2026-09-20"
  fund_code         text not null,
  fund_name         text,
  holding_assets    numeric,
  valuation_percent numeric,
  created_at        timestamptz default now(),
  unique (week, fund_code)
);

-- ===== 动态库 第二层：基金具体持仓信息 =====
create table if not exists public.fund_holdings (
  id             bigint generated always as identity primary key,
  fund_code      text not null,
  fund_name      text,
  holding_assets numeric,
  holding_cost   numeric,
  holding_profit numeric,
  holding_shares numeric,
  unit_cost      numeric,
  week_nav       numeric,
  week           text not null,
  created_at     timestamptz default now(),
  unique (week, fund_code)   -- 幂等：同周同基金仅一条
);

-- ===== 静态库：基金固定信息（仅购入新基金时补充更新） =====
create table if not exists public.static_funds (
  id         bigint generated always as identity primary key,
  fund_code  text not null unique,
  fund_name  text,
  index_code text,      -- 所属指数代码（雪球基金指数，AI 分类）
  index_name text,      -- 所属指数名称
  category   text,      -- core / satellite / gold
  status     text default 'pending_classify',
  created_at timestamptz default now()
);

-- ===== 规则参数表（改数值不碰代码） =====
create table if not exists public.strategy_config (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz default now()
);

insert into public.strategy_config (key, value) values
  ('large_cap', '{"metric":"pe","buy_tiers":[[10,2000],[20,1000],[30,500]],"pause":35}'),
  ('chinext',   '{"metric":"pb","buy_zone":40,"base_amount":300,"step":10,"multiplier":1.5,"pause":50}'),
  ('star50',    '{"metric":"pb","buy_zone":30,"base_amount":500,"step":10,"multiplier":2.0,"pause":40}'),
  ('sell',      '{"zone":70,"steps":[80,90],"fraction":0.30}'),
  ('portfolio', '{"satellite_max_ratio":0.40,"gold_baseline_ratio":0.25,"gold_rebalance_band":0.07}'),
  ('industry_discipline', '"star50"')
on conflict (key) do nothing;

-- ===== 群消息轮询：已处理消息去重（保证幂等） =====
create table if not exists public.processed_messages (
  message_id   text primary key,
  processed_at timestamptz default now()
);

-- ===== 待补基金代码的快照（群里发图但库里查不到代码时暂存） =====
create table if not exists public.pending_snapshots (
  id         bigint generated always as identity primary key,
  message_id text unique,     -- 触发它的图片消息
  fund_name  text,            -- OCR 出的基金名
  payload    jsonb,           -- OCR 出的完整持仓数据
  created_at timestamptz default now()
);

-- ===== 定时任务扩展 =====
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- ===== 定时任务（替换 YOUR_PROJECT_REF 与 YOUR_SERVICE_KEY 后取消注释执行）=====
-- ① 群消息轮询：每 10 分钟扫一次群，自动拾取新截图并入库（北京时间）
-- select cron.schedule('poll-chat', '*/10 * * * *', $$
--   select net.http_post(
--     url := 'https://YOUR_PROJECT_REF.supabase.co/functions/v1/poll-chat',
--     headers := jsonb_build_object('Authorization', 'Bearer YOUR_SERVICE_KEY')
--   ) $$);
--
-- ② 周报：每周一 9:00 北京时间 = 1:00 UTC
-- select cron.schedule('weekly-report', '0 1 * * 1', $$
--   select net.http_post(
--     url := 'https://YOUR_PROJECT_REF.supabase.co/functions/v1/weekly-report',
--     headers := jsonb_build_object('Authorization', 'Bearer YOUR_SERVICE_KEY')
--   ) $$);
--
-- 查看已挂载的定时任务：
-- select jobname, schedule, active from cron.job;
