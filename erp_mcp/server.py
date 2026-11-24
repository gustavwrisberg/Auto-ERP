"""MCP server that gives Claude a small, safe set of ERP tools.

Design rules (the part you sell to clients):
  * Claude can READ, and can CREATE DRAFTS. It can never book, pay or delete.
  * Every call is written to logs/audit.jsonl.
  * ERP_READ_ONLY=1 removes the write tool entirely; ERP_DRY_RUN=1 validates without saving.

Run it:   python -m erp_mcp.server
Inspect:  npx @modelcontextprotocol/inspector python -m erp_mcp.server
"""

from __future__ import annotations

import functools
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from erp import ERPError, get_backend

ROOT = Path(__file__).resolve().parent.parent
AUDIT_LOG = Path(os.environ.get("ERP_AUDIT_LOG", ROOT / "logs" / "audit.jsonl"))
READ_ONLY = os.environ.get("ERP_READ_ONLY", "0") == "1"
DRY_RUN = os.environ.get("ERP_DRY_RUN", "0") == "1"



class BusinessRuleError(ToolError, ERPError):
    """A refused request. MCP sends its message to Claude as a readable tool error."""


erp = get_backend()
server = MCPServer(
    name="auto-erp",
    instructions=(
        "Tools for the bookkeeping of a small Danish company. All amounts are DKK unless stated. "
        "You can read data and create DRAFT supplier vouchers; a person approves every booking. "
        "Never guess a supplier, account or VAT code: look them up. If something is unclear, "
        "create no draft and explain what a human needs to check."
    ),
)


def audited(fn):
    """Log every tool call (name, arguments, outcome) as one JSON line."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": fn.__name__, "args": kwargs}
        try:
            result = fn(*args, **kwargs)
            entry["ok"] = True
            return result
        except ERPError as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
            raise BusinessRuleError(str(exc)) from exc  # Claude reads this message and can act on it
        finally:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    return wrapper


# ---------------- read tools ----------------

@audited
def get_company_info() -> dict:
    """Company name, base currency and the amount above which a person must review a voucher."""
    return erp.company()


@audited
def list_suppliers(query: str = "") -> list[dict]:
    """Find suppliers by part of the name, CVR number or EU VAT number. Empty query lists all.
    Each supplier has a default_account and default_vat you should normally use."""
    return erp.suppliers(query or None)


@audited
def list_accounts() -> list[dict]:
    """The chart of accounts (kontoplan): account number and name."""
    return erp.accounts()


@audited
def list_vat_codes() -> list[dict]:
    """VAT codes with their rate, e.g. I25 = Danish input VAT 25%."""
    return erp.vat_codes()


@audited
def list_overdue_invoices(min_days_overdue: int = 1) -> list[dict]:
    """Unpaid sales invoices at least this many days past due, most overdue first."""
    return erp.overdue_invoices(min_days_overdue)


@audited
def list_draft_vouchers() -> list[dict]:
    """Vouchers waiting for a person: status 'draft' (looks fine) or 'needs_review' (has flags)."""
    return erp.vouchers("draft") + erp.vouchers("needs_review")


@audited
def check_duplicate(supplier_id: str, invoice_number: str) -> dict:
    """Check whether this supplier invoice is already registered (booked or draft)."""
    found = erp.find_voucher(supplier_id, invoice_number)
    return {"duplicate": bool(found), "existing": found}


# ---------------- write tool (drafts only) ----------------

@audited
def create_draft_voucher(
    supplier_id: str,
    invoice_number: str,
    invoice_date: str,
    account: int,
    vat_code: str,
    amount_excl_vat: float,
    vat_amount: float,
    total: float,
    due_date: str = "",
    currency: str = "DKK",
    source_file: str = "",
    notes: str = "",
) -> dict:
    """Create a DRAFT supplier voucher for a person to approve. Dates are YYYY-MM-DD.
    The ERP checks the arithmetic, VAT rate, duplicates and approval limit, and marks the
    draft 'needs_review' with flags if anything looks off. It refuses unknown suppliers,
    accounts and VAT codes, and duplicates. Put anything a reviewer should know in notes."""
    result = erp.create_draft_voucher(
        supplier_id=supplier_id, invoice_number=invoice_number, invoice_date=invoice_date,
        due_date=due_date or None, account=int(account), vat_code=vat_code,
        amount_excl_vat=float(amount_excl_vat), vat_amount=float(vat_amount), total=float(total),
        currency=currency, source_file=source_file, notes=notes, dry_run=DRY_RUN,
    )
    return {"voucher_id": result.voucher_id, "status": result.status, "flags": result.flags, "dry_run": result.dry_run}


READ_TOOLS = [get_company_info, list_suppliers, list_accounts, list_vat_codes,
              list_overdue_invoices, list_draft_vouchers, check_duplicate]

for _fn in READ_TOOLS:
    server.tool()(_fn)
if not READ_ONLY:
    server.tool()(create_draft_voucher)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
