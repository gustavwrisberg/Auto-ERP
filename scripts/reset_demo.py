"""Reset the mock ERP to its seed data and clear the logs, so every demo starts the same."""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from erp import MockERP  # noqa: E402

MockERP().reset()
shutil.rmtree(ROOT / "logs", ignore_errors=True)
print("Mock ERP reset to data/seed.json and logs cleared.")
