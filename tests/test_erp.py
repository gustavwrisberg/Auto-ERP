"""Offline tests: business rules in the mock ERP and the MCP server's guardrails. No API key needed."""

import importlib
import json

import pytest

from erp import ERPError, MockERP

GOOD = dict(supplier_id="S100", invoice_number="K-1", invoice_date="2026-11-18", due_date="2026-12-02",
            account=2800, vat_code="I25", amount_excl_vat=100.0, vat_amount=25.0, total=125.0)


@pytest.fixture
def erp(tmp_path, monkeypatch):
    monkeypatch.setenv("ERP_STATE_FILE", str(tmp_path / "erp.json"))
    monkeypatch.setenv("ERP_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("DEMO_TODAY", "2026-11-24")
    return MockERP()


def test_clean_invoice_becomes_plain_draft(erp):
    r = erp.create_draft_voucher(**GOOD)
    assert r.status == "draft" and r.flags == []
    assert erp.vouchers("draft")[0]["invoice_number"] == "K-1"


def test_unknown_supplier_is_refused(erp):
    with pytest.raises(ERPError, match="Unknown supplier"):
        erp.create_draft_voucher(**{**GOOD, "supplier_id": "S999"})


def test_duplicate_is_refused(erp):
    with pytest.raises(ERPError, match="Duplicate"):
        erp.create_draft_voucher(**{**GOOD, "supplier_id": "S101", "invoice_number": "NF-77120"})


@pytest.mark.parametrize("change, flag", [
    ({"total": 130.0}, "do not add up"),
    ({"vat_amount": 20.0, "total": 120.0}, "VAT"),
    ({"amount_excl_vat": 48000.0, "vat_amount": 12000.0, "total": 60000.0}, "approval limit"),
    ({"currency": "EUR"}, "Foreign currency"),
    ({"account": 2210}, "differs from supplier default"),
])
def test_suspicious_drafts_need_review(erp, change, flag):
    r = erp.create_draft_voucher(**{**GOOD, **change})
    assert r.status == "needs_review"
    assert any(flag in f for f in r.flags)


def test_dry_run_saves_nothing(erp):
    r = erp.create_draft_voucher(**GOOD, dry_run=True)
    assert r.dry_run and erp.vouchers("draft") == []


def test_overdue_invoices_sorted(erp):
    overdue = erp.overdue_invoices()
    assert [i["number"] for i in overdue] == [1041, 1043]
    assert overdue[0]["days_overdue"] == 40


def test_only_humans_book(erp):
    r = erp.create_draft_voucher(**GOOD)
    erp.set_status(r.voucher_id, "booked", by="tester")
    with pytest.raises(ERPError):
        erp.set_status(r.voucher_id, "booked", by="tester")


def _load_server(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("ERP_STATE_FILE", str(tmp_path / "erp.json"))
    monkeypatch.setenv("ERP_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import erp_mcp.server as server
    return importlib.reload(server)


@pytest.mark.anyio
async def test_server_exposes_no_booking_tool(monkeypatch, tmp_path):
    s = _load_server(monkeypatch, tmp_path, ERP_READ_ONLY="0")
    names = {t.name for t in await s.server.list_tools()}
    assert "create_draft_voucher" in names
    assert not any(word in n for n in names for word in ("book", "pay", "delete"))


@pytest.mark.anyio
async def test_read_only_mode_removes_write_tool(monkeypatch, tmp_path):
    s = _load_server(monkeypatch, tmp_path, ERP_READ_ONLY="1")
    names = {t.name for t in await s.server.list_tools()}
    assert "create_draft_voucher" not in names


def test_every_call_is_audited(monkeypatch, tmp_path):
    s = _load_server(monkeypatch, tmp_path, ERP_READ_ONLY="0")
    s.list_suppliers(query="nordvind")
    with pytest.raises(ERPError):
        s.create_draft_voucher(**{**GOOD, "supplier_id": "S999"})
    lines = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [(e["tool"], e["ok"]) for e in lines] == [("list_suppliers", True), ("create_draft_voucher", False)]


@pytest.fixture
def anyio_backend():
    return "asyncio"
