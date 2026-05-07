"""
matcher.py
----------
Fuzzy product-matching service.

Matches a parsed item name against the Product master table using:
  1. Alias expansion  — Hindi / regional names are mapped to English equivalents
  2. token_set_ratio  (word-order tolerant) via rapidfuzz
  3. partial_ratio    (substring / alias match) via rapidfuzz
  Combined score = 0.7 * token_set_ratio + 0.3 * partial_ratio
  Final score    = max(score_on_original, score_on_alias)

requirements: rapidfuzz
"""
from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.product import Product


# ---------------------------------------------------------------------------
# Alias dictionary  —  Hindi / Marathi / regional → English
# Keys are the regional/alternate names (lower-case).
# Values are the English product names as they appear in the Product master.
# Add more entries here as new aliases are discovered.
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


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _resolve_alias(text: str) -> str:
    """
    If the normalized text (or any token within it) matches an alias,
    return the English equivalent. Otherwise return the original text.

    Checks:
      1. Exact full-string match in ALIAS_MAP
      2. Any single alias key found as a substring in the query
    """
    norm = _normalize(text)
    # 1. Exact match
    if norm in ALIAS_MAP:
        return ALIAS_MAP[norm]
    # 2. Substring match — longest key wins (avoids "dal" beating "moong dal")
    best_key = ""
    for key in ALIAS_MAP:
        if key in norm and len(key) > len(best_key):
            best_key = key
    if best_key:
        return ALIAS_MAP[best_key]
    return text


def _score(query: str, candidate: str) -> float:
    """
    Composite fuzzy score (0-100).
    Runs on both the original query AND its alias-resolved form,
    returns the higher of the two scores.
    """
    q_orig  = _normalize(query)
    q_alias = _normalize(_resolve_alias(query))
    c       = _normalize(candidate)

    if not c:
        return 0.0

    def _raw(q: str) -> float:
        if not q:
            return 0.0
        return round(0.7 * fuzz.token_set_ratio(q, c) + 0.3 * fuzz.partial_ratio(q, c), 2)

    return max(_raw(q_orig), _raw(q_alias))


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
    total_amount (if detected by the parser) is passed through unchanged.
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
            # Pass the grand total from the sheet through to the response.
            # None if the parser did not find a total row.
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
