"""Template adapter for a real e-conomic agreement (read-only parts sketched).

This shows the shape of a production adapter: same method names as MockERP, so the MCP
server and agent do not change. It is deliberately incomplete:

- Read methods call the e-conomic REST API (https://restapi.e-conomic.com) with the
  X-AppSecretToken / X-AgreementGrantToken headers. Verify field names against the
  current API docs before relying on them.
- create_draft_voucher is NOT implemented. In e-conomic, drafts are entries in a journal
  (kassekladde) that a person books in the UI. Implement it only on a test agreement,
  and keep booking as a human step.

Use a dedicated API user with the narrowest rights possible, and never commit tokens.
"""

from __future__ import annotations

import json
import os
import urllib.request

BASE_URL = os.environ.get("ECONOMIC_BASE_URL", "https://restapi.e-conomic.com")


class EconomicERP:
    def __init__(self, app_secret: str, grant_token: str, base_url: str = BASE_URL):
        self._headers = {
            "X-AppSecretToken": app_secret,
            "X-AgreementGrantToken": grant_token,
            "Content-Type": "application/json",
        }
        self._base = base_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "EconomicERP":
        try:
            return cls(os.environ["ECONOMIC_APP_SECRET_TOKEN"], os.environ["ECONOMIC_AGREEMENT_GRANT_TOKEN"])
        except KeyError as missing:
            raise RuntimeError(f"Set {missing} in your .env to use ERP_BACKEND=economic") from None

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(f"{self._base}{path}", headers=self._headers)
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https base URL
            return json.loads(resp.read())

    def company(self) -> dict:
        info = self._get("/self")
        return {"name": info.get("company", {}).get("name"), "currency": "DKK", "approval_limit_dkk": 50000}

    def accounts(self) -> list[dict]:
        return [{"number": a["accountNumber"], "name": a["name"]} for a in self._get("/accounts?pagesize=1000")["collection"]]

    def vat_codes(self) -> list[dict]:
        return [{"code": v["vatCode"], "name": v["name"], "rate": v.get("ratePercentage", 0) / 100}
                for v in self._get("/vat-accounts")["collection"]]

    def suppliers(self, query: str | None = None) -> list[dict]:
        items = [{"id": str(s["supplierNumber"]), "name": s["name"], "cvr": s.get("corporateIdentificationNumber")}
                 for s in self._get("/suppliers?pagesize=1000")["collection"]]
        if query:
            q = query.lower()
            items = [s for s in items if q in s["name"].lower() or q == (s["cvr"] or "")]
        return items

    def overdue_invoices(self, min_days: int = 1) -> list[dict]:
        raise NotImplementedError("Map /invoices/overdue to the MockERP format here.")

    def vouchers(self, status: str | None = None) -> list[dict]:
        raise NotImplementedError("Read journal entries (kassekladde) here.")

    def find_voucher(self, supplier_id: str, invoice_number: str) -> dict | None:
        raise NotImplementedError

    def create_draft_voucher(self, **kwargs):
        raise NotImplementedError("Implement against a TEST agreement first; booking stays a human step.")
