"""End-to-end orchestration for bootstrap, review, and ask commands."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence

from .chunking import chunks_from_abstract, chunks_from_pages
from .config import Settings, get_settings
from .llm_adapter import LLMAdapter
from .pdf_parser import acquire_pdf, parse_pdf_pages
from .rag import HybridRAG
from .render_txt import render_answer_txt, render_review_txt, write_text
from .review import LiteratureReviewGenerator
from .schemas import EvidenceChunk, PaperRecord
from .search import ACADEMIC_SOURCES, LiteratureSearcher
from .storage import KnowledgeBase
from .utils import read_json, write_json


def load_seed_topics(path: Path) -> List[str]:
    data = read_json(path, default=[])
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    if isinstance(data, dict):
        topics = data.get("seed_topics") or data.get("topics") or []
        return [str(item).strip() for item in topics if str(item).strip()]
    raise ValueError("seed file must be a JSON list or an object with seed_topics.")


def bootstrap(
    seed_path: Path,
    limit: int = 30,
    settings: Settings | None = None,
    local_pdf_dir: Path | None = None,
    demo: bool = False,
    skip_pdf_download: bool = False,
    max_queries: int | None = None,
    sources: Sequence[str] | None = None,
) -> Dict:
    settings = settings or get_settings()
    settings.ensure_dirs()
    seed_topics = load_seed_topics(seed_path)
    searcher = LiteratureSearcher(settings)
    result = searcher.search(
        seed_topics,
        limit=limit,
        sources=sources or ACADEMIC_SOURCES,
        local_pdf_dir=local_pdf_dir,
        demo=demo,
        max_queries=max_queries,
    )
    papers = result.papers
    chunks: List[EvidenceChunk] = []

    for paper in papers:
        paper_chunks: List[EvidenceChunk] = []
        pdf_path = None if skip_pdf_download else acquire_pdf(paper, settings)
        if pdf_path:
            pages = parse_pdf_pages(pdf_path)
            if pages:
                paper.pdf_available = True
                paper.evidence_level = "full_text"
                paper_chunks = chunks_from_pages(paper, pages, settings.chunk_max_chars, settings.chunk_overlap_chars)
        if not paper_chunks:
            paper.pdf_available = False
            paper.evidence_level = "abstract_only" if paper.abstract else "metadata_only"
            paper_chunks = chunks_from_abstract(paper, settings.chunk_max_chars, settings.chunk_overlap_chars)
        chunks.extend(paper_chunks)

    result.manifest.pdf_available = sum(1 for p in papers if p.pdf_available)
    result.manifest.abstract_only = sum(1 for p in papers if p.evidence_level == "abstract_only")
    result.manifest.selected = len(papers)

    write_json(settings.outputs_dir / "papers.json", [paper.to_dict() for paper in papers])
    write_json(settings.outputs_dir / "chunks.json", [chunk.to_dict() for chunk in chunks])
    write_json(settings.outputs_dir / "search_manifest.json", result.manifest.to_dict())

    kb = KnowledgeBase(settings, reset=True)
    kb.index(chunks)
    warnings = result.manifest.warnings + kb.warnings
    write_text(settings.outputs_dir / "warnings.txt", "\n".join(warnings) + ("\n" if warnings else ""))
    return {
        "papers": len(papers),
        "chunks": len(chunks),
        "outputs_dir": str(settings.outputs_dir),
        "warnings": warnings,
    }


def generate_review(
    topic: str,
    top_k: int = 20,
    core_count: int = 5,
    related_count: int = 10,
    settings: Settings | None = None,
) -> Dict:
    settings = settings or get_settings()
    papers = [PaperRecord.from_dict(data) for data in read_json(settings.outputs_dir / "papers.json", default=[])]
    if not papers:
        raise FileNotFoundError("outputs/papers.json not found. Run bootstrap first.")
    rag = HybridRAG(settings)
    evidence = rag.search(topic, top_k=top_k)
    llm = LLMAdapter(settings)
    generator = LiteratureReviewGenerator(llm)
    manifest = read_json(settings.outputs_dir / "search_manifest.json", default={})
    review = generator.build_review(topic, papers, evidence, core_count, related_count, manifest=manifest)
    write_json(settings.outputs_dir / "literature_review.json", review)
    write_text(settings.outputs_dir / "literature_review.txt", render_review_txt(review))
    return review


def ask_question(
    question: str,
    top_k: int = 8,
    settings: Settings | None = None,
) -> Dict:
    settings = settings or get_settings()
    rag = HybridRAG(settings)
    evidence = rag.search(question, top_k=top_k)
    llm = LLMAdapter(settings)
    generator = LiteratureReviewGenerator(llm)
    answer = generator.answer_question(question, evidence)
    write_json(settings.outputs_dir / "answer.json", answer)
    write_text(settings.outputs_dir / "answer.txt", render_answer_txt(answer))
    return answer


def test_llm(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    llm = LLMAdapter(settings)
    data = llm.generate_json(
        'Return {"ok": true, "provider": "configured-provider"} as JSON.',
        max_tokens=200,
    )
    return str(data)
