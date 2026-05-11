"""
matcher.py
----------
Fuzzy product-matching service.

Exposes two matching paths:

1. Simple matcher  (match_document_simple)
   - Alias expansion via ALIAS_MAP
   - token_set_ratio  (word-order tolerant)
   - partial_ratio    (substring / alias match)
   Score = max(0.7*token_set_ratio + 0.3*partial_ratio) over original and alias.

2. Advanced matcher  (match_document_advanced)
   - Uses ProductMatcher from app.services.matching
   - Layers 4/4b (Levenshtein + Phonetic), 5 (TF-IDF), 6 (inverted-index)
     can be toggled via flags.
   - ProductMatcher instance is built once per request and reused across rows.
"""
from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.product import Product as DbProduct
# Issue 1 & 15: matching.py now exports MatcherProduct directly;
# no import alias needed here.
from app.services.matching import normalize, ProductMatcher, MatcherProduct


# ---------------------------------------------------------------------------
# Alias dictionary  —  Hindi / Marathi / regional -> English
# ---------------------------------------------------------------------------
ALIAS_MAP: dict[str, str] = {
    # Fruits
    "limbu":          "lemon",
    "nimbu":          "lemon",
    "nimboo":         "lemon",
    "sour lime":      "lemon",
    "malta":          "mandarin orange",
    "santara":        "mandarin orange",
    "kela":           "banana",
    "kele":           "banana",
    "seb":            "apple",
    "angoor":         "grapes",
    "aam":            "mango",
    "papita":         "papaya",
    "ananas":         "pineapple",
    "tarbuj":         "watermelon",
    "tarbooz":        "watermelon",
    "kharbooja":      "sweet melon",
    "anar":           "pomegranate",
    "amrood":         "guava",
    "nashpati":       "pear",
    "chikoo":         "sapodilla",
    # Vegetables
    "aloo":           "potatoes",
    "aaloo":          "potatoes",
    "pyaz":           "onion",
    "pyaaz":          "onion",
    "tamatar":        "tomatoes",
    "tamater":        "tomatoes",
    "baingan":        "egg plant",
    "brinjal":        "egg plant",
    "gobhi":          "cauliflower",
    "phool gobhi":    "cauliflower",
    "patta gobhi":    "cabbage",
    "band gobhi":     "cabbage",
    "gajar":          "carrot",
    "palak":          "spinach",
    "methi":          "fenugreek leaves",
    "dhaniya":        "coriander leaves",
    "dhania":         "coriander leaves",
    "pudina":         "mint leaves",
    "bhindi":         "lady finger",
    "okra":           "lady finger",
    "shimla mirch":   "capsicum",
    "mirch":          "green hot peppers",
    "hari mirch":     "green hot peppers",
    "adrak":          "ginger",
    "lehsun":         "garlic",
    "lahasun":        "garlic",
    "matar":          "green peas",
    "hara matar":     "green peas",
    "hari matar":     "green peas",
    "kaddu":          "pumpkin",
    "lauki":          "bottle gourd",
    "turai":          "ridge gourd",
    "karela":         "bittergourd",
    "sem":            "broad beans",
    "sem fali":       "broad beans",
    "lobia":          "black eyed peas",
    "kathal":         "jackfruit",
    "khira":          "cucumber",
    "kheera":         "cucumber",
    "mooli":          "radish",
    "arbi":           "taro",
    "shakarkand":     "sweet potato",
    "suran":          "yam",
    "zucchini":       "marrow",
    # Meat / Seafood
    "murgi":          "chicken",
    "murg":           "chicken",
    "gosht":          "mutton",
    "bakra":          "mutton",
    "maachli":        "fish",
    "machli":         "fish",
    "machhli":        "fish",
    "jhinga":         "prawns",
    "chingri":        "prawns",
    "anda":           "eggs",
    "ande":           "eggs",
    # Dairy
    "doodh":          "milk",
    "dahi":           "yoghurt",
    "curd":           "yoghurt",
    "paneer":         "cottage cheese",
    "makhan":         "butter",
    "ghee":           "clarified butter",
    # Dry goods / spices
    "chawal":         "rice",
    "atta":           "wheat flour",
    "maida":          "refined flour",
    "besan":          "gram flour",
    "dal":            "lentils",
    "chana dal":      "split chickpeas",
    "moong dal":      "moong lentils",
    "masoor dal":     "red lentils",
    "haldi":          "turmeric",
    "turmeric":       "turmeric powder",
    "jeera":          "cumin",
    "zeera":          "cumin",
    "dhaniya powder": "coriander powder",
    "kali mirch":     "black pepper",
    "dalchini":       "cinnamon",
    "laung":          "cloves",
    "elaichi":        "cardamom",
    "jaiphal":        "nutmeg",
    "saunf":          "fennel seeds",
    "rai":            "mustard seeds",
    "sarson":         "mustard seeds",
    "til":            "sesame seeds",
    "namak":          "salt",
    "cheeni":         "sugar",
    "shakkar":        "sugar",
    "tel":            "oil",
    "sarson ka tel":  "mustard oil",
    "sirka":          "vinegar",
    "imli":           "tamarind",
    "kaju":           "cashews",
    "badam":          "almonds",
    "akhrot":         "walnuts",
    "kishmish":       "raisins",
    "pista":          "pistachios",
}


