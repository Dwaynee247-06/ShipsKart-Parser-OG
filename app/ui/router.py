"""UI router — serves the Jinja2 HTML frontend via FastAPI.

Routes
------
GET  /        → upload form (index.html)
POST /upload  → parse & match, renders results.html
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(tags=["UI"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

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
    use_lev: str = Form("off"),
    use_tfidf: str = Form("off"),
    use_inv: str = Form("off"),
    use_phonetic: str = Form("off"),
):
    adv      = advanced == "on"
    lev      = use_lev == "on"
    tfidf    = use_tfidf == "on"
    inv      = use_inv == "on"
    phonetic = use_phonetic == "on"

    api_base = _api_base(request)
    params = {
        "advanced":           str(adv).lower(),
        "use_levenshtein":    str(lev).lower(),
        "use_tfidf":          str(tfidf).lower(),
        "use_inverted_index": str(inv).lower(),
        "use_phonetic":       str(phonetic).lower(),
        "top_n":              top_n,
    }

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
            "response":   data,
            "api_base":   api_base,
            "top_n":      top_n,
            "advanced":   adv,
            "use_lev":    lev,
            "use_tfidf":  tfidf,
            "use_inv":    inv,
            "use_phonetic": phonetic,
        },
    )
