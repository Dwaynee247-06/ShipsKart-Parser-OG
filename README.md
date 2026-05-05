# ShipsKart Parser API

> FastAPI service that parses maritime provision/requisition documents (Excel, Word, PDF) and fuzzy-matches every line item against a product master database — with full support for Hindi, Marathi, and regional-language item names.

---

## Features

- Upload **Excel** (`.xlsx`, `.xlsm`), **Word** (`.docx`, `.doc`), or **PDF** files.
- Auto-detect and parse tabular data (SR. NO., ITEMS, UNIT, QTY, etc.).
- Normalize multi-page PDFs into a single logical table.
- **Regional-language alias resolution** — Hindi/Marathi item names (e.g. `limbu`, `nimbu`, `aloo`, `gosht`) are transparently mapped to their English equivalents before matching.
- Fuzzy-match each item name against the Product master table using a weighted `rapidfuzz` scorer.
- Return top **N** product matches per row with a similarity score.
- Simple API surface — just two endpoints:
  - `GET  /api/v1/health`
  - `POST /api/v1/parse/match`

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| PDF Parsing | pdfplumber |
| Excel Parsing | openpyxl |
| Word Parsing | python-docx |
| Database / ORM | SQL Server + SQLAlchemy |
| Fuzzy Matching | rapidfuzz |
| Migrations | Alembic |

---

## API Overview

### Health Check

**GET** `/api/v1/health`

Returns a simple status response:

```json
{
  "status": "ok",
  "service": "ShipsKart Parser API",
  "version": "1.1.0",
  "timestamp": "2026-05-05T06:00:00Z"
}
```

### Parse & Match

**POST** `/api/v1/parse/match`

**Request:**
- Content-Type: `multipart/form-data`
- Field: `file` — Excel (`.xlsx` / `.xlsm`), Word (`.docx` / `.doc`), or PDF (`.pdf`)
- Query param: `top_n` *(optional, default `5`)* — number of best matches per item

**Example using `curl`:**

```bash
curl -X POST "http://localhost:8000/api/v1/parse/match?top_n=5" \
  -F "file=@OWNER-SHEET-APJ-SHIRIN-PROVISION-QUOTATION-MUNDRA.xlsx"
```

**Response shape:**

```json
{
  "tables": {
    "table_1": {
      "document_info": {},
      "headers": ["sr_no", "items", "unit", "qty", "category", "rate", "gst", "amount"],
      "rows": [
        {
          "sr_no": "1",
          "items": "Chicken Dressed Broiler",
          "unit": "Kg",
          "qty": "100",
          "category": "NON-VEG",
          "rate": "276.00",
          "gst": "0",
          "amount": "27600.00",
          "matches": [
            {
              "rank": 1,
              "score_pct": 98.5,
              "product_id": 1,
              "product_name": "Chicken Dressed Broiler",
              "category": "Non-Veg",
              "brand": "Generic",
              "unit": "Kg"
            }
          ]
        }
      ]
    }
  },
  "summary": {
    "total_items": 50,
    "matched_above_80": 46,
    "matched_above_50": 3,
    "unmatched": 1
  }
}
```

Interactive docs: **http://localhost:8000/docs** | **http://localhost:8000/redoc**

---

## Matching Logic

Located in `app/services/matcher.py`.

For each parsed row the matcher runs in **two passes** and picks the higher score:

1. **Pass 1 — Raw name**: score the item name as-is.
2. **Pass 2 — Alias-resolved name**: run `_resolve_alias()` to translate regional/Hindi names to English, then score again.

Each pass computes:

```
score = 0.7 × token_set_ratio + 0.3 × partial_ratio
```

- `token_set_ratio` — word-order tolerant ("Broiler Dressed Chicken" still matches "Chicken Dressed Broiler")
- `partial_ratio` — handles substrings and partial names

**Example — alias resolution in action:**

```
"Nimbu"  →  _resolve_alias()  →  "lemon"
score("Nimbu",  "Lemon") = 40%   ← fuzzy alone fails
score("lemon",  "Lemon") = 100%  ← alias wins ✅
```

### ALIAS_MAP — Regional Name Dictionary

`matcher.py` ships with 100+ Hindi/Marathi/regional → English mappings:

| Category | Examples |
|---|---|
| Fruits | `limbu / nimbu → lemon`, `malta → mandarin orange`, `kela → banana`, `tarbuj → watermelon`, `aam → mango` |
| Vegetables | `aloo → potatoes`, `pyaz → onion`, `baingan → eggplant`, `bhindi → lady finger`, `lauki → bottle gourd`, `palak → spinach` |
| Meat / Seafood | `murgi → chicken`, `gosht → mutton`, `machli → fish`, `jhinga → prawns`, `anda → eggs` |
| Dairy | `doodh → milk`, `dahi → yoghurt`, `paneer → cottage cheese`, `makkhan → butter` |
| Dry Goods / Spices | `haldi → turmeric`, `jeera → cumin`, `chawal → rice`, `atta → wheat flour`, `dal → lentils` |

