"""
matcher.py
----------
Fuzzy product-matching service.

Matches a parsed item name against the Product master table using:
  1. token_set_ratio  (word-order tolerant) via rapidfuzz
  2. partial_ratio    (substring / alias match) via rapidfuzz
  Combined score = 0.7 * token_set_ratio + 0.3 * partial_ratio

requirements: rapidfuzz
"""
from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.product import Product


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _score(query: str, candidate: str) -> float:
    q = _normalize(query)
    c = _normalize(candidate)
    if not q or not c:
        return 0.0
    token_set = fuzz.token_set_ratio(q, c)
    partial   = fuzz.partial_ratio(q, c)
    return round(0.7 * token_set + 0.3 * partial, 2)


def match_item(
    db: Session,
    item_name: str,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """
    Return up to `top_n` best-matching products from the DB for `item_name`.

    Each result dict::

        {
            "rank":         int,
            "score_pct":    float,   # 0.0 - 100.0
            "product_id":   int,
            "product_name": str,
            "category":     str,
            "brand":        str,
            "unit":         str,
        }
    """
    all_products: list[Product] = (
        db.query(Product)
        .filter(Product.IsActive == True)  # noqa: E712
        .all()
    )

    scored = [
        (_score(item_name, p.ProductName), p)
        for p in all_products
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "rank":         rank + 1,
            "score_pct":    score,
            "product_id":   p.ProductID,
            "product_name": p.ProductName,
            "category":     p.category.CategoryName if p.category else None,
            "brand":        p.brand.BrandName if p.brand else None,
            "unit":         p.UnitOfMeasure,
        }
        for rank, (score, p) in enumerate(scored[:top_n])
    ]


def match_document(
    db: Session,
    parsed_tables: dict[str, Any],
    top_n: int = 5,
) -> dict[str, Any]:
    """
    Enrich every parsed row with top-N product matches.
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
            matches = match_item(db, item_name, top_n=top_n)
            enriched_rows.append({**row, "matches": matches})

            total_items += 1
            best = matches[0]["score_pct"] if matches else 0
            if best >= 80:
                matched_above_80 += 1
            elif best >= 50:
                matched_above_50 += 1
            else:
                unmatched += 1

        output_tables[table_key] = {
            "document_info": table_data.get("document_info", {}),
            "headers":       table_data.get("headers", []),
            "rows":          enriched_rows,
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
