"""Hybrid RAG retrieval over persisted evidence chunks."""

from __future__ import annotations

from typing import Dict, Iterable, List

from .bm25 import BM25Document, BM25Index
from .config import Settings
from .schemas import EvidenceChunk
from .storage import KnowledgeBase
from .utils import read_json


class HybridRAG:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chunks = [
            EvidenceChunk.from_dict(data)
            for data in read_json(settings.outputs_dir / "chunks.json", default=[])
        ]
        self.chunk_map = {chunk.chunk_id: chunk.to_dict() for chunk in self.chunks}
        self.bm25 = BM25Index(
            BM25Document(chunk.chunk_id, " ".join([chunk.title, chunk.title, chunk.section, chunk.text]))
            for chunk in self.chunks
        )
        self.kb = KnowledgeBase(settings, reset=False)

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        expanded_query = expand_query_for_retrieval(query)
        dense_results = self.kb.query_dense(expanded_query, top_k=top_k * 2)
        bm25_results = self.bm25.search(expanded_query, top_k=top_k * 2)
        merged: Dict[str, Dict] = {}

        for item in dense_results:
            chunk_id = item.get("chunk_id")
            if not chunk_id:
                continue
            base = self.chunk_map.get(chunk_id, {}).copy()
            base.update(item)
            base["hybrid_score"] = max(base.get("hybrid_score", 0.0), 0.6 * float(item.get("dense_score", 0.0)))
            merged[chunk_id] = base

        max_bm25 = max([score for _, score in bm25_results], default=1.0)
        for chunk_id, score in bm25_results:
            base = merged.get(chunk_id, self.chunk_map.get(chunk_id, {}).copy())
            if not base:
                continue
            sparse_score = score / max_bm25 if max_bm25 else 0.0
            base["sparse_score"] = sparse_score
            base["hybrid_score"] = float(base.get("hybrid_score", 0.0)) + 0.4 * sparse_score
            merged[chunk_id] = base

        for item in merged.values():
            item["hybrid_score"] = float(item.get("hybrid_score", 0.0)) + metadata_bonus(query, item)
        ranked = sorted(merged.values(), key=lambda item: item.get("hybrid_score", 0.0), reverse=True)
        return ranked[:top_k]


def expand_query_for_retrieval(query: str) -> str:
    additions = []
    mapping = {
        "不足": "limitation gap challenge underexplored difficult future work",
        "缺陷": "limitation gap challenge",
        "问题": "problem challenge issue",
        "已有研究": "existing research prior work literature",
        "结论": "conclusion finding result",
        "系统": "system framework agent workflow",
        "验证": "evaluation validation experiment benchmark simulation real-world",
        "硬件": "hardware physical real-world closed-loop",
        "仿真": "simulation benchmark",
    }
    for key, value in mapping.items():
        if key in query:
            additions.append(value)
    return " ".join([query] + additions)


def metadata_bonus(query: str, item: Dict) -> float:
    query_lower = (query or "").lower()
    title = str(item.get("title", "")).lower()
    text = str(item.get("text", "")).lower()
    combined = " ".join([title, text])
    bonus = 0.0

    if "ai scientist" in query_lower:
        if "ai scientist" in title:
            bonus += 0.35
        elif any(term in title for term in ["co-scientist", "scientific discovery", "robot scientist"]):
            bonus += 0.18
        elif not any(
            term in combined
            for term in ["scientist", "scientific discovery", "hypothesis", "experiment", "agentic", "autonomous discovery"]
        ):
            bonus -= 0.20

    if any(term in query for term in ["不足", "缺陷", "问题"]) or any(term in query_lower for term in ["gap", "limitation"]):
        if any(
            marker in combined
            for marker in [
                "limitation",
                "challenge",
                "underexplored",
                "future work",
                "simulation",
                "benchmark",
                "validation",
                "experiment",
                "human",
                "reliance",
            ]
        ):
            bonus += 0.12
    return bonus