To add more aliases, append to `ALIAS_MAP` in `matcher.py` — no other code changes needed.

### Score Buckets

The `summary` block in the response classifies every item:

| Bucket | Condition |
|---|---|
| `matched_above_80` | Best match score ≥ 80% |
| `matched_above_50` | Best match score ≥ 50% and < 80% |
| `unmatched` | Best match score < 50% |

---

## Project Structure

```text
app/
  main.py                        # FastAPI app, router registration
  api/
    deps.py                      # get_db() dependency
    v1/
      routes/
        health.py                # GET /health
        parse.py                 # POST /parse/match
  core/
    config.py                    # Settings (API prefix, allowed extensions, DB URL)
    exceptions.py                # UnsupportedFileTypeError and other custom exceptions
    logging.py                   # Logging configuration
  db/
    base.py                      # SQLAlchemy declarative Base
    session.py                   # Engine + SessionLocal
  models/
    product.py                   # Category, Brand, Product ORM models
  schemas/
    job.py                       # Pydantic response models (HealthResponse, etc.)
  services/
    files.py                     # File save/read helpers
    matcher.py                   # Fuzzy matching engine + ALIAS_MAP
    parsers/
      __init__.py                # dispatch_parser() — routes by extension
      excel.py                   # Excel parsing logic (openpyxl)
      pdf.py                     # PDF parsing + multi-page stitching (pdfplumber)
      word.py                    # Word parsing logic (python-docx)
      _shared.py                 # Shared helpers (build_table_from_rows, clean_cell)
  utils/
    time.py                      # utc_now()
alembic/                         # DB migration scripts
scripts/                         # Utility / seed scripts
requirements.txt
alembic.ini
```

---

## Database Schema

This service expects a **product master database** with three tables: `Category`, `Brand`, and `Product`.

### Category

```sql
CREATE TABLE Category (
  CategoryID   INT           PRIMARY KEY IDENTITY,
  CategoryName NVARCHAR(100) NOT NULL UNIQUE,
  Description  NVARCHAR(255) NULL
);
```

### Brand

```sql
CREATE TABLE Brand (
  BrandID   INT           PRIMARY KEY IDENTITY,
  BrandName NVARCHAR(150) NOT NULL UNIQUE,
  Notes     NVARCHAR(255) NULL
);
```

### Product

```sql
CREATE TABLE Product (
  ProductID     INT           PRIMARY KEY IDENTITY,
  ProductName   NVARCHAR(200) NOT NULL,
  CategoryID    INT           NOT NULL REFERENCES Category(CategoryID),
  BrandID       INT           NOT NULL REFERENCES Brand(BrandID),
  UnitOfMeasure NVARCHAR(20)  NOT NULL,
  IsActive      BIT           NOT NULL DEFAULT 1,
  CreatedAt     DATETIME      NOT NULL DEFAULT GETDATE()
);
```

Populate `Category`, `Brand`, and `Product` from the owner sheet or another master source before running the service.

---

## Running Locally

### Prerequisites

- Python 3.10+
- SQL Server instance (local or network)
- Microsoft ODBC Driver 17 or 18 for SQL Server

### Setup

```bash
git clone https://github.com/Dwaynee247-06/ShipsKart-Parser-OG.git
cd ShipsKart-Parser-OG

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Configure your `.env` file:

```env
DATABASE_URL=mssql+pyodbc://USER:PASSWORD@SERVER/ShipsKartDB?driver=ODBC+Driver+17+for+SQL+Server
API_V1_PREFIX=/api/v1
APP_NAME=ShipsKart Parser API
APP_VERSION=1.1.0
```

### Start the server

```bash
uvicorn app.main:app --reload
```

---

## Testing the Parser

Sample test files can be used directly:

| File | Format | Use |
|---|---|---|
| `test_provision_sample.xlsx` | Excel | Smaller replica of the owner sheet |
| `test_provision_sample.docx` | Word | Same data in `.docx` table format |

1. Run the app and open Swagger: `http://localhost:8000/docs`
2. Go to `POST /api/v1/parse/match`
3. Upload one of the test files
4. Inspect `tables[table_1].rows[].matches[]` and `score_pct` values

You can also test with scanned / multi-page PDFs — the `pdf.py` parser stitches multiple pages into one logical table.

---

## Future Improvements

- Add authentication (API keys / JWT) for production.
- Support configurable match thresholds (e.g., flag items with score < 60%).
- Add admin endpoints to manage `Product`, `Brand`, and `Category` directly via the API.
- Add unit tests for parsers and matcher using `pytest`.
- Add pagination / filtering for large tables.
- OCR support for scanned PDFs (e.g., via Tesseract).
- Expand `ALIAS_MAP` with more regional languages (Gujarati, Tamil, Bengali).

---
