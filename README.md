# Auto-ERP

**Claude automates supplier-invoice intake for a small Danish company. A person approves every booking.**

A runnable demo of how to connect Claude to an ERP or accounting system safely. It ships with a
mock ERP for a fictional company, *Fjordside Demo ApS*, so it runs offline with no real books and no ERP account.

```
 invoices (PDF/text)        Claude agent             MCP server (yours)            ERP
 samples/inbox/  ───────▶  reads, extracts,  ───▶  8 tools, read + DRAFT only ───▶  mock ERP
                           looks up, drafts         validation, audit log           (or e-conomic)
                                                                                        │
                                              person reviews & books  ◀─────────────────┘
                                              scripts/approve.py
```

## What it shows

| | |
|---|---|
| **Copilot** | Ask Claude Desktop questions about live ERP data: "Who owes us money?" |
| **Agent workflow** | Claude reads 7 supplier invoices and creates draft vouchers on its own |
| **Guardrails** | No booking/payment tool exists; refusals for unknown suppliers and duplicates; flags for math errors, VAT mismatches, foreign currency and amounts over the approval limit; read-only and dry-run modes |
| **Audit trail** | Every tool call → `logs/audit.jsonl` |
| **Measurable accuracy** | `evals/run_eval.py` scores a run: invoices handled correctly + fields extracted correctly |

The sample inbox has been chosen to show each guardrail working:

| Invoice | What should happen |
|---|---|
| Kontorhjørnet K-55821 | Clean draft |
| Lyskilde Energi LE-2026-1188 | Clean draft |
| Nordvind Fragt NF-77120 | **Skipped:** already booked (duplicate) |
| Bogholderiet Østerbro 2026-311 | **Needs review:** total doesn't add up |
| Træ & Tømmer TT-90412 | **Needs review:** 80,000 DKK is over the 50,000 DKK approval limit |
| Cloudly Software CL-INV-4471 | **Needs review:** EUR, EU reverse charge |
| Solsikke Rengøring 118 | **Skipped:** unknown supplier, a human must create it |

## Quick start

```bash
git clone https://github.com/gustavwrisberg/Auto-ERP.git && cd Auto-ERP
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt               # the Agent SDK bundles the Claude Code CLI it drives
export ANTHROPIC_API_KEY=sk-ant-...           # or copy .env.example
export DEMO_TODAY=2026-11-24                  # same results in every demo

pytest -q                                     # 14 offline tests, no API key needed
python scripts/reset_demo.py                  # fresh mock ERP
python -m agent.invoice_intake                # Claude processes samples/inbox
python scripts/approve.py                     # you book or reject each draft
python evals/run_eval.py                      # score the run
```

Add `--dry-run` to the agent to validate without saving anything.

## Use it as a copilot in Claude Desktop

Copy `docs/claude_desktop_config.example.json` into your Claude Desktop config, set the absolute path,
restart Claude, and ask:

- "Which customers are overdue, and by how much? Draft a polite reminder in Danish for the oldest one."
- "What does our chart of accounts look like? Which account would a freight invoice go to?"
- "Show me the vouchers waiting for approval and explain the flags."

`ERP_READ_ONLY=1` is set in the example, so Claude can only read. In Claude Code:
`claude mcp add auto-erp -e PYTHONPATH=$PWD -- python3 -m erp_mcp.server`

## Project layout

```
erp/backend.py           mock ERP + business rules (validation, flags, duplicates)
erp/economic.py          template adapter for a real e-conomic agreement (read-only sketch)
erp_mcp/server.py        MCP server: the tools Claude may use, audit log, read-only/dry-run switches
agent/invoice_intake.py  Claude Agent SDK workflow (Read + Glob + ERP tools only)
scripts/approve.py       the human approval step
scripts/reset_demo.py    reset state between demos
evals/                   expected results + scoring script
samples/inbox/           7 fictional supplier invoices
data/seed.json           fictional company, suppliers, accounts, VAT codes
docs/demo-script.md      a 10-minute client demo, step by step
```

## Going from demo to a real client

1. Write an adapter with the same methods as `MockERP` for the client's system (e-conomic, Dinero,
   Billy, Uniconta, Business Central, Odoo), starting from `erp/economic.py`.
2. Use a **test agreement/sandbox** and a dedicated API user with the narrowest rights.
3. Build an eval set from 30+ of the client's real (anonymised) invoices, and track accuracy.
4. Run in parallel with the manual process for 2–4 weeks before relying on it.
5. Sign a data processing agreement; list Anthropic and any hosting as sub-processors.

## Disclaimer

All companies, CVR numbers and invoices in this repository are fictional. This is demonstration
code, not accounting software: keep a person responsible for every booking.

MIT licensed.
