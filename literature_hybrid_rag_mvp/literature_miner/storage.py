"""Persistent chunk storage and dense retrieval."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import Settings
from .schemas import EvidenceChunk
from .utils import tokenize


class HashingEmbedder:
    """Small deterministic fallback embedder used when MiniLM is unavailable."""

    def __init__(self, dims: int = 384):
        self.dims = dims

    def encode(self, texts, normalize_embeddings: bool = True):
        single = isinstance(texts, str)
        values = [texts] if single else list(texts)
        vectors = [self._encode_one(text, normalize_embeddings=normalize_embeddings) for text in values]
        return vectors[0] if single else vectors

    def _encode_one(self, text: str, normalize_embeddings: bool = True) -> List[float]:
        vector = [0.0] * self.dims
        for token in tokenize(text):
            bucket = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16) % self.dims
            vector[bucket] += 1.0
        if normalize_embeddings:
            norm = math.sqrt(sum(value * value for value in vector))
            if norm:
                vector = [value / norm for value in vector]
        return vector


class KnowledgeBase:
    def __init__(self, settings: Settings, reset: bool = False):
        self.settings = settings
        self.reset = reset
        self.client = None
        self.collection = None
        self.embedder = None
        self.warnings: List[str] = []
        self._init_dense()

    def _init_dense(self) -> None:
        if not self.settings.enable_dense:
            self.warnings.append("Dense retrieval disabled by configuration.")
            return
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=str(self.settings.knowledge_base_dir))
            if self.reset:
                try:
                    self.client.delete_collection(self.settings.collection_name)
                except Exception:
                    pass
            self.collection = self.client.get_or_create_collection(name=self.settings.collection_name)
            self.embedder = self._load_embedder()
        except Exception as exc:  # noqa: BLE001 - fallback to BM25/JSON
            self.warnings.append(f"Chroma unavailable; dense retrieval disabled: {exc}")
            self.client = None
            self.collection = None
            self.embedder = None

    def _load_embedder(self):
        if self.settings.embedding_backend == "hashing":
            self.warnings.append("Using hashing embeddings because EMBEDDING_BACKEND=hashing.")
            return HashingEmbedder()
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(self.settings.embedding_model)
        except Exception as exc:  # noqa: BLE001 - robust offline fallback
            self.warnings.append(f"MiniLM embedding unavailable; using hashing embeddings: {exc}")
            return HashingEmbedder()

    def index(self, chunks: Iterable[EvidenceChunk]) -> None:
        chunk_list = list(chunks)
        if not self.collection or not self.embedder or not chunk_list:
            return
        ids = [chunk.chunk_id for chunk in chunk_list]
        documents = [chunk.text for chunk in chunk_list]
        metadatas = [
            {
                "paper_id": chunk.paper_id,
                "chunk_index": chunk.chunk_index,
                "title": chunk.title,
                "year": chunk.year or "",
                "doi": chunk.doi,
                "page_number": chunk.page_number if chunk.page_number is not None else "",
                "section": chunk.section,
                "source_url": chunk.source_url,
                "verification_status": chunk.verification_status,
                "evidence_level": chunk.evidence_level,
            }
            for chunk in chunk_list
        ]
        embeddings = self.embedder.encode(documents, normalize_embeddings=True)
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    def query_dense(self, query: str, top_k: int = 10) -> List[Dict]:
        if not self.collection or not self.embedder:
            return []
        embedding = self.embedder.encode(query, normalize_embeddings=True)
        result = self.collection.query(query_embeddings=[embedding], n_results=top_k)
        output: List[Dict] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for idx, chunk_id in enumerate(ids):
            distance = distances[idx] if idx < len(distances) else 1.0
            metadata = dict(metadatas[idx] or {})
            metadata["chunk_id"] = chunk_id
            metadata["text"] = documents[idx] if idx < len(documents) else ""
            metadata["dense_score"] = 1.0 / (1.0 + float(distance))
            output.append(metadata)
        return output
