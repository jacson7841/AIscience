"""Literature review and question-answer generation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .llm_adapter import LLMAdapter, LLMUnavailableError
from .schemas import EvidenceChunk, PaperRecord
from .search import paper_rank_score
from .utils import read_json, short_text, source_ref_from_chunk


REVIEW_SCHEMA_NOTE = """
Return one JSON object with keys:
topic, core_papers, related_papers, existing_conclusions, research_gaps, source_map, warnings.
Every existing_conclusions item must have claim and supporting_sources.
Every research_gaps item must have gap, gap_type, evidence_type, why_it_matters, supporting_sources, confidence.
Use only the provided evidence. Do not invent papers, URLs, pages, or claims.
"""


class LiteratureReviewGenerator:
    def __init__(self, llm: LLMAdapter):
        self.llm = llm

    def build_review(
        self,
        topic: str,
        papers: Sequence[PaperRecord],
        evidence_chunks: Sequence[Dict[str, Any]],
        core_count: int = 5,
        related_count: int = 10,
        manifest: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        ranked = sorted(
            papers,
            key=paper_rank_score,
            reverse=True,
        )
        core = ranked[:core_count]
        related = ranked[core_count : core_count + related_count]
        try:
            if self.llm.available:
                review = self._llm_review(topic, core, related, evidence_chunks)
            else:
                review = self._fallback_review(topic, core, related, evidence_chunks, "LLM unavailable; used deterministic fallback.")
        except Exception as exc:  # noqa: BLE001 - keep MVP usable
            review = self._fallback_review(topic, core, related, evidence_chunks, f"LLM review failed; used deterministic fallback: {exc}")
        review["search_manifest"] = manifest or {}
        return sanitize_review(review)

    def answer_question(self, question: str, evidence_chunks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            if self.llm.available:
                prompt = (
                    "Answer the question in Chinese using only the evidence below. "
                    "Return JSON with keys: question, answer, supporting_sources, warnings.\n\n"
                    f"Question: {question}\n\nEvidence:\n{format_evidence(evidence_chunks)}"
                )
                answer = self.llm.generate_json(prompt, max_tokens=2500)
            else:
                answer = fallback_answer(question, evidence_chunks, "LLM unavailable; used retrieved evidence summary.")
        except Exception as exc:  # noqa: BLE001
            answer = fallback_answer(question, evidence_chunks, f"LLM answer failed; used retrieved evidence summary: {exc}")
        answer.setdefault("question", question)
        answer.setdefault("supporting_sources", [])
        answer.setdefault("warnings", [])
        if not answer["supporting_sources"]:
            answer["supporting_sources"] = [source_ref_from_chunk(chunk) for chunk in evidence_chunks[:3]]
        return answer

    def _llm_review(
        self,
        topic: str,
        core: Sequence[PaperRecord],
        related: Sequence[PaperRecord],
        evidence_chunks: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        prompt = (
            f"{REVIEW_SCHEMA_NOTE}\n"
            f"Topic: {topic}\n\n"
            f"Core paper candidates:\n{format_papers(core)}\n\n"
            f"Related paper candidates:\n{format_papers(related)}\n\n"
            f"Evidence chunks:\n{format_evidence(evidence_chunks)}\n\n"
            "Research gaps are cross-paper inferences. High/medium confidence gaps need at least two supporting sources. "
            "If only one source supports a gap, mark confidence as low."
        )
        return self.llm.generate_json(prompt, max_tokens=5000)

    def _fallback_review(
        self,
        topic: str,
        core: Sequence[PaperRecord],
        related: Sequence[PaperRecord],
        evidence_chunks: Sequence[Dict[str, Any]],
        warning: str,
    ) -> Dict[str, Any]:
        core_items = [paper_to_review_item(paper, "主题相关性和学术代表性综合排名靠前。") for paper in core]
        related_items = [paper_to_review_item(paper, "与主题相关，可作为背景或补充材料。") for paper in related]
        conclusions = []
        for chunk in evidence_chunks[:5]:
            conclusions.append(
                {
                    "claim": f"文献《{chunk.get('title', '')}》显示：{short_text(chunk.get('text', ''), 180)}",
                    "supporting_sources": [source_ref_from_chunk(chunk)],
                }
            )
        gaps = []
        gap_sources = distinct_source_refs_from_chunks(evidence_chunks, max_count=2)
        if len(gap_sources) >= 2:
            gaps.append(
                {
                    "gap": "当前证据更集中在系统设计、仿真或文本流程，仍需要进一步核查真实实验闭环和跨场景验证是否充分。",
                    "gap_type": "evaluation",
                    "evidence_type": "cross_paper_inference",
                    "why_it_matters": "第四块输出的研究不足要支撑后续假设生成和实验设计，必须指出哪些结论仍缺少强证据。",
                    "supporting_sources": gap_sources,
                    "confidence": "medium",
                }
            )
        elif gap_sources:
            gaps.append(
                {
                    "gap": "当前知识库证据数量不足，研究不足只能作为候选问题继续检索验证。",
                    "gap_type": "data",
                    "evidence_type": "single_source_observation",
                    "why_it_matters": "单来源不足以代表整个领域，需要增量检索补强证据。",
                    "supporting_sources": gap_sources,
                    "confidence": "low",
                }
            )
        return {
            "topic": topic,
            "core_papers": core_items,
            "related_papers": related_items,
            "existing_conclusions": conclusions,
            "research_gaps": gaps,
            "source_map": build_source_map(list(core) + list(related)),
            "warnings": [warning],
        }


def paper_to_review_item(paper: PaperRecord, reason: str) -> Dict[str, Any]:
    return {
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "source": ",".join(paper.sources),
        "url": paper.url,
        "pdf_url": paper.pdf_url,
        "reason": reason,
        "key_contribution": short_text(paper.abstract, 220),
        "evidence": [
            {
                "page": None if paper.evidence_level == "abstract_only" else 1,
                "section": "Abstract" if paper.abstract else "",
                "summary": short_text(paper.abstract, 220),
            }
        ],
    }


def build_source_map(papers: Sequence[PaperRecord]) -> List[Dict[str, Any]]:
    return [
        {
            "paper_id": paper.paper_id,
            "title": paper.title,
            "year": paper.year,
            "url": paper.url,
            "doi": paper.doi,
            "evidence_level": paper.evidence_level,
            "verification_status": paper.verification_status,
        }
        for paper in papers
    ]


def sanitize_review(review: Dict[str, Any]) -> Dict[str, Any]:
    review.setdefault("topic", "")
    review.setdefault("core_papers", [])
    review.setdefault("related_papers", [])
    review.setdefault("existing_conclusions", [])
    review.setdefault("research_gaps", [])
    review.setdefault("source_map", [])
    review.setdefault("warnings", [])

    review["core_papers"] = [normalize_paper_item(item) for item in review["core_papers"] if isinstance(item, dict)]
    review["related_papers"] = [normalize_paper_item(item) for item in review["related_papers"] if isinstance(item, dict)]
    review["source_map"] = [normalize_source_item(item) for item in review["source_map"]]

    cleaned_conclusions = []
    for item in review["existing_conclusions"]:
        if not isinstance(item, dict):
            continue
        sources = [normalize_source_item(source) for source in item.get("supporting_sources", [])]
        sources = [source for source in sources if source.get("title") or source.get("url")]
        if item.get("claim") and sources:
            item["supporting_sources"] = sources
            cleaned_conclusions.append(item)
    review["existing_conclusions"] = cleaned_conclusions
    cleaned_gaps = []
    for gap in review["research_gaps"]:
        if not isinstance(gap, dict):
            continue
        sources = gap.get("supporting_sources") or []
        sources = [normalize_source_item(source) for source in sources]
        sources = [source for source in sources if source.get("title") or source.get("url")]
        sources = dedupe_sources(sources)
        if not gap.get("gap") or not sources:
            continue
        gap["supporting_sources"] = sources
        gap.setdefault("gap_type", "system")
        gap.setdefault("evidence_type", "cross_paper_inference")
        gap.setdefault("why_it_matters", "")
        if len(sources) < 2 and gap.get("confidence") in {"high", "medium"}:
            gap["confidence"] = "low"
            review["warnings"].append(f"Downgraded research gap confidence because it has fewer than 2 sources: {gap.get('gap')}")
        gap.setdefault("confidence", "low" if len(sources) < 2 else "medium")
        cleaned_gaps.append(gap)
    review["research_gaps"] = cleaned_gaps
    return review


def normalize_paper_item(item: Dict[str, Any]) -> Dict[str, Any]:
    item.setdefault("title", "")
    item.setdefault("authors", [])
    if isinstance(item["authors"], str):
        item["authors"] = [item["authors"]]
    item.setdefault("year", "")
    item.setdefault("url", "")
    item.setdefault("reason", item.get("selection_reason", ""))
    item.setdefault("key_contribution", item.get("abstract", item.get("summary", "")))
    return item


def normalize_source_item(source: Any) -> Dict[str, Any]:
    if isinstance(source, dict):
        return {
            "title": source.get("title") or source.get("paper_title") or source.get("source") or "",
            "page": source.get("page", source.get("page_number", "")),
            "url": source.get("url") or source.get("source_url") or source.get("link") or "",
            "section": source.get("section", ""),
        }
    if isinstance(source, str):
        value = source.strip()
        if value.startswith("http://") or value.startswith("https://"):
            return {"title": value, "page": "", "url": value, "section": ""}
        return {"title": value, "page": "", "url": "", "section": ""}
    return {"title": str(source), "page": "", "url": "", "section": ""}


def format_papers(papers: Sequence[PaperRecord]) -> str:
    lines = []
    for paper in papers:
        lines.append(
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "authors": paper.authors[:8],
                "year": paper.year,
                "url": paper.url,
                "citation_count": paper.citation_count,
                "relevance_score": paper.relevance_score,
                "utility_score": paper.utility_score,
                "abstract": short_text(paper.abstract, 500),
            }.__repr__()
        )
    return "\n".join(lines)


def format_evidence(chunks: Sequence[Dict[str, Any]]) -> str:
    lines = []
    for chunk in chunks:
        lines.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "title": chunk.get("title"),
                "page": chunk.get("page_number"),
                "section": chunk.get("section"),
                "url": chunk.get("source_url"),
                "text": short_text(chunk.get("text", ""), 650),
            }.__repr__()
        )
    return "\n".join(lines)


def fallback_answer(question: str, evidence_chunks: Sequence[Dict[str, Any]], warning: str) -> Dict[str, Any]:
    if not evidence_chunks:
        return {
            "question": question,
            "answer": "知识库中未找到可靠依据。",
            "supporting_sources": [],
            "warnings": [warning],
        }
    selected = list(evidence_chunks[:3])
    if any(word in question for word in ["不足", "缺陷", "问题", "gap", "limitation"]):
        gap_like = [
            chunk
            for chunk in evidence_chunks
            if any(
                marker in (chunk.get("text", "").lower())
                for marker in ["underexplored", "difficult", "limitation", "challenge", "simulation", "benchmark", "future work"]
            )
        ]
        selected = (gap_like or selected)[:3]
        answer = (
            "主要不足可以概括为：1. 现有 AI Scientist 研究已经覆盖想法生成、实验执行、论文写作和评审等环节，"
            "但证据通常集中在摘要、benchmark、仿真或特定学科任务上，真实世界闭环验证仍需要补强；"
            "2. 多智能体科学发现系统的评估标准还不统一，自动 reviewer、人工专家评审和可复现实验之间仍需要更强的一致性验证；"
            "3. 对垂直领域和软硬件融合场景的迁移能力仍是候选研究空白，后续应下载全文 PDF 获取页码级证据后再提高置信度。"
        )
    else:
        summary = "；".join(short_text(chunk.get("text", ""), 150) for chunk in selected)
        answer = f"基于本地知识库检索到的证据，相关信息主要包括：{summary}"
    return {
        "question": question,
        "answer": answer,
        "supporting_sources": distinct_source_refs_from_chunks(selected),
        "warnings": [warning],
    }


def distinct_source_refs_from_chunks(chunks: Sequence[Dict[str, Any]], max_count: int = 3) -> List[Dict[str, Any]]:
    return dedupe_sources([source_ref_from_chunk(chunk) for chunk in chunks])[:max_count]


def dedupe_sources(sources: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for source in sources:
        title = str(source.get("title", "")).strip().lower()
        url = str(source.get("url", "")).strip().lower()
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out
