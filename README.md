# Excel Parser API

A production-ready FastAPI service that:
- Accepts Excel file uploads (`.xlsx`, `.xlsm`)
- Scans **every sheet** for **multiple table blocks**
- Normalizes headers (e.g. `Sr No` → `sr_no`, `Unit of measurement` → `unit_of_measurement`)
- Preserves **blank cells as `null`** in JSON
- Groups tables sharing the same header signature into `requirements1`, `requirements2`, ...
- Stores all job metadata in **Microsoft SQL Server** (managed via SSMS)
- Fast JSON output via `orjson`
- Designed for future extension with PDF, DOCX, and Image parsers

---

## Project Structure

```
excel_parser_final/
├── app/
│   ├── api/
│   │   ├── deps.py                  # DB dependency injection
│   │   └── v1/routes/
│   │       ├── health.py            # GET /health
│   │       └── jobs.py              # POST /jobs/parse, GET /jobs, GET /jobs/{id}, GET /jobs/{id}/result
│   ├── core/
│   │   ├── config.py                # All settings (env-driven)
│   │   ├── exceptions.py            # Custom HTTP exceptions
│   │   └── logging.py               # Logging setup
│   ├── db/
│   │   ├── base.py                  # SQLAlchemy DeclarativeBase
│   │   ├── init_db.py               # create_tables() on startup
│   │   └── session.py               # Engine + SessionLocal
│   ├── models/
│   │   ├── job.py                   # ParseJob SQLAlchemy model (parse_jobs table)
│   │   └── job_store.py             # Repository: create/get/update/list
│   ├── schemas/
│   │   └── job.py                   # Pydantic schemas for API I/O and parser output
│   ├── services/
│   │   ├── files.py                 # Upload saving, JSON writing
│   │   └── parsers/
│   │       └── excel.py             # Core Excel parser (multi-sheet, multi-table, grouping)
│   ├── utils/
│   │   └── time.py                  # UTC timestamp helper
│   ├── tests/
│   │   ├── test_parser.py           # Unit tests for parser logic
│   │   └── test_health.py           # Smoke test for API health endpoint
│   └── main.py                      # FastAPI app factory
├── alembic/                         # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                    # Migration scripts go here
├── alembic.ini
├── data/
│   ├── uploads/                     # Uploaded Excel files (gitignored)
│   └── results/                     # Generated JSON results (gitignored)
├── scripts/
│   └── create_sample_excel.py       # Generate a test workbook
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Prerequisites

1. **Python 3.11+**
2. **SQL Server** running locally or on a network server (managed via SSMS)
3. **Microsoft ODBC Driver 18 for SQL Server** installed on the machine running the API
   - Windows: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
   - Create the database first: `CREATE DATABASE ExcelParserDB;`

---

## Setup & Run

```bash
# 1. Clone / extract the project
cd excel_parser_final

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate 
#gitbash: python -m venv .venv
source .venv/Scripts/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set your DATABASE_URL

# 5. Start the API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The `parse_jobs` table is created automatically in SQL Server on first startup.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/jobs/parse` | Upload & parse an Excel file |
| GET | `/api/v1/jobs` | List all jobs (paginated) |
| GET | `/api/v1/jobs/{job_id}` | Get job status |
| GET | `/api/v1/jobs/{job_id}/result` | Download JSON result |

Interactive docs: **http://localhost:8000/docs**

---

## Example Usage

```bash
# Upload an Excel file
curl -X POST "http://localhost:8000/api/v1/jobs/parse" \
  -F "file=@sample_input.xlsx"

# Check status
curl "http://localhost:8000/api/v1/jobs/<job_id>"

# Download result
curl -L "http://localhost:8000/api/v1/jobs/<job_id>/result" -o result.json
```

---

## Sample JSON Output

```json
{
  "requirements1": {
    "requirement_name": "requirements1",
    "headers": ["sr_no", "product_name", "unit_of_measurement", "quantity", "remarks"],
    "header_signature": "sr_no|product_name|unit_of_measurement|quantity|remarks",
    "total_rows": 8,
    "tables": [
      {
        "sheet_name": "Sheet1",
        "table_id": "Sheet1__block_1_abc123",
        "source_range": "A1:E7",
        "headers": ["sr_no", "product_name", "unit_of_measurement", "quantity", "remarks"],
        "rows": [
          { "sr_no": 1, "product_name": "Cement", "unit_of_measurement": "KG", "quantity": 100, "remarks": null },
          { "sr_no": 2, "product_name": "Sand",   "unit_of_measurement": "LTR", "quantity": 200, "remarks": "Course sand" }
        ]
      },
      {
        "sheet_name": "Sheet2",
        "table_id": "Sheet2__block_1_def456",
        "source_range": "A1:E3",
        "rows": [
          { "sr_no": 5, "product_name": "Steel Rods", "unit_of_measurement": "KG", "quantity": 500, "remarks": "12mm dia" },
          { "sr_no": 6, "product_name": "Bricks", "unit_of_measurement": "Units", "quantity": 1000, "remarks": null }
        ]
      }
    ]
  },
  "requirements2": {
    "requirement_name": "requirements2",
    "headers": ["id", "vendor_name", "contact", "city"],
    "tables": [...]
  }
}
```

---

## Run Tests

```bash
pytest app/tests/ -v
```

---

## Generate Sample Excel for Testing

```bash
python scripts/create_sample_excel.py
# Creates: sample_input.xlsx
```

---

## Database (SQL Server / SSMS)

The API auto-creates a `parse_jobs` table with:

| Column | Type | Description |
|--------|------|-------------|
| id | INT (PK) | Auto-increment |
| job_id | VARCHAR(64) | UUID, indexed |
| status | VARCHAR(32) | processing / completed / failed |
| filename | VARCHAR(255) | Original uploaded filename |
| created_at | VARCHAR(64) | ISO UTC timestamp |
| completed_at | VARCHAR(64) | ISO UTC timestamp |
| error | TEXT | Error message if failed |
| result_file | VARCHAR(255) | JSON result filename |
| groups | INT | Number of grouped requirements |
| total_rows | INT | Total rows parsed |

View records in SSMS:
```sql
SELECT * FROM ExcelParserDB.dbo.parse_jobs ORDER BY id DESC;
```

---

## Future Extensions (Not in scope yet)
- PDF parser
- DOCX parser
- Image/OCR parser
- Celery + Redis for async background jobs
- S3 / Azure Blob for file storage
- Auth and role-based access
- Alembic migration scripts
