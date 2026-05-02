# ShipsKart Parser API

FastAPI service to parse provision / requisition documents (Excel, Word, PDF) and match each line item against a product master database.

---

## Features

- Upload **Excel** (`.xlsx`, `.xlsm`), **Word** (`.docx`, `.doc`), or **PDF** files.
- Auto-detect and parse tabular data (SR. NO., ITEMS, UNIT, QTY, etc.).
- Normalize multi-page PDFs into a single logical table.
- Fuzzy-match each item name against the Product master table.
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
  "timestamp": "2026-05-02T06:20:00Z"
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
    matcher.py                   # Fuzzy matching against Product table
    parsers/
      __init__.py                # dispatch_parser() — routes by extension
      excel.py                   # Excel parsing logic (openpyxl)
      pdf.py                     # PDF parsing + multi-page stitching (pdfplumber)
      word.py                    # Word parsing logic (python-docx)
      _shared.py                 # Shared helpers (build_table_from_rows, clean_cell)
  utils/
    time.py                      # utc_now()
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

## Matching Logic

Located in `app/services/matcher.py`.

For each parsed row:

1. Take the `items` field (fallback to `description` if present).
2. Compare it against every active `ProductName` in the DB using:
   - `token_set_ratio(query, product_name)` — word-order tolerant
   - `partial_ratio(query, product_name)` — handles substrings / aliases
   - `score = 0.7 × token_set_ratio + 0.3 × partial_ratio`
3. Sort products by `score` descending.
4. Return the top `top_n` products as `matches[]`.

The `summary` block in the response counts:

| Bucket | Condition |
|---|---|
| `matched_above_80` | Best match score ≥ 80% |
| `matched_above_50` | Best match score ≥ 50% and < 80% |
| `unmatched` | Best match score < 50% |

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

Sample test files are available to use directly:

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

---