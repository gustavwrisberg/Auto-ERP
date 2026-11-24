# 10-minute client demo

For a meeting with a small-company owner or their bookkeeper. Goal: they see that Claude saves
real time **and** that nothing gets booked without a person.

## Before the meeting (5 min)

```bash
export DEMO_TODAY=2026-11-24
python scripts/reset_demo.py
python -m agent.invoice_intake --dry-run   # warm-up: checks key, network, MCP server
python scripts/reset_demo.py
```

Open three windows: a terminal, `samples/inbox/` in a file viewer, and Claude Desktop with the
Auto-ERP connector in read-only mode.

## 1. The problem (1 min)

"How many supplier invoices do you get a month, and who types them in?" Write their numbers
down; you'll use them for the ROI at the end. Open two sample invoices: different layouts, Danish
number formats, one in EUR.

## 2. Copilot (2 min) - Claude Desktop

- "Which customers are overdue? Draft a friendly reminder in Danish for the oldest."
- "What account and VAT code would a freight invoice from Nordvind go to?"

Point out: Claude is reading the ERP live, and in this mode it cannot change anything.

## 3. The agent (3 min) - terminal

```bash
python -m agent.invoice_intake
```

While it runs, narrate the tool calls: it reads the invoice, looks up the supplier by CVR, checks
for duplicates, creates a draft. Then read the summary table aloud:

- 2 clean drafts
- 3 flagged for review: arithmetic error, over the approval limit, foreign currency
- 2 skipped: a duplicate it caught, and a supplier it refused to invent

## 4. The human step (2 min)

```bash
python scripts/approve.py
```

Book the two clean ones, reject the one with the arithmetic error. Say: "There is no tool that
lets Claude book or pay. Only this step, done by your bookkeeper, can." Show `logs/audit.jsonl`:
every action is traceable.

## 5. Proof and next step (2 min)

```bash
python evals/run_eval.py
```

"On your real invoices we'd measure this the same way, before you rely on it." Then the ROI:
invoices per month × minutes saved per invoice × hourly cost. Offer the discovery workshop.

## If something goes wrong

- Authentication error → `ANTHROPIC_API_KEY` not set in this terminal.
- Agent says a voucher already exists → you forgot `scripts/reset_demo.py`.
- Different overdue numbers → `DEMO_TODAY` not set.
