from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.parse import router as parse_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging(debug=settings.debug)

app = FastAPI(
    title="ShipsKart Parser API",
    version="1.1.0",
    description=(
        "Upload Excel or PDF shipping documents to:\n"
        "- **Parse** them into structured JSON\n"
        "- **Match** every line item against the Product master database\n"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(parse_router,  prefix=settings.api_v1_prefix)
