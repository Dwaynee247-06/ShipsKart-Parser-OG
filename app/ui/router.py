"""UI router — serves the Jinja2 HTML frontend via FastAPI.

Routes
------
GET  /        → upload form (index.html)
POST /upload  → parse & match, renders results.html
"""
from __future__ import annotations

from typing import List

import httpx
from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(tags=["UI"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Layer number → API param name mapping
_LAYER_MAP = {
    "1": "use_levenshtein",
    "2": "use_tfidf",
    "3": "use_inverted_index",
    "4": "use_phonetic",
}

# ── helpers ──────────────────────────────────────────────────────────────

def _api_base(request: Request) -> str:
    """Return the base URL of this same FastAPI server."""
    return str(request.base_url).rstrip("/")


# ── routes ───────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html"
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    top_n: int = Form(5),
    advanced: str = Form("off"),
    layers: List[str] = Form(default=[]),
):
    adv = advanced == "on"

    # Build the layers query params for the API
    # Each selected layer number maps to a named bool param
    active_layers = [int(l) for l in layers if l in _LAYER_MAP]

    api_base = _api_base(request)

    # Build query params: advanced + top_n + layers as repeated integers
    params: list = [
        ("advanced", str(adv).lower()),
        ("top_n", top_n),
    ]
    for layer_num in active_layers:
        params.append(("layers", layer_num))

    file_bytes = await file.read()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{api_base}/api/v1/parse/match",
                params=params,
                files={"file": (file.filename, file_bytes, file.content_type)},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": f"API error: {exc}"},
        )

    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "response":      data,
            "api_base":      api_base,
            "top_n":         top_n,
            "advanced":      adv,
            "active_layers": active_layers,
        },
    )