# ---------------------------------------------------------------------------
# Issue 14: _normalize() removed — use normalize() from matching.py
# ---------------------------------------------------------------------------

def _resolve_alias(text: str) -> str:
    norm = normalize(text)
    if norm in ALIAS_MAP:
        return ALIAS_MAP[norm]
    best_key = ""
    for key in ALIAS_MAP:
        if key in norm and len(key) > len(best_key):
            best_key = key
    if best_key:
        return ALIAS_MAP[best_key]
    return text


def _score(query: str, candidate: str) -> float:
    q_orig  = normalize(query)
    q_alias = normalize(_resolve_alias(query))
    c       = normalize(candidate)

    if not c:
        return 0.0

    def _raw(q: str) -> float:
        if not q:
            return 0.0
        return round(0.7 * fuzz.token_set_ratio(q, c) + 0.3 * fuzz.partial_ratio(q, c), 2)

    return max(_raw(q_orig), _raw(q_alias))


# ---------------------------------------------------------------------------
# Simple matching API
# ---------------------------------------------------------------------------

def match_item_simple(
    db: Session,
    item_name: str,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    all_products: list[DbProduct] = (
        db.query(DbProduct)
        .filter(DbProduct.IsActive == True)  # noqa: E712
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


def match_document_simple(
    db: Session,
    parsed_tables: dict[str, Any],
    top_n: int = 5,
) -> dict[str, Any]:
    output_tables: dict[str, Any] = {}
    total_items = 0
    matched_above_80 = 0
    matched_above_50 = 0
    unmatched = 0

    for table_key, table_data in parsed_tables.items():
        enriched_rows = []
        for row in table_data.get("rows", []):
            item_name = row.get("items") or row.get("description") or ""
            matches = match_item_simple(db, item_name, top_n=top_n)
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
            "total_amount":  table_data.get("total_amount"),
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


# ---------------------------------------------------------------------------
# Advanced matching helpers
# ---------------------------------------------------------------------------

# Issue 11: ProductMatcher is built ONCE and returned so the caller can
# reuse it across all rows in the document — avoids rebuilding TF-IDF
# and inverted index per row.
def _build_product_matcher(
    db: Session,
    use_levenshtein: bool,
    use_tfidf: bool,
    use_inverted_index: bool,
    use_phonetic: bool,
) -> ProductMatcher:
    db_products: list[DbProduct] = (
        db.query(DbProduct)
        .filter(DbProduct.IsActive == True)  # noqa: E712
        .all()
    )
    pm_products = [
        MatcherProduct(id=p.ProductID, name=p.ProductName)
        for p in db_products
    ]
    return ProductMatcher(
        products=pm_products,
        alias_map=ALIAS_MAP,
        use_levenshtein=use_levenshtein,
        use_tfidf=use_tfidf,
        use_inverted_index=use_inverted_index,
        use_phonetic=use_phonetic,
    )


def match_item_advanced(
    matcher: ProductMatcher,
    db: Session,
    item_name: str,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    result = matcher.match(item_name, top_n=top_n)
    candidates = result.get("candidates", [])
    match_status = result.get("status", "candidate")

    if not candidates:
        return []

    # Issue 10: batch-fetch all candidate products in ONE query instead
    # of one query per candidate inside the loop.
    candidate_ids = [entry["product"].id for entry in candidates]
    db_products_map: dict[int, DbProduct] = {
        p.ProductID: p
        for p in db.query(DbProduct)
        .filter(DbProduct.ProductID.in_(candidate_ids))
        .all()
    }

    formatted: list[dict[str, Any]] = []
    for rank, entry in enumerate(candidates, start=1):
        prod = entry["product"]
        score = entry["score"]
        db_product = db_products_map.get(prod.id)
        if db_product is None:
            continue
        formatted.append(
            {
                "rank":         rank,
                "score_pct":    score,
                "match_status": match_status if rank == 1 else "candidate",
                "product_id":   db_product.ProductID,
                "product_name": db_product.ProductName,
                "category":     db_product.category.CategoryName if db_product.category else None,
                "brand":        db_product.brand.BrandName if db_product.brand else None,
                "unit":         db_product.UnitOfMeasure,
            }
        )

    return formatted


def match_document_advanced(
    db: Session,
    parsed_tables: dict[str, Any],
    top_n: int = 5,
    use_levenshtein: bool = True,
    use_tfidf: bool = True,
    use_inverted_index: bool = True,
    use_phonetic: bool = True,
) -> dict[str, Any]:
    # Issue 11: build matcher ONCE for the entire document
    matcher = _build_product_matcher(
        db=db,
        use_levenshtein=use_levenshtein,
        use_tfidf=use_tfidf,
        use_inverted_index=use_inverted_index,
        use_phonetic=use_phonetic,
    )

    output_tables: dict[str, Any] = {}
    total_items = 0
    matched_confident = 0
    matched_candidate = 0
    unmatched = 0

    for table_key, table_data in parsed_tables.items():
        enriched_rows = []
        for row in table_data.get("rows", []):
            item_name = row.get("items") or row.get("description") or ""
            matches = match_item_advanced(matcher, db, item_name, top_n=top_n)
            enriched_rows.append({**row, "matches": matches})

            total_items += 1
            # Issue 12: use only match_status from the result — no double-counting
            status = matches[0].get("match_status", "no_match") if matches else "no_match"
            if status == "confident":
                matched_confident += 1
            elif status == "candidate":
                matched_candidate += 1
            else:
                unmatched += 1

        output_tables[table_key] = {
            "document_info": table_data.get("document_info", {}),
            "headers":       table_data.get("headers", []),
            "rows":          enriched_rows,
            "total_amount":  table_data.get("total_amount"),
        }

    return {
        "tables": output_tables,
        "summary": {
            "total_items":       total_items,
            "matched_confident": matched_confident,
            "matched_candidate": matched_candidate,
            "unmatched":         unmatched,
        },
    }


# ---------------------------------------------------------------------------
# Unified entrypoint used by the API
# ---------------------------------------------------------------------------

def match_document(
    db: Session,
    parsed_tables: dict[str, Any],
    top_n: int = 5,
    advanced: bool = False,
    use_levenshtein: bool = True,
    use_tfidf: bool = True,
    use_inverted_index: bool = True,
    use_phonetic: bool = True,
) -> dict[str, Any]:
    """Route to simple or advanced matcher based on the `advanced` flag."""
    if not advanced:
        return match_document_simple(db, parsed_tables, top_n=top_n)

    return match_document_advanced(
        db=db,
        parsed_tables=parsed_tables,
        top_n=top_n,
        use_levenshtein=use_levenshtein,
        use_tfidf=use_tfidf,
        use_inverted_index=use_inverted_index,
        use_phonetic=use_phonetic,
    )
