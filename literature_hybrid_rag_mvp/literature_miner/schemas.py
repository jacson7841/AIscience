"""Dataclasses and JSON shapes used across the literature pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PaperRecord:
    paper_id: str
    title: str
    normalized_title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    openalex_id: str = ""
    s2_id: str = ""
    abstract: str = ""
    url: str = ""
    pdf_url: str = ""
    citation_count: int = 0
    sources: List[str] = field(default_factory=list)
    verification_status: str = "unverified"
    pdf_available: bool = False
    evidence_level: str = "metadata_only"
    topics: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    utility_score: float = 0.0
    local_pdf_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperRecord":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class EvidenceChunk:
    chunk_id: str
    paper_id: str
    chunk_index: int
    title: str
    year: Optional[int]
    doi: str
    page_number: Optional[int]
    section: str
    text: str
    source_url: str
    verification_status: str
    evidence_level: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceChunk":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class SourceStats:
    queries: List[str] = field(default_factory=list)
    returned: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchManifest:
    seed_topics: List[str] = field(default_factory=list)
    expanded_queries: List[str] = field(default_factory=list)
    sources: Dict[str, SourceStats] = field(default_factory=dict)
    before_dedup: int = 0
    after_dedup: int = 0
    verified: int = 0
    pdf_available: int = 0
    abstract_only: int = 0
    selected: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["sources"] = {
            name: stats.to_dict() if hasattr(stats, "to_dict") else stats
            for name, stats in self.sources.items()
        }
        return data
