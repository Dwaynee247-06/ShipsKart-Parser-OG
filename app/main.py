"""
Excel Parser API — main application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.jobs import router as jobs_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.init_db import create_tables

configure_logging(debug=settings.debug)
create_tables()  # Auto-create parse_jobs table on startup if it does not exist

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Production-ready API for extracting, normalizing, and grouping tabular data "
        "from Excel workbooks. Stores job metadata in Microsoft SQL Server. "
        "Designed to be extended later with PDF, DOCX, and Image parsers."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(jobs_router, prefix=settings.api_v1_prefix)
