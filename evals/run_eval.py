"""Score the last agent run against evals/expected.json.

    python scripts/reset_demo.py
    python -m agent.invoice_intake
    python evals/run_eval.py

Checks every field of every expected draft, and that skipped invoices produced no draft.
This is the number you show a client: "X of Y fields correct, 0 wrong bookings".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from erp import MockERP  # noqa: E402

FIELDS = ["supplier_id", "invoice_number", "invoice_date", "due_date", "account", "vat_code",
          "amount_excl_vat", "vat_amount", "total", "currency"]


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.01
    return str(a).strip().lower() == str(b).strip().lower()


def main() -> int:
    expected = {k: v for k, v in json.loads((ROOT / "evals" / "expected.json").read_text()).items() if not k.startswith("_")}
    created = {v["source_file"].split("/")[-1]: v for v in MockERP().vouchers() if v.get("created_by") == "claude-agent"}

    field_ok = field_total = cases_ok = 0
    for file, exp in expected.items():
        got = created.get(file)
        if exp["result"] == "skipped":
            ok = got is None
            print(f"{'PASS' if ok else 'FAIL'}  {file}: expected no draft ({exp['reason']})"
                  + ("" if ok else f", got {got['id']}"))
        elif got is None:
            ok = False
            field_total += len(FIELDS)
            print(f"FAIL  {file}: no draft created")
        else:
            wrong = [f for f in FIELDS if not same(got.get(f), exp[f])]
            field_total += len(FIELDS)
            field_ok += len(FIELDS) - len(wrong)
            status_ok = got["status"] == exp["result"]
            ok = not wrong and status_ok
            detail = "" if ok else " | " + ", ".join(
                [f"{f}: got {got.get(f)!r}, want {exp[f]!r}" for f in wrong]
                + ([] if status_ok else [f"status: got {got['status']}, want {exp['result']}"]))
            print(f"{'PASS' if ok else 'FAIL'}  {file}{detail}")
        cases_ok += ok

    print(f"\n{cases_ok}/{len(expected)} invoices handled correctly · "
          f"{field_ok}/{field_total} extracted fields correct")
    return 0 if cases_ok == len(expected) else 1


if __name__ == "__main__":
    sys.exit(main())
