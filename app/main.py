from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.jobs import router as parse_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging(debug=settings.debug)

app = FastAPI(
    title="Excel Parser API",
    version="1.0.0",
    description="Upload an Excel file and get parsed tabular JSON directly.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# NOTE: allow_credentials=True is incompatible with allow_origins=["*"].
# Browsers reject credentialed requests when the origin is a wildcard.
# Use allow_credentials=False for open APIs, or replace "*" with specific
# origins if you need cookie/auth header support.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(parse_router, prefix=settings.api_v1_prefix)
