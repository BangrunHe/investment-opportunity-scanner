# Investment Opportunity Scanner

**A serverless AI agent that turns a fund screenshot in a chat app into a weekly, valuation-driven action plan.**

No app to install, no dashboard to open. Send a screenshot to a Feishu group — the system reads it, stores it, and every Monday tells you exactly what to buy, hold, pause, or sell.

---

## How it works

| # | You do | The system does |
|---|---|---|
| 1 | Send a fund-holding screenshot to a Feishu group | Downloads the image → multimodal OCR → structured JSON → writes to Postgres |
| 2 | (New fund only) reply with the 6-digit fund code | Pairs the reply with the pending snapshot and stores it |
| 3 | Nothing | Every Monday 09:00 it posts a valuation-based action plan back to the group |

---

## Why it is interesting

- **Two platforms, nothing else** — **Feishu is the frontend *and* the result view** (you send a screenshot, you read a report); **Supabase is the backend, the database *and* the scheduler**. No frontend framework, no server to operate, no separate worker, no message broker.
- **No inbound webhook** — instead of Feishu pushing events across borders (unreliable), Supabase *pulls* the chat every 10 minutes. The agent is purely outbound.
- **Rules live in data, not code** — buy/pause/sell thresholds sit in a `strategy_config` table; changing them needs no redeploy.
- **AI as a fallback chain** — 63 valuation indices come from Xueqiu; for funds tracking an index Xueqiu doesn't have, the LLM picks the closest industry proxy and labels it low-confidence.
- **Idempotent twice over** — messages dedup by `message_id`, rows dedup by `unique(week, fund_code)` + upsert.
- **Graceful degradation** — every external call (news, LLM, OCR) is wrapped, so a failing dependency degrades one section instead of breaking the run.

---

## Architecture

**The whole system is two platforms.**

```
┌──────────────────────────────────────────────────────────────┐
│  Platform 1 · FEISHU          frontend  +  result view       │
│    in   →  send a fund screenshot into a group               │
│    out  ←  holdings table  ·  weekly action plan             │
└──────────────────────────────────────────────────────────────┘
                            ▲  │
                   pull chat│  │send message
                            │  ▼
┌──────────────────────────────────────────────────────────────┐
│  Platform 2 · SUPABASE        backend + db + scheduler       │
│                                                              │
│   poll-chat       cron */10 min                              │
│     download image → multimodal OCR → resolve fund code      │
│     → upsert into Postgres → reply with holdings table       │
│                                                              │
│   weekly-report   cron Mon 09:00                             │
│     valuation percentiles → LLM index classification         │
│     → discipline engine → reply with action plan             │
│                                                              │
│   Postgres · 6 tables                                        │
│     holdings · fund metadata · rule config · dedup state     │
└──────────────────────────────────────────────────────────────┘
```

| | Traditional build | This project |
|---|---|---|
| Frontend | React / Vue app | *not needed* — the chat window is the UI |
| Backend | FastAPI / Express service | Edge Functions (same platform as the DB) |
| Database | separate managed Postgres | Supabase Postgres |
| Scheduler | Celery / Airflow / a VPS cron | `pg_cron` |
| Notifications | email service / push SDK | the same chat the input came from |
| **Total platforms** | **4–6** | **2** |

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Runtime | **Supabase Edge Functions** (Deno / TypeScript) | Serverless, same platform as the DB |
| Database | **Supabase Postgres** (6 tables) | Relational rows fit weekly snapshots naturally |
| Scheduling | **pg_cron + pg_net** | No external worker needed |
| OCR / vision | **Qwen3.8-Flash** (DashScope, OpenAI-compatible) | Reads Chinese fund screenshots accurately |
| Reasoning | **DeepSeek `deepseek-chat`** | Cost-efficient structured JSON output |
| Market data | **Xueqiu / Danjuan** valuation center | Free PE/PB percentiles for 63 indices |
| Messaging | **Feishu custom app bot** (IM API) | Chat as both input and notification channel |
| Dev tooling | **Python 3.11** | Reference implementation, backtesting, ops scripts |

