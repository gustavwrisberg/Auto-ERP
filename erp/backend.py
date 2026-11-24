"""A small mock ERP that behaves like the parts of a real accounting system the demo needs.

State lives in a JSON file (default: .demo_state/erp.json) so you can inspect it, reset it,
and run the demo offline. Swap this class for a real adapter (see erp/economic.py) to go live.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = ROOT / "data" / "seed.json"
DEFAULT_STATE_FILE = ROOT / ".demo_state" / "erp.json"

ROUNDING_TOLERANCE = 0.01


class ERPError(ValueError):
    """Raised when a request breaks a business rule. The message is safe to show to Claude."""


@dataclass
class DraftResult:
    voucher_id: str
    status: str  # "draft" or "needs_review"
    flags: list[str] = field(default_factory=list)
    dry_run: bool = False


def today() -> date:
    """The demo's 'today'. Set DEMO_TODAY=YYYY-MM-DD for repeatable demos."""
    override = os.environ.get("DEMO_TODAY")
    return date.fromisoformat(override) if override else date.today()


class MockERP:
    def __init__(self, state_file: str | Path | None = None):
        self.state_file = Path(state_file or os.environ.get("ERP_STATE_FILE") or DEFAULT_STATE_FILE)
        if not self.state_file.exists():
            self.reset()

    # ---------- state ----------
    def reset(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SEED_FILE, self.state_file)

    def _load(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_file)

    # ---------- read ----------
    def company(self) -> dict:
        return self._load()["company"]

    def accounts(self) -> list[dict]:
        return self._load()["accounts"]

    def vat_codes(self) -> list[dict]:
        return self._load()["vat_codes"]

    def suppliers(self, query: str | None = None) -> list[dict]:
        items = self._load()["suppliers"]
        if query:
            q = query.lower().strip()
            items = [
                s for s in items
                if q in s["name"].lower() or q == (s.get("cvr") or "") or q == (s.get("eu_vat") or "").lower()
            ]
        return items

    def overdue_invoices(self, min_days: int = 1) -> list[dict]:
        data = self._load()
        customers = {c["id"]: c for c in data["customers"]}
        now = today()
        result = []
        for inv in data["sales_invoices"]:
            if inv["paid"]:
                continue
            days = (now - date.fromisoformat(inv["due_date"])).days
            if days >= min_days:
                cust = customers[inv["customer_id"]]
                result.append({**inv, "customer_name": cust["name"], "customer_email": cust["email"], "days_overdue": days})
        return sorted(result, key=lambda r: r["days_overdue"], reverse=True)

    def vouchers(self, status: str | None = None) -> list[dict]:
        items = self._load()["vouchers"]
        return [v for v in items if status is None or v["status"] == status]

    def find_voucher(self, supplier_id: str, invoice_number: str) -> dict | None:
        for v in self._load()["vouchers"]:
            if v["supplier_id"] == supplier_id and v["invoice_number"].strip().lower() == invoice_number.strip().lower() \
                    and v["status"] != "rejected":
                return v
        return None

    # ---------- write (drafts only) ----------
    def create_draft_voucher(self, *, supplier_id: str, invoice_number: str, invoice_date: str, due_date: str | None,
                             account: int, vat_code: str, amount_excl_vat: float, vat_amount: float, total: float,
                             currency: str = "DKK", source_file: str = "", notes: str = "",
                             dry_run: bool = False) -> DraftResult:
        data = self._load()
        suppliers = {s["id"]: s for s in data["suppliers"]}
        accounts = {a["number"] for a in data["accounts"]}
        vat = {v["code"]: v for v in data["vat_codes"]}
        flags: list[str] = []

        # Hard rules: refuse the draft.
        if supplier_id not in suppliers:
            raise ERPError(f"Unknown supplier_id '{supplier_id}'. Look it up with list_suppliers; "
                           "if it does not exist, do not invent one - report it for a human.")
        if account not in accounts:
            raise ERPError(f"Unknown account {account}. Use list_accounts.")
        if vat_code not in vat:
            raise ERPError(f"Unknown vat_code '{vat_code}'. Use list_vat_codes.")
        try:
            date.fromisoformat(invoice_date)
            if due_date:
                date.fromisoformat(due_date)
        except ValueError as exc:
            raise ERPError("Dates must be YYYY-MM-DD.") from exc
        if self.find_voucher(supplier_id, invoice_number):
            raise ERPError(f"Duplicate: invoice {invoice_number} from {supplier_id} is already registered.")

        # Soft rules: create the draft but flag it for a human.
        if abs(round(amount_excl_vat + vat_amount, 2) - round(total, 2)) > ROUNDING_TOLERANCE:
            flags.append(f"Amounts do not add up: {amount_excl_vat} + {vat_amount} != {total}")
        expected_vat = round(amount_excl_vat * vat[vat_code]["rate"], 2)
        if abs(expected_vat - vat_amount) > ROUNDING_TOLERANCE:
            flags.append(f"VAT {vat_amount} differs from {vat_code} rate (expected {expected_vat})")
        if currency.upper() != data["company"]["currency"]:
            flags.append(f"Foreign currency {currency.upper()}: check exchange rate before booking")
        if total > data["company"]["approval_limit_dkk"]:
            flags.append(f"Total {total:,.2f} is above the approval limit of {data['company']['approval_limit_dkk']:,} DKK")
        sup = suppliers[supplier_id]
        if account != sup.get("default_account"):
            flags.append(f"Account {account} differs from supplier default {sup.get('default_account')}")
        if vat_code != sup.get("default_vat"):
            flags.append(f"VAT code {vat_code} differs from supplier default {sup.get('default_vat')}")

        voucher_id = f"V-{len(data['vouchers']) + 1:04d}"
        status = "needs_review" if flags else "draft"
        if dry_run:
            return DraftResult(voucher_id="(dry-run)", status=status, flags=flags, dry_run=True)

        data["vouchers"].append({
            "id": voucher_id,
            "status": status,
            "supplier_id": supplier_id,
            "invoice_number": invoice_number.strip(),
            "invoice_date": invoice_date,
            "due_date": due_date,
            "account": account,
            "vat_code": vat_code,
            "amount_excl_vat": round(amount_excl_vat, 2),
            "vat_amount": round(vat_amount, 2),
            "total": round(total, 2),
            "currency": currency.upper(),
            "source_file": source_file,
            "notes": notes,
            "created_by": "claude-agent",
            "flags": flags,
        })
        self._save(data)
        return DraftResult(voucher_id=voucher_id, status=status, flags=flags)

    # ---------- human-only actions (not exposed to Claude) ----------
    def set_status(self, voucher_id: str, status: str, by: str) -> dict:
        if status not in {"booked", "rejected"}:
            raise ERPError("Status must be 'booked' or 'rejected'.")
        data = self._load()
        for v in data["vouchers"]:
            if v["id"] == voucher_id:
                if v["status"] not in {"draft", "needs_review"}:
                    raise ERPError(f"{voucher_id} is already {v['status']}.")
                v["status"] = status
                v["decided_by"] = by
                self._save(data)
                return v
        raise ERPError(f"No voucher {voucher_id}.")
