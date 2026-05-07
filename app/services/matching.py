from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    import jellyfish
    _JELLYFISH = True
except ImportError:
    _JELLYFISH = False


@dataclass
class Product:
    id: int
    name: str


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    bad_chars = ",.;:/\\|()[]{}!@#$%^&*_+=<>\"'"
    for ch in bad_chars:
        text = text.replace(ch, " ")
    return " ".join(text.split())


def resolve_alias(text: str, alias_map: Dict[str, str]) -> str:
    if not text:
        return ""
    tokens = normalize(text).split()
    resolved = [alias_map.get(tok, tok) for tok in tokens]
    return " ".join(resolved)


def _phonetic_similarity(query: str, candidate: str) -> float:
    """Return 0-100 phonetic similarity using Soundex on each token pair.
    Falls back to 0 if jellyfish is not installed."""
    if not _JELLYFISH:
        return 0.0
    q_tokens = query.split()
    c_tokens = candidate.split()
    if not q_tokens or not c_tokens:
        return 0.0
    matches = 0
    for qt in q_tokens:
        qs = jellyfish.soundex(qt)
        for ct in c_tokens:
            if qs == jellyfish.soundex(ct):
                matches += 1
                break
    return round((matches / len(q_tokens)) * 100, 2)


class ProductMatcher:
    def __init__(
        self,
        products: List[Product],
        alias_map: Optional[Dict[str, str]] = None,
        use_levenshtein: bool = True,
        use_tfidf: bool = True,
        use_inverted_index: bool = True,
        use_phonetic: bool = True,
        ngram_range: Tuple[int, int] = (2, 3),
    ):
        self.products = products
        self.alias_map = alias_map or {}

        self.use_levenshtein = use_levenshtein
        self.use_tfidf = use_tfidf
        self.use_inverted_index = use_inverted_index
        self.use_phonetic = use_phonetic and _JELLYFISH

        self.norm_names: List[str] = []
        for p in products:
            base = normalize(p.name)
            alias = resolve_alias(p.name, self.alias_map)
            combined = f"{base} {alias}".strip()
            self.norm_names.append(combined)

        self.inverted_index: Optional[Dict[str, set]] = None
        if self.use_inverted_index:
            self.inverted_index = self._build_inverted_index()

        self.vectorizer = None
        self.tfidf_matrix = None
        if self.use_tfidf:
            self.vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=ngram_range,
            )
            self.tfidf_matrix = self.vectorizer.fit_transform(self.norm_names)

        # Layer 7: feedback cache  query_norm -> product_id
        self.confirmed_cache: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_inverted_index(self) -> Dict[str, set]:
        index: Dict[str, set] = defaultdict(set)
        for i, name in enumerate(self.norm_names):
            for word in name.split():
                index[word].add(i)
        return index

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(
        self,
        raw_query: str,
        top_n: int = 5,
        confident_threshold: float = 72.0,
        reject_threshold: float = 45.0,
    ):
        """
        Returns dict:
          status   : 'confident' | 'candidate' | 'no_match' | 'cached'
          best     : {product, score} or None
          candidates: [{product, score}, ...]
        """
        q_norm = normalize(raw_query)

        # Layer 7: feedback cache check
        if q_norm in self.confirmed_cache:
            pid = self.confirmed_cache[q_norm]
            prod = next((p for p in self.products if p.id == pid), None)
            if prod:
                return {
                    "status": "cached",
                    "best": {"product": prod, "score": 100.0},
                    "candidates": [{"product": prod, "score": 100.0}],
                }

        # Layer 1: normalise + expand aliases
        query_base = normalize(raw_query)
        query_alias = resolve_alias(raw_query, self.alias_map)
        query_combined = f"{query_base} {query_alias}".strip()

        if not query_combined:
            return {"status": "no_match", "best": None, "candidates": []}

        # Layer 2: exact match
        for i, name in enumerate(self.norm_names):
            if query_combined == name:
                prod = self.products[i]
                self.confirmed_cache[q_norm] = prod.id
                return {
                    "status": "confident",
                    "best": {"product": prod, "score": 100.0},
                    "candidates": [{"product": prod, "score": 100.0}],
                }

        # Layer 6: inverted-index pre-filter
        # KEY FIX: if the index finds nothing (heavy typos share zero words)
        # fall back to scoring ALL products so Levenshtein + phonetic still fire
        if self.use_inverted_index and self.inverted_index is not None:
            candidate_indices = self._get_candidate_indices(query_combined)
            if not candidate_indices:
                # typo fallback — score everything
                candidate_indices = list(range(len(self.products)))
        else:
            candidate_indices = list(range(len(self.products)))

        scored = []
        for idx in candidate_indices:
            prod = self.products[idx]
            prod_name = self.norm_names[idx]
            score = self._combined_score(query_combined, prod_name, idx)
            scored.append((prod, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_n]

        if not top:
            return {"status": "no_match", "best": None, "candidates": []}

        best_prod, best_score = top[0]

        if best_score >= confident_threshold:
            status = "confident"
            self.confirmed_cache[q_norm] = best_prod.id
        elif best_score < reject_threshold:
            status = "no_match"
        else:
            status = "candidate"

        return {
            "status": status,
            "best": {"product": best_prod, "score": best_score} if status != "no_match" else None,
            "candidates": [{"product": p, "score": s} for p, s in top],
        }

    def confirm_match(self, raw_query: str, product_id: int) -> None:
        """Store a user-confirmed mapping in the feedback cache."""
        self.confirmed_cache[normalize(raw_query)] = product_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_candidate_indices(self, query: str) -> List[int]:
        words = query.split()
        candidates: set = set()
        for w in words:
            candidates |= self.inverted_index.get(w, set())  # type: ignore[union-attr]
        return list(candidates)

    def _combined_score(self, query: str, candidate: str, idx: int) -> float:
        is_short = len(query.split()) <= 2

        # Layer 3: token-based fuzzy
        token_score = (
            0.7 * fuzz.token_set_ratio(query, candidate)
            + 0.3 * fuzz.partial_ratio(query, candidate)
        )

        # Layer 4: Levenshtein (character edit distance)
        lev_score = 0.0
        if self.use_levenshtein:
            lev_score = Levenshtein.normalized_similarity(query, candidate) * 100

        # Layer 4b: Phonetic (Soundex)
        phonetic_score = 0.0
        if self.use_phonetic:
            phonetic_score = _phonetic_similarity(query, candidate)

        # Adaptive blending — short queries lean on character/phonetic signals
        if is_short:
            # short / heavily typo'd: Levenshtein + phonetic carry more weight
            fuzzy_score = (
                0.35 * token_score
                + 0.35 * lev_score
                + 0.30 * phonetic_score
            )
        else:
            fuzzy_score = (
                0.50 * token_score
                + 0.30 * lev_score
                + 0.20 * phonetic_score
            )

        # Layer 5: TF-IDF cosine similarity
        if self.use_tfidf and self.vectorizer is not None and self.tfidf_matrix is not None:
            query_vec = self.vectorizer.transform([query])
            prod_vec = self.tfidf_matrix[idx]
            tfidf_score = cosine_similarity(query_vec, prod_vec)[0, 0] * 100
            # TF-IDF gets 40 %, fuzzy blend gets 60 %
            final_score = 0.40 * tfidf_score + 0.60 * fuzzy_score
        else:
            final_score = fuzzy_score

        return round(final_score, 2)
