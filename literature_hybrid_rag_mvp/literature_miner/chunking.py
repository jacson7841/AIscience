"""Text chunking with provenance-preserving metadata."""

from __future__ import annotations

from typing import Dict, Iterable, List

from .schemas import EvidenceChunk, PaperRecord


def chunks_from_pages(
    paper: PaperRecord,
    pages: Iterable[Dict],
    max_chars: int = 1000,
    overlap_chars: int = 150,
) -> List[EvidenceChunk]:
    chunks: List[EvidenceChunk] = []
    chunk_index = 0
    for page in pages:
        text = normalize_text(page.get("text", ""))
        if not text:
            continue
        for part in split_text(text, max_chars=max_chars, overlap_chars=overlap_chars):
            if part:
                chunks.append(make_chunk(paper, chunk_index, part, page.get("page_number"), page.get("section", "")))
                chunk_index += 1
    return chunks


def chunks_from_abstract(paper: PaperRecord, max_chars: int = 1000, overlap_chars: int = 150) -> List[EvidenceChunk]:
    abstract = normalize_text(paper.abstract)
    if not abstract:
        return []
    temp = PaperRecord.from_dict(paper.to_dict())
    temp.evidence_level = "abstract_only"
    return chunks_from_pages(
        temp,
        [{"page_number": None, "section": "Abstract", "text": abstract}],
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )


def make_chunk(
    paper: PaperRecord,
    chunk_index: int,
    text: str,
    page_number,
    section: str,
) -> EvidenceChunk:
    chunk_id = f"{paper.paper_id}_chunk_{chunk_index:04d}"
    return EvidenceChunk(
        chunk_id=chunk_id,
        paper_id=paper.paper_id,
        chunk_index=chunk_index,
        title=paper.title,
        year=paper.year,
        doi=paper.doi,
        page_number=page_number,
        section=section,
        text=text,
        source_url=paper.url or paper.pdf_url,
        verification_status=paper.verification_status,
        evidence_level=paper.evidence_level,
    )


def normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def split_text(text: str, max_chars: int = 1000, overlap_chars: int = 150) -> List[str]:
    parts: List[str] = []
    start = 0
    while start < len(text):
        raw_end = min(len(text), start + max_chars)
        end = choose_boundary(text, start, raw_end, max_chars)
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        start = next_start(text, max(0, end - overlap_chars))
    return parts


def choose_boundary(text: str, start: int, raw_end: int, max_chars: int) -> int:
    if raw_end >= len(text):
        return len(text)
    floor = min(raw_end, start + max(120, int(max_chars * 0.65)))
    candidates = []
    for marker in [". ", "? ", "! ", "; ", "。", "？", "！", "；"]:
        pos = text.rfind(marker, floor, raw_end)
        if pos >= 0:
            candidates.append(pos + len(marker))
    return max(candidates) if candidates else raw_end


def next_start(text: str, proposed: int) -> int:
    if proposed <= 0:
        return 0
    if proposed >= len(text):
        return len(text)
    if text[proposed].isspace():
        return proposed + 1
    if not text[proposed].isalnum() or not text[proposed - 1].isalnum():
        return proposed
    space = text.find(" ", proposed, min(len(text), proposed + 80))
    return space + 1 if space >= 0 else proposed
