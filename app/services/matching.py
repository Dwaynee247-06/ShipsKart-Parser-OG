from dataclasses import dataclass
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


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


class ProductMatcher:
    def __init__(
        self,
        products: List[Product],
        alias_map: Optional[Dict[str, str]] = None,
        use_levenshtein: bool = True,
        use_tfidf: bool = True,
        use_inverted_index: bool = True,
        ngram_range: Tuple[int, int] = (2, 3),
    ):
        self.products = products
        self.alias_map = alias_map or {}

        self.use_levenshtein = use_levenshtein
        self.use_tfidf = use_tfidf
        self.use_inverted_index = use_inverted_index

        self.norm_names = []
        for p in products:
            base = normalize(p.name)
            alias = resolve_alias(p.name, self.alias_map)
            combined = f"{base} {alias}".strip()
            self.norm_names.append(combined)

        self.inverted_index = None
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

    def _build_inverted_index(self) -> Dict[str, set]:
        index = defaultdict(set)
        for i, name in enumerate(self.norm_names):
            for word in name.split():
                index[word].add(i)
        return index

    def match(
        self,
        raw_query: str,
        top_n: int = 5,
        confident_threshold: float = 80.0,
        reject_threshold: float = 50.0,
    ):
        query_base = normalize(raw_query)
        query_alias = resolve_alias(raw_query, self.alias_map)
        query_combined = f"{query_base} {query_alias}".strip()

        if not query_combined:
            return {"status": "no_match", "best": None, "candidates": []}

        for i, name in enumerate(self.norm_names):
            if query_combined == name:
                prod = self.products[i]
                return {
                    "status": "confident",
                    "best": {"product": prod, "score": 100.0},
                    "candidates": [{"product": prod, "score": 100.0}],
                }

        if self.use_inverted_index and self.inverted_index is not None:
            candidate_indices = self._get_candidate_indices(query_combined)
            if not candidate_indices:
                return {"status": "no_match", "best": None, "candidates": []}
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
        elif best_score < reject_threshold:
            status = "no_match"
        else:
            status = "candidate"

        return {
            "status": status,
            "best": {"product": best_prod, "score": best_score} if status != "no_match" else None,
            "candidates": [
                {"product": p, "score": s} for p, s in top
            ],
        }

    def _get_candidate_indices(self, query: str) -> List[int]:
        words = query.split()
        candidates = set()
        for w in words:
            candidates |= self.inverted_index.get(w, set())
        return list(candidates)

    def _combined_score(self, query: str, candidate: str, idx: int) -> float:
        token_score = (
            0.7 * fuzz.token_set_ratio(query, candidate)
            + 0.3 * fuzz.partial_ratio(query, candidate)
        )

        if self.use_levenshtein:
            lev_score = Levenshtein.normalized_similarity(query, candidate) * 100
            is_short = len(query.split()) <= 2
            lev_weight = 0.4 if is_short else 0.15
            fuzzy_score = (1 - lev_weight) * token_score + lev_weight * lev_score
        else:
            fuzzy_score = token_score

        if self.use_tfidf and self.vectorizer is not None and self.tfidf_matrix is not None:
            query_vec = self.vectorizer.transform([query])
            prod_vec = self.tfidf_matrix[idx]
            tfidf_score = cosine_similarity(query_vec, prod_vec)[0, 0] * 100
            final_score = 0.5 * tfidf_score + 0.5 * fuzzy_score
        else:
            final_score = fuzzy_score

        return round(final_score, 2)