---

## The strategy engine

Valuation discipline, encoded as pure functions:

| Asset class | Metric | Accumulate | Pause | Distribute |
|---|---|---|---|---|
| CSI 300 / 500 / 1000 | PE percentile | <30 → ¥500/mo · <20 → ¥1000/mo · <10 → ¥2000/mo | >35 | >70, each +10 pct step → sell 30% |
| ChiNext | PB percentile | <40, amount ×1.5 per 10 pct drop | >50 | >70, +10 pct steps → sell 30% |
| STAR 50 & industry funds | PB percentile | <30, amount ×2 per 10 pct drop | >40 | >70, +10 pct steps → sell 30% |
| Gold | — | rebalance around a 25% baseline, ±7% band | — | — |

**Portfolio rules** — funds are split into *core* (broad / strategy index) and *satellite* (industry); satellite exposure is capped at 40%, and gold is rebalanced separately.

---

## Quick start

**1 · Create the schema** — run `supabase/sql/01_init.sql` in the Supabase SQL editor.

**2 · Deploy the functions**

```bash
supabase link --project-ref <YOUR_PROJECT_REF>
supabase functions deploy poll-chat
supabase functions deploy weekly-report
```

**3 · Set secrets** (Supabase → Edge Functions → Secrets)

| Secret | Purpose |
|---|---|
| `DEEPSEEK_API_KEY` | Classification & reasoning |
| `VISION_API_KEY` / `VISION_MODEL` | Multimodal OCR |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | Feishu custom app |
| `FEISHU_BITABLE_APP_TOKEN` / `FEISHU_BITABLE_TABLE_ID` | Archive table |
| `FEISHU_CHAT_ID` | Input + notification group |

**4 · Configure Feishu** — full walkthrough in [`supabase/FEISHU_SETUP.md`](supabase/FEISHU_SETUP.md) (app creation, 5 required scopes, group bot, archive table).

**5 · Enable the schedule** — uncomment the two `cron.schedule` blocks in `supabase/sql/01_init.sql`.

---

## Repository layout

```
├── supabase/                    Cloud backend (the actual product)
│   ├── sql/
│   │   ├── 00_reset.sql
│   │   └── 01_init.sql          Schema + rule config + cron
│   ├── functions/
│   │   ├── _shared/             12 modules: strategy, valuation, AI, Feishu, ...
│   │   ├── poll-chat/           Chat → OCR → DB → reply
│   │   └── weekly-report/       Analysis → weekly plan
│   ├── README.md                Backend deep dive
│   └── FEISHU_SETUP.md          Feishu setup walkthrough
├── src/                         Python reference implementation + backtester
├── tools/                       Ops scripts (chat id lookup, archive inspector)
└── tests/                       Unit tests for the rule engine
```

---

## Local Python tooling

A parallel implementation used for development, backtesting and debugging — it mirrors the cloud logic:

```bash
pip install -r requirements.txt
python main.py                          # fetch valuation + print signals
python -m unittest discover -s tests    # rule-engine tests
python tools/feishu_chat_id.py          # look up a Feishu group id
```

---

## Design notes

Four decisions that mattered more than the code:

- **Pull, don't push.** An inbound webhook from Feishu to Supabase crosses a border and fails silently. Polling the other way is outbound, retryable and observable.
- **Rules live in a table, not in code.** Thresholds change often; redeploying a function every time you tweak a number is the wrong trade.
- **Distinguish "the model is wrong" from "the answer isn't in my options".** A fund can track an index the data source simply does not publish. Rejecting the answer is not the same as the answer being wrong — proxy-match instead.
- **Say why it failed.** "Fetch failed" and "filter matched nothing" look identical in the output but need opposite fixes. Expose both in the response.

---

## License

MIT
