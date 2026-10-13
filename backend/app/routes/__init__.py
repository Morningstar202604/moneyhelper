"""Route modules: each subpackage registers CRUD + query routes on the main app's router.

Keeps main.py focused on middleware / core endpoints (ask, confirm, bootstrap, dashboard).
"""

from fastapi import APIRouter

# Re-export each sub-router for inclusion in the main app.
from .budgets import router as budgets_router
from .calculations import router as calculations_router
from .goals import router as goals_router
from .debts_subs import router as debts_subs_router
from .market import router as market_router
from .import_routes import router as import_router
from .provenance import router as provenance_router
from .members import router as members_router
from .family import router as family_router

__all__ = ["budgets_router", "calculations_router", "goals_router", "debts_subs_router", "market_router", "import_router", "provenance_router", "members_router", "family_router"]
