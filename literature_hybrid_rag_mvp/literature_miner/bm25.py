"""Tiny dependency-free BM25 implementation for sparse retrieval."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .utils import tokenize


@dataclass
class BM25Document:
    doc_id: str
    text: str


class BM25Index:
    def __init__(self, documents: Iterable[BM25Document], k1: float = 1.5, b: float = 0.75):
        self.documents = list(documents)
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(doc.text) for doc in self.documents]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_lengths) / max(1, len(self.doc_lengths))
        self.term_freqs = [Counter(tokens) for tokens in self.doc_tokens]
        self.doc_freq: Dict[str, int] = Counter()
        for freqs in self.term_freqs:
            for term in freqs:
                self.doc_freq[term] += 1

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        query_terms = tokenize(query)
        if not query_terms or not self.documents:
            return []
        scores: List[Tuple[str, float]] = []
        for idx, doc in enumerate(self.documents):
            score = 0.0
            dl = self.doc_lengths[idx] or 1
            freqs = self.term_freqs[idx]
            for term in query_terms:
                if term not in freqs:
                    continue
                df = self.doc_freq.get(term, 0)
                idf = math.log(1 + (len(self.documents) - df + 0.5) / (df + 0.5))
                tf = freqs[term]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / max(1e-9, self.avgdl))
                score += idf * (tf * (self.k1 + 1) / denom)
            if score > 0:
                scores.append((doc.doc_id, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:top_k]
