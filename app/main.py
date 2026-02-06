"""
Nomadays SaaS API - Main application entry point.

A comprehensive platform for DMC (Destination Management Companies)
with quotation engine, contract management, and AI-powered price control.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import (
    auth,
    tenants,
    suppliers,
    contracts,
    trips,
    quotation,
    alerts,
    dashboard,
    formulas,
    dossiers,
    travel_themes,
    exchange_rates,
    trip_locations,
    country_templates,
    partner_agencies,
    distribution,
    import_circuit,
    translate_circuit,
    trip_preview,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print(f"🚀 Starting {settings.app_name}...")
    yield
    # Shutdown
    print(f"👋 Shutting down {settings.app_name}...")


app = FastAPI(
    title=settings.app_name,
    description="""
    ## Nomadays SaaS API

    A comprehensive platform for DMC (Destination Management Companies) featuring:

    - **Quotation Engine**: Calculate trip costs with complex pricing rules
    - **Contract Management**: Track supplier contracts and rates
    - **AI Price Controller**: Detect pricing anomalies and expiring contracts
    - **Multi-tenant Architecture**: Complete data isolation between DMCs

    ### Authentication
    All endpoints require JWT authentication. Use `/auth/login` to obtain a token.
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
app.include_router(suppliers.router, prefix="/suppliers", tags=["Suppliers"])
app.include_router(contracts.router, prefix="/contracts", tags=["Contracts"])
app.include_router(trips.router, prefix="/trips", tags=["Trips"])
app.include_router(quotation.router, prefix="/quotation", tags=["Quotation Engine"])
app.include_router(alerts.router, prefix="/alerts", tags=["AI Alerts"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(formulas.router, prefix="/trip-structure", tags=["Formulas & Items"])
app.include_router(dossiers.router, prefix="/dossiers", tags=["Dossiers"])
app.include_router(travel_themes.router, prefix="/travel-themes", tags=["Travel Themes"])
app.include_router(exchange_rates.router, prefix="/exchange-rates", tags=["Exchange Rates"])
app.include_router(trip_locations.router)  # Nested under /trips/{trip_id}/locations
app.include_router(trip_locations.places_router)  # /places endpoints
app.include_router(country_templates.router)  # /templates endpoints
app.include_router(partner_agencies.router)  # /partner-agencies endpoints
app.include_router(distribution.router)  # Public distribution API /api/v1/catalog
app.include_router(import_circuit.router)  # Circuit import from URL /import
app.include_router(translate_circuit.router, prefix="/translate", tags=["Translation"])  # Circuit translation
app.include_router(trip_preview.router, prefix="/trips", tags=["Trip Preview"])  # Translation preview with cache


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "connected",  # TODO: actual check
        "ai": "available" if settings.anthropic_api_key else "not_configured",
    }
