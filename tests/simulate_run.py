"""Fill the mock ERP with the drafts a perfect agent run would create (no API key needed).
Used in CI to check that the eval script and approval CLI work end to end."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from erp import MockERP  # noqa: E402

FIELDS = ["supplier_id", "invoice_number", "invoice_date", "due_date", "account", "vat_code",
          "amount_excl_vat", "vat_amount", "total", "currency"]

erp = MockERP()
erp.reset()
for file, exp in json.loads((ROOT / "evals" / "expected.json").read_text()).items():
    if file.startswith("_") or exp["result"] == "skipped":
        continue
    erp.create_draft_voucher(**{k: exp[k] for k in FIELDS}, source_file=file)
print("Simulated a perfect run.")
