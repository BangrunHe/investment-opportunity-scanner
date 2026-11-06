# Backend — Supabase

The serverless backend: two Edge Functions, a Postgres schema, and a scheduler.

Everything the product does happens here. See the [project README](../README.md) for the
overall picture.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  FEISHU            frontend  +  result view              │
│    in   →  a fund screenshot sent to a group             │
│    out  ←  holdings table  ·  weekly action plan          │
└──────────────────────────────────────────────────────────┘
                        ▲   │
               pull chat│   │send message
                        │   ▼
┌──────────────────────────────────────────────────────────┐
│  SUPABASE           backend  +  db  +  scheduler         │
│                                                          │
│   poll-chat            cron every 10 minutes             │
│     download image → multimodal OCR → resolve fund code  │
│     → upsert into Postgres → reply with holdings table   │
│                                                          │
│   weekly-report        cron Monday 09:00                 │
│     valuation percentiles → LLM index classification     │
│     → discipline engine → reply with the action plan     │
└──────────────────────────────────────────────────────────┘
```

---

## Data model

| Table | Purpose |
|---|---|
| `static_funds` | Fund metadata: code, name, matched index, category (`core` / `satellite` / `gold`) |
| `fund_holdings` | Per-week holding detail — `unique(week, fund_code)` |
| `holding_snapshots` | Per-week holding snapshot, kept for return curves — `unique(week, fund_code)` |
| `strategy_config` | Rule parameters as JSONB — thresholds live here, not in code |
| `processed_messages` | Chat message ids already handled (dedup) |
| `pending_snapshots` | Snapshots waiting for the user to supply a fund code |

`week` is a `YYYY-MM-DD~YYYY-MM-DD` string covering Monday to Sunday.

---

## 1 · Create the schema

In the Supabase dashboard open **SQL Editor** and run
[`sql/01_init.sql`](sql/01_init.sql). It creates all six tables, seeds the rule
parameters, and enables `pg_cron` / `pg_net`.

> To wipe everything and start over, run [`sql/00_reset.sql`](sql/00_reset.sql) first.
> It **deletes all holdings** — use it only for a clean rebuild.

Verify:

```sql
select
  (select count(*) from information_schema.tables where table_schema = 'public'
     and table_name in ('static_funds','fund_holdings','holding_snapshots',
                        'strategy_config','processed_messages','pending_snapshots')) as tables,
  (select count(*) from public.strategy_config) as config_rows;
-- expect: tables = 6, config_rows = 6
```

### Rule parameters

`strategy_config` holds every threshold. Editing a value takes effect on the next run —
no redeploy.

| Key | Meaning |
|---|---|
| `large_cap` | PE tiers for CSI 300 / 500 / 1000 |
| `chinext` | PB rule for ChiNext |
| `star50` | PB rule for STAR 50 and industry funds |
| `sell` | Sell zone and step sizes |
| `portfolio` | Satellite cap, gold baseline, rebalance band |
| `industry_discipline` | Which rule industry funds follow |

---

## 2 · Deploy the functions

```bash
cd <repo root>
supabase link --project-ref <YOUR_PROJECT_REF>
supabase functions deploy poll-chat
supabase functions deploy weekly-report
```

> The `Docker is not running` warning is harmless — Docker is only needed for local serving.

---

## 3 · Set secrets

Supabase dashboard → **Edge Functions → Secrets**:

| Secret | Purpose |
|---|---|
| `DEEPSEEK_API_KEY` | Index classification and reasoning |
| `VISION_API_KEY` | Multimodal OCR |
| `VISION_MODEL` | e.g. `qwen3.8-flash` |
| `FEISHU_APP_ID` | Feishu custom app |
| `FEISHU_APP_SECRET` | Feishu custom app |
| `FEISHU_BITABLE_APP_TOKEN` | Archive table location |
| `FEISHU_BITABLE_TABLE_ID` | Archive table location |
| `FEISHU_CHAT_ID` | The group used for input and notifications |

> `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are injected automatically — do not set them.

How to obtain the Feishu values: **[FEISHU_SETUP.md](FEISHU_SETUP.md)**.

---

## 4 · Schedule the runs

Open [`sql/01_init.sql`](sql/01_init.sql), find the two commented `cron.schedule` blocks,
replace `<YOUR_PROJECT_REF>` and `<YOUR_SERVICE_KEY>`, and run them in the SQL Editor.

