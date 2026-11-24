"""Invoice-intake agent: reads supplier invoices from a folder and creates DRAFT vouchers.

    python -m agent.invoice_intake                 # process samples/inbox
    python -m agent.invoice_intake --inbox path/   # another folder
    python -m agent.invoice_intake --dry-run       # validate, save nothing

Needs ANTHROPIC_API_KEY (or a logged-in Claude Code) and the Claude Code CLI, which the
Claude Agent SDK drives. Claude only gets: Read + Glob (to read the invoices) and the
ERP tools from erp_mcp. No shell, no file writes, no booking.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

ROOT = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT = """You are the accounts-payable assistant for a small Danish company.
Your job: turn supplier invoices into DRAFT vouchers in the ERP. A person approves every draft.

For each invoice file:
1. Read it. Extract supplier name, CVR/VAT id, invoice number, invoice date, due date,
   amount excl. VAT, VAT amount, total and currency. Danish formats: 1.960,00 = 1960.00;
   dates like 18.11.2026 or 20/11/2026 are day-month-year. "Netto 14 dage" = due 14 days after the invoice date.
2. Find the supplier with list_suppliers (try CVR first, then name). Never invent a supplier.
3. Call check_duplicate. If it is a duplicate, do not create a draft.
4. Use the supplier's default_account and default_vat unless the invoice clearly says otherwise.
5. Copy amounts exactly as printed, even if they look wrong: the ERP flags errors for the reviewer.
6. Call create_draft_voucher with source_file set to the file name and short notes for the reviewer.

Finish with a table: file | supplier | total | result (draft / needs review / skipped) | why.
Be brief. Never claim something was booked or paid."""


def build_options(dry_run: bool) -> ClaudeAgentOptions:
    env = {"ERP_DRY_RUN": "1" if dry_run else "0", "PYTHONPATH": str(ROOT)}
    for key in ("ERP_BACKEND", "ERP_STATE_FILE", "DEMO_TODAY"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        cwd=str(ROOT),
        tools=["Read", "Glob"],  # the only built-in tools Claude can see
        allowed_tools=["Read", "Glob", "mcp__erp__*"],
        permission_mode="dontAsk",  # anything not allowed above is refused, never prompted
        mcp_servers={
            "erp": {"type": "stdio", "command": sys.executable, "args": ["-m", "erp_mcp.server"], "env": env},
        },
        model=os.environ.get("CLAUDE_MODEL") or None,
        max_turns=80,
    )


async def run(inbox: Path, dry_run: bool) -> str:
    files = sorted(p.name for p in inbox.iterdir() if p.is_file())
    if not files:
        return "Inbox is empty."
    rel = inbox.resolve().relative_to(ROOT) if inbox.resolve().is_relative_to(ROOT) else inbox.resolve()
    prompt = f"Process these {len(files)} invoice files in {rel}/: " + ", ".join(files)

    final = ""
    async for message in query(prompt=prompt, options=build_options(dry_run)):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    name = block.name.replace("mcp__erp__", "erp.")
                    arg = block.input.get("file_path") or block.input.get("query") or block.input.get("invoice_number") or ""
                    print(f"  -> {name} {arg}")
                elif isinstance(block, TextBlock):
                    final = block.text
        elif isinstance(message, ResultMessage):
            cost = f"${message.total_cost_usd:.4f}" if message.total_cost_usd is not None else "n/a"
            print(f"\nDone in {message.duration_ms / 1000:.1f}s, {message.num_turns} turns, cost {cost}")
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inbox", type=Path, default=ROOT / "samples" / "inbox")
    parser.add_argument("--dry-run", action="store_true", help="validate drafts without saving them")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Note: ANTHROPIC_API_KEY is not set; relying on a logged-in Claude Code (`claude login`).")
    print(f"Processing {args.inbox} {'(dry run)' if args.dry_run else ''}\n")
    try:
        report = asyncio.run(run(args.inbox, args.dry_run))
    except Exception as exc:  # noqa: BLE001 - show a readable message for demo setups
        if "auth" in str(exc).lower():
            sys.exit("Claude could not authenticate. Put ANTHROPIC_API_KEY in your environment (see .env.example).")
        raise
    print("\n" + report)

    out = ROOT / "logs" / f"run-{datetime.now():%Y%m%d-%H%M%S}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nReport saved to {out.relative_to(ROOT)}. Next: python scripts/approve.py")


if __name__ == "__main__":
    main()
