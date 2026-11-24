"""The human step: review drafts Claude created and book or reject them.

    python scripts/approve.py            # interactive review
    python scripts/approve.py --list     # just show what is waiting

Claude has no tool that books anything; only this script (a person) can.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from erp import MockERP  # noqa: E402


def show(v: dict, suppliers: dict) -> None:
    name = suppliers.get(v["supplier_id"], {}).get("name", v["supplier_id"])
    mark = "REVIEW" if v["status"] == "needs_review" else "ok"
    print(f"\n[{v['id']}] {mark:6}  {name}  invoice {v['invoice_number']}  ({v['invoice_date']}, due {v.get('due_date') or '-'})")
    print(f"         account {v['account']}  VAT {v['vat_code']}  "
          f"{v['amount_excl_vat']:,.2f} + {v['vat_amount']:,.2f} = {v['total']:,.2f} {v['currency']}")
    for flag in v.get("flags", []):
        print(f"         ! {flag}")
    if v.get("notes"):
        print(f"         note: {v['notes']}")
    print(f"         source: {v.get('source_file') or '-'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    erp = MockERP()
    suppliers = {s["id"]: s for s in erp.suppliers()}
    waiting = erp.vouchers("draft") + erp.vouchers("needs_review")
    if not waiting:
        print("Nothing waiting for approval.")
        return

    print(f"{len(waiting)} voucher(s) waiting for approval")
    user = getpass.getuser()
    for v in waiting:
        show(v, suppliers)
        if args.list:
            continue
        answer = input("         [b]ook / [r]eject / [s]kip? ").strip().lower()
        if answer == "b":
            erp.set_status(v["id"], "booked", by=user)
            print("         booked")
        elif answer == "r":
            erp.set_status(v["id"], "rejected", by=user)
            print("         rejected")


if __name__ == "__main__":
    main()
