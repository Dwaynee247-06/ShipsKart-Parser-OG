# ShipsKart Parser

A **FastAPI-based** parser and intelligent product-matching system for maritime procurement documents — Excel, PDF, and Word. It extracts structured line items, detects useful headers even from messy sheets, and matches parsed item names against the ShipsKart product catalog using a multi-layer fuzzy matching engine.

Both the **browser UI** and **REST API** are served by the same FastAPI process on a single port — no separate frontend server required.

---

## Features

- Parse `.xlsx`, `.xls`, `.pdf`, `.docx`, `.doc` procurement documents into structured table data
- Detect useful headers even when column names are messy, misspelled, abbreviated, or buried mid-sheet
- Resolve regional and Hindi aliases (`baingan → egg plant`, `murg → chicken`, etc.)
- Match extracted item names against the product catalog with **Legacy** or **Advanced** mode
- Handle heavy typos like `"Chiken Dresed Broylr"` using four configurable matching layers
- Return top-N candidate matches per row (default: 5) for human review
- Cache confirmed matches to speed up repeated queries
- Built-in Jinja2 browser UI served directly by FastAPI — no Flask, no second server

---

## Project Structure

```
ShipsKart-Parser-OG/
├── app/
│   ├── api/             # REST API route handlers (/api/v1/...)
│   ├── core/            # Settings, config, logging
│   ├── db/              # Database session and connection
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/
│   │   ├── files.py     # File parsing (Excel, PDF, Word)
│   │   ├── matcher.py   # Matching service wrapper + alias map
│   │   └── matching.py  # Core ProductMatcher implementation
│   ├── ui/              # Browser UI (FastAPI router + Jinja2 templates)
│   │   ├── router.py    # Handles GET / and POST /upload
│   │   └── templates/
│   │       ├── base.html    # Shared layout, design tokens, nav
│   │       ├── index.html   # Upload form
│   │       └── results.html # Match results display
│   ├── tests/           # Pytest test suite
│   ├── utils/           # Shared utilities
│   └── main.py          # FastAPI app entrypoint
├── alembic/             # Database migrations
├── scripts/             # Helper scripts
├── alembic.ini
├── requirements.txt
└── README.md
```

---

## Quick Start

```bash
git clone https://github.com/Dwaynee247-06/ShipsKart-Parser-OG.git
cd ShipsKart-Parser-OG
pip install -r requirements.txt
uvicorn app.main:app --reload
```

| URL | What you get |
|-----|--------------|
| `http://127.0.0.1:8000/` | Browser upload UI |
| `http://127.0.0.1:8000/docs` | Swagger API explorer |
| `http://127.0.0.1:8000/redoc` | ReDoc API reference |

---

## Matching Modes

### Legacy Matcher

Fast matching for clean or semi-clean input. Uses:

- Alias expansion (Hindi/regional names → English catalog terms)
- `token_set_ratio` — handles word-order changes
- `partial_ratio` — handles substring overlap

### Advanced Matcher (Multi-Layer)

A four-layer pipeline that handles typos, abbreviations, and phonetic variants. Layers are selected by **number** in both the UI and API.

| # | Name | Strategy | Best For |
|---|------|----------|----------|
| 1 | Levenshtein | Character-level edit distance | Typos, OCR errors |
| 2 | TF-IDF | Character n-gram cosine similarity | Abbreviations, partial names |
| 3 | Inverted Index | Token prefilter index | Speed, broad token overlap |
| 4 | Phonetic | Soundex / phonetic grouping | Different spellings, same sound |

All four layers are **recommended** and enabled by default. Disabling any layer reduces accuracy.

> **UI vs API:** The browser UI intentionally shows only layer numbers (1 · 2 · 3 · 4) to keep the interface simple for operators. The API and Swagger UI expose the full named enum for developers.

#### Adaptive score weighting

Scores from active layers are blended based on query length:

- **Short queries (1–2 words):** Levenshtein 35% · Phonetic 20% · Token 20% · TF-IDF 25%
- **Longer queries:** TF-IDF 40% · Token 30% · Levenshtein 20% · Phonetic 10%

#### Match status thresholds

| Status | Score | Meaning |
|--------|-------|---------|
| `confident` | ≥ 72 | Auto-selectable match |
| `candidate` | 45–71 | Top candidates shown for review |
| `no_match` | < 45 | No reliable catalog match found |
| `cached` | — | Previously confirmed; returned instantly |

---

## API Reference

### Parse + Match a file

```http
POST /api/v1/parse/match
Content-Type: multipart/form-data

file=<your_file>
advanced=true
top_n=5
layers=1&layers=2&layers=3&layers=4
```

**`layers` parameter** — pass one or more integers (repeat the param):

| Value | Layer |
|-------|-------|
| `1` | Levenshtein |
| `2` | TF-IDF |
| `3` | Inverted Index |
| `4` | Phonetic |

### Confirm a match

```http
POST /api/v1/confirm_match
Content-Type: application/json

{
  "raw_query": "chiken dressed broylr",
  "product_id": 42
}
```

### Health check

```http
GET /api/v1/health
```

Full interactive docs with request/response schemas: **`/docs`**

---

## Alias Map (examples)

| Input | Resolves to |
|-------|-------------|
| `baingan` | egg plant |
| `tamatar` | tomatoes |
| `murg` | chicken |
| `hari mirch` | green hot peppers |
| `palak` | spinach |
| `kheera` | cucumber |
| `aata` | wheat flour |

---

## Database Migrations (Alembic)

```bash
# Create a new migration
alembic revision --autogenerate -m "your message"

# Apply all pending migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

---

## Running Tests

```bash
pytest app/tests/
```

---

## Tech Stack

| Layer | Library |
|-------|---------|
| API & UI | FastAPI + Jinja2 |
| ORM | SQLAlchemy + Alembic |
| Fuzzy matching | RapidFuzz |
| Phonetic matching | Jellyfish |
| Vector similarity | scikit-learn (TF-IDF) |
| Excel parsing | openpyxl |
| PDF parsing | pdfplumber |
| Word parsing | python-docx |
| Async HTTP (internal) | httpx |
| Testing | pytest + httpx |

---

## Requirements

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9
jinja2>=3.1.0
httpx>=0.27.0
openpyxl>=3.1.0
python-docx>=1.1.0
pdfplumber>=0.11.0
orjson>=3.10.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
sqlalchemy>=2.0.0
pyodbc>=5.1.0
alembic>=1.13.0
rapidfuzz>=3.9.0
jellyfish>=1.0.0
scikit-learn>=1.4.0
pytest>=8.0.0
```

> **Note:** `jellyfish` enables the Phonetic layer (Layer 4 / Soundex). If not installed, that layer is skipped gracefully and the remaining layers still run.

---

## Author

Built by [Dwayne Dsouza](https://github.com/Dwaynee247-06) for ShipsKart parsing and smart product-matching workflows.
