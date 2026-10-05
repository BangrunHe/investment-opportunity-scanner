-- ============================================================
-- 00_reset.sql — 重置为空白（⚠ 会删除全部持仓数据！）
-- 用途：从零验证代码完整性 / 项目迁移前重置
-- 在 Supabase SQL Editor 执行
-- ============================================================

-- 1. 移除定时任务（若已配置）
do $$
begin
  perform cron.unschedule('weekly-report');
exception when others then null;
end $$;

-- 2. 删除业务表（含数据）
drop table if exists public.fund_holdings cascade;
drop table if exists public.holding_snapshots cascade;
drop table if exists public.static_funds cascade;
drop table if exists public.strategy_config cascade;
