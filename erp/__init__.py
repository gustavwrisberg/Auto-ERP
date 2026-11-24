"""ERP backends. MockERP runs offline; erp.economic shows how to plug in a real system."""

import os

from .backend import DraftResult, ERPError, MockERP, today


def get_backend():
    """Pick the backend from ERP_BACKEND (default: mock)."""
    name = os.environ.get("ERP_BACKEND", "mock").lower()
    if name == "mock":
        return MockERP()
    if name == "economic":
        from .economic import EconomicERP

        return EconomicERP.from_env()
    raise ValueError(f"Unknown ERP_BACKEND '{name}' (use 'mock' or 'economic')")


__all__ = ["DraftResult", "ERPError", "MockERP", "get_backend", "today"]
