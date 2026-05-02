"""
matcher.py
----------
Fuzzy product-matching service.

Given a list of item names parsed from an uploaded document, this module
queries the Product master table and returns the top-N matches for each
item using a composite scoring strategy:

  1. Exact match on SkrtCode              → 100%
  2. token_set_ratio  (word-order tolerant) via rapidfuzz
  3. partial_ratio    (substring match)     via rapidfuzz
  4. Combined score   = 0.7 * token_set + 0.3 * partial

requirements: rapidfuzz
"""
from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.product import Product


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(text: str | None) -> str:
    """Lower-case, strip, collapse whitespace."""
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _score(query: str, candidate: str) -> float:
    """
    Composite fuzzy score between two strings (0-100).
    Weights: 70% token_set_ratio + 30% partial_ratio.
    """
    q = _normalize(query)
    c = _normalize(candidate)
    if not q or not c:
        return 0.0
    token_set = fuzz.token_set_ratio(q, c)
    partial   = fuzz.partial_ratio(q, c)
    return round(0.7 * token_set + 0.3 * partial, 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_item(
    db: Session,
    item_name: str,
    skrt_code: str | None = None,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """
    Return up to `top_n` best-matching products from the DB for `item_name`.

    If `skrt_code` is provided and an exact match exists it is always ranked #1
    with a 100% score regardless of fuzzy scores.

    Each result dict contains:
      {
          "rank":          int,
          "score_pct":     float,   # 0.0 – 100.0
          "skrt_code":     str,
          "product_name":  str,
          "category":      str,
          "brand":         str,
          "unit":          str,
          "gst_pct":       float,
          "remarks":       str | None,
      }
    """
    all_products: list[Product] = (
        db.query(Product)
        .filter(Product.IsActive == True)  # noqa: E712
        .all()
    )

    scored: list[tuple[float, Product]] = []
    exact_match: Product | None = None

    if skrt_code:
        norm_code = _normalize(skrt_code)
        for p in all_products:
            if _normalize(p.SkrtCode) == norm_code:
                exact_match = p
                break

    for p in all_products:
        if exact_match and p.ProductID == exact_match.ProductID:
            continue
        s = _score(item_name, p.ProductName)
        # Also score against Remarks for alias coverage
        if p.Remarks:
            s = max(s, _score(item_name, p.Remarks))
        scored.append((s, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    results: list[dict[str, Any]] = []
    start_rank = 1

    if exact_match:
        results.append({
            "rank":         1,
            "score_pct":    100.0,
            "skrt_code":    exact_match.SkrtCode,
            "product_name": exact_match.ProductName,
            "category":     exact_match.category.CategoryName if exact_match.category else None,
            "brand":        exact_match.brand.BrandName if exact_match.brand else None,
            "unit":         exact_match.UnitOfMeasure,
            "gst_pct":      float(exact_match.GSTPercent),
            "remarks":      exact_match.Remarks,
        })
        start_rank = 2
        top = top[:top_n - 1]

    for rank_offset, (score, p) in enumerate(top):
        results.append({
            "rank":         start_rank + rank_offset,
            "score_pct":    score,
            "skrt_code":    p.SkrtCode,
            "product_name": p.ProductName,
            "category":     p.category.CategoryName if p.category else None,
            "brand":        p.brand.BrandName if p.brand else None,
            "unit":         p.UnitOfMeasure,
            "gst_pct":      float(p.GSTPercent),
            "remarks":      p.Remarks,
        })

    return results


def match_document(
    db: Session,
    parsed_tables: dict[str, Any],
    top_n: int = 5,
) -> dict[str, Any]:
    """
    Iterate over every row in every parsed table and enrich each row with
    top-N product matches.

    Input  : parsed_tables — the dict returned by dispatch_parser
             e.g. { "table_1": { "headers": [...], "rows": [{...}, ...] } }

    Output : {
        "tables": {
            "table_1": {
                "headers": [...],
                "rows": [
                    {
                        ...original row fields...,
                        "matches": [ { rank, score_pct, skrt_code, ... }, ... ]
                    },
                    ...
                ]
            }
        },
        "summary": {
            "total_items":   int,
            "matched_above_80": int,   # items where best match score >= 80
            "matched_above_50": int,
            "unmatched":     int,      # best match score < 50
        }
    }
    """
    output_tables: dict[str, Any] = {}
    total_items = 0
    matched_above_80 = 0
    matched_above_50 = 0
    unmatched = 0

    for table_key, table_data in parsed_tables.items():
        enriched_rows = []
        for row in table_data.get("rows", []):
            item_name = row.get("items") or row.get("description") or ""
            skrt_code = row.get("skrt_code") or row.get("skrt code") or None

            matches = match_item(db, item_name, skrt_code=skrt_code, top_n=top_n)
            enriched_row = {**row, "matches": matches}
            enriched_rows.append(enriched_row)

            total_items += 1
            best_score = matches[0]["score_pct"] if matches else 0
            if best_score >= 80:
                matched_above_80 += 1
            elif best_score >= 50:
                matched_above_50 += 1
            else:
                unmatched += 1

        output_tables[table_key] = {
            "document_info": table_data.get("document_info", {}),
            "headers": table_data.get("headers", []),
            "rows": enriched_rows,
        }

    return {
        "tables": output_tables,
        "summary": {
            "total_items":      total_items,
            "matched_above_80": matched_above_80,
            "matched_above_50": matched_above_50,
            "unmatched":        unmatched,
        },
    }
