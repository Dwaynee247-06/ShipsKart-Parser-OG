# ShipsKart Parser OG

A **FastAPI-based** parser and intelligent product-matching system for maritime procurement documents — Excel, PDF, and Word. It extracts structured rows, detects useful headers even from messy or unusual sheets, and matches parsed item names against the ShipsKart product catalog using a multi-layer smart matcher.

---

## Features

- Parse Excel (`.xlsx`), PDF, and Word (`.docx`) procurement documents into structured table data
- Detect useful headers even when column names are messy, misspelled, abbreviated, or buried in the middle of the sheet
- Resolve regional and Hindi aliases (`baingan → egg plant`, `tamatar → tomatoes`, `murg → chicken`)
- Match extracted item names against the product catalog with **Legacy** or **Advanced** mode
- Handle heavy typos like `"Chiken Dresed Broylr"` using Levenshtein, phonetic, and TF-IDF layers
- Return top-5 candidate matches per row for user review
- Cache confirmed matches to speed up repeated queries
- Flask UI for interactive file upload and result review

---

## Project Structure

```
ShipsKart-Parser-OG/
├── app/
│   ├── api/             # FastAPI route handlers
│   ├── core/            # Settings, config, startup
│   ├── db/              # Database session and connection
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/
│   │   ├── files.py     # File parsing (Excel, PDF, Word)
│   │   ├── matcher.py   # Matching service wrapper + alias map
│   │   └── matching.py  # Core ProductMatcher implementation
│   ├── tests/           # Pytest test suite
│   ├── utils/           # Shared utilities
│   └── main.py          # FastAPI app entrypoint
├── alembic/             # Database migrations
├── flask_ui/            # Flask frontend for file upload + results
├── scripts/             # Helper scripts
├── alembic.ini
├── requirements.txt
└── README.md
```

---

## Matching Modes

### Legacy Matcher

Fast matching for clean or semi-clean input. Uses:

- Alias expansion (Hindi/regional names → English catalog terms)
- `token_set_ratio` — handles word-order changes
- `partial_ratio` — handles substring overlap

### Advanced Matcher (Multi-Layer)

A full 9-layer pipeline that handles heavy typos, unusual names, and phonetic variants.

| Layer | What it does |
|-------|-------------|
| **1. Normalization** | Lowercase, remove punctuation, collapse spaces |
| **2. Alias resolution** | Expand known Hindi/regional names to English |
| **3. Token fuzzy match** | RapidFuzz `token_set_ratio` + `partial_ratio` |
| **4. Levenshtein similarity** | Character-level edit distance — handles typos like `chiken → chicken` |
| **5. Phonetic similarity** | `jellyfish.soundex()` — matches words that sound alike even if spelled differently |
| **6. TF-IDF cosine similarity** | Character n-gram vectors — catches rewritten or paraphrased names |
| **7. Inverted index prefilter** | Narrows down candidates using shared tokens for speed |
| **8. Typo fallback** | If the index finds no candidates (heavy typos), scores **all** products instead |
| **9. Feedback cache** | Confirmed user selections are remembered for future queries |

#### Why the typo fallback exists

The inverted index works by finding products that share at least one word with the query. A heavily misspelled query like `"chiken dressed broylr"` shares **zero clean words** with `"chicken dressed broiler"`, so the index returns empty — and previously the matcher stopped there.

Now, when the index returns empty, the matcher falls back to scoring all products via Levenshtein, phonetic, and TF-IDF. This means heavy typos are still resolved correctly.

#### Adaptive score weighting

Scores are blended differently based on query length:

- **Short (1–2 words):** Levenshtein 35% · Phonetic 20% · Token 20% · TF-IDF 25%
- **Longer queries:** TF-IDF 40% · Token 30% · Levenshtein 20% · Phonetic 10%

#### Match status thresholds

| Status | Condition | Meaning |
|--------|-----------|---------|
| `confident` | Score ≥ 72 | Auto-selectable match |
| `candidate` | Score 45–71 | Top candidates shown for user review |
| `no_match` | Score < 45 | No reliable catalog match found |
| `cached` | In feedback cache | Previously confirmed; returned instantly |

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

## API Usage

### Run the server

```bash
uvicorn app.main:app --reload
```

Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Parse + match a file

```http
POST /api/v1/parse/match
Content-Type: multipart/form-data

file=<your_file>
advanced=true
use_levenshtein=true
use_tfidf=true
use_inverted_index=true
use_phonetic=true
```

### Confirm a match

```http
POST /api/v1/confirm_match
Content-Type: application/json

{
  "raw_query": "chiken dressed broylr",
  "product_id": 42
}
```

---

## Flask UI

A lightweight Flask frontend lives in `flask_ui/`. It provides:

- File upload form
- Parsed results table with top-5 candidate match cards per row
- Clickable candidate selection (radio card UI)
- Confirm button to store selection in the feedback cache

To run:

```bash
cd flask_ui
python app.py
```

---

## Installation

```bash
git clone https://github.com/Dwaynee247-06/ShipsKart-Parser-OG.git
cd ShipsKart-Parser-OG
pip install -r requirements.txt
```

---

## Requirements

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9
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
flask>=3.0.0
requests>=2.32.0
pytest>=8.0.0
httpx>=0.27.0
```

> **Note:** `jellyfish` enables phonetic matching (Soundex). If not installed, the phonetic layer is skipped gracefully and the other layers still run.

---

## Database Migrations (Alembic)

```bash
# Create a new migration
alembic revision --autogenerate -m "your message"

# Apply migrations
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

## Test Cases (Excel sheet)

A test workbook (`shipskart_test_cases.xlsx`) is available to validate all layers. It includes:

| Test | Input | Tests |
|------|-------|-------|
| Clean match | `Chicken Dressed Broiler` | Base accuracy |
| Heavy typos | `Chiken Dresed Broylr` | Levenshtein + phonetic + TF-IDF fallback |
| Hindi alias | `baingan` | Alias expansion |
| Spaces + Hindi | `" Hari   Mirch  "` | Normalization + alias |
| Regional meat | `MURG` | Case normalization + alias |
| Unusual header | `Qty Req`, `Catg`, `Purchase Reamrk` | Header alias normalization |
| Hidden header | Header at row 5 with metadata above | Header detection |
| Numeric quantity | `"1,000"` as text | Value-signature inference |

---

## Tech Stack

| Layer | Library |
|-------|---------|
| API | FastAPI |
| ORM | SQLAlchemy + Alembic |
| Fuzzy matching | RapidFuzz |
| Phonetic matching | Jellyfish |
| Vector similarity | scikit-learn (TF-IDF) |
| Excel parsing | openpyxl |
| PDF parsing | pdfplumber |
| Word parsing | python-docx |
| Frontend UI | Flask + Jinja2 |
| Testing | pytest + httpx |

---

## Author

Built by [Dwayne Dsouza](https://github.com/Dwaynee247-06) for ShipsKart parsing and smart product-matching workflows.