| Job | Schedule | What it does |
|---|---|---|
| `poll-chat` | `*/10 * * * *` | Picks up new screenshots and stores them |
| `weekly-report` | `0 1 * * 1` | Monday 09:00 Beijing time — posts the weekly plan |

Confirm the jobs are registered:

```sql
select jobname, schedule, active from cron.job;
```

---

## 5 · Daily operation

| You | The system |
|---|---|
| Send a fund screenshot into the group | Within 10 minutes: OCR → stored → replies with the holdings table |
| (New fund only) reply with the 6-digit code | Pairs it with the pending snapshot and stores it |
| Sold a fund completely → reply `清仓 007606` | Writes a zero row; the fund leaves the table and is not resurrected next week |
| Nothing | Monday 09:00: posts the weekly action plan |

### Incremental uploads

You only need to send the screenshots of funds whose values **changed**. After every
write the function carries the other funds forward from their most recent row, so each
`week` is a complete snapshot rather than just the delta you uploaded. The reply tells
you how it was composed:

```
✅ 已入库 1 只，顺延保留 7 只未变动的基金

📋 当前持仓（8 只 · 合计 12,106.81 元）
```

Without that carry-forward, a week would contain only the funds in that week's
screenshots — the table would look like earlier funds had been lost, and cross-week
totals and weights would be wrong. Already-populated rows for the current week are
never overwritten by the carry-forward step, so re-running is safe.

`清仓` (also accepts `卖出` / `移除` / `删除`) writes a deliberate `holding_assets = 0`
row instead of deleting the fund. A zero value keeps travelling forward through the
carry-forward chain, so the fund cannot come back from history, while its earlier rows
stay intact for the return curve. Zero-value rows are filtered out of both the group
reply and the weekly report.

Run a function manually when debugging:

```sql
select net.http_post(
  url := 'https://<PROJECT_REF>.supabase.co/functions/v1/weekly-report',
  headers := jsonb_build_object('Authorization', 'Bearer <YOUR_SERVICE_KEY>')
);
```

---

## 6 · Reliability

The backend is designed so that running anything twice changes nothing.

| Layer | Mechanism |
|---|---|
| Chat messages | `processed_messages` keyed by `message_id` — a message is never handled twice |
| Holdings rows | `unique(week, fund_code)` + upsert — same week, same fund = overwrite, never duplicate |
| Across weeks | Each week writes its own row, so history is preserved |
| Unchanged funds | Carried forward into the current week from their latest row — every week stays a full snapshot |
| External calls | News, LLM and OCR are each wrapped — a failing dependency degrades one section, it does not fail the run |

Re-uploading a fund in the same week overwrites that week's row with the newer figures,
which is the intended behaviour.

### Upgrading data written before the carry-forward release

Older rows only contain what was uploaded in each week, so historical weeks are partial.
Backfill them once:

```bash
python tools/backfill_holdings.py            # dry run: prints what would be added
python tools/backfill_holdings.py --apply    # writes to fund_holdings + holding_snapshots
```

Existing rows for a week are never modified — only the gaps are filled. A week with no
rows at all (nothing uploaded that week) stays a gap; insert it by hand if you want an
unbroken return curve.

---

## 7 · Troubleshooting

| Symptom | Cause |
|---|---|
| `need scope: im:message.group_msg` | The app is missing the "read group messages" scope |
| Bot never replies | `FEISHU_CHAT_ID` is wrong, the app version is not published, or the app was removed from the group |
| A fund is never matched to an index | Its tracked index is not among the 63 published by the data source — the classifier should proxy-match to the closest industry index; check the function logs |
| Snapshot stored but no reply | The function ran but the send failed — check the `notify` field in the response |
| Nothing is processed | The cron job is missing or `active = false` — inspect `cron.job` |
| Function returns `{"ok":false}` | The `message` field carries the precise error |

---

## 8 · Migrating to another project

| Item | What to carry over |
|---|---|
| Database | Run `sql/01_init.sql` |
| Code | The whole `supabase/functions/` directory |
| Secrets | The eight listed in section 3 |
| Feishu | Custom app (bot capability + required scopes), one group, one archive table |
| Schedule | The two `cron.schedule` calls with the new project ref and key |

No file in this repository contains credentials — they live only in Supabase Secrets.
