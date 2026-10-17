"""Route modules: each subpackage registers CRUD + query routes on the main app's router.

Keeps main.py focused on middleware / core endpoints (ask, confirm, bootstrap, dashboard).
"""

# Re-export each sub-router for inclusion in the main app.
from .budgets import router as budgets_router
from .calculations import router as calculations_router
from .debts_subs import router as debts_subs_router
from .family import router as family_router
from .goals import router as goals_router
from .import_routes import router as import_router
from .market import router as market_router
from .members import router as members_router
from .provenance import router as provenance_router
from .settings import router as settings_router

__all__ = ["budgets_router", "calculations_router", "debts_subs_router", "family_router", "goals_router", "import_router", "market_router", "members_router", "provenance_router",
           "settings_router"]
