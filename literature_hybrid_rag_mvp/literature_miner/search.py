"""Multi-source scholarly search and paper normalization."""

from __future__ import annotations

import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from .config import Settings
from .schemas import PaperRecord, SearchManifest, SourceStats
from .utils import (
    canonical_arxiv_id,
    extract_arxiv_id,
    log_scale,
    normalize_title,
    reconstruct_openalex_abstract,
    safe_year,
    stable_id,
    tokenize,
    unique_keep_order,
)


ACADEMIC_SOURCES = ("arxiv", "openalex", "semantic_scholar")


@dataclass
class SearchResult:
    papers: List[PaperRecord] = field(default_factory=list)
    manifest: SearchManifest = field(default_factory=SearchManifest)


class LiteratureSearcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def expand_queries(self, seed_topics: Sequence[str]) -> List[str]:
        variants: List[str] = []
        for topic in seed_topics:
            topic = topic.strip()
            if not topic:
                continue
            variants.extend(
                [
                    topic,
                    f"{topic} literature review",
                    f"{topic} hypothesis generation",
                    f"{topic} scientific discovery agent",
                ]
            )
        return unique_keep_order(variants)

    def search(
        self,
        seed_topics: Sequence[str],
        limit: int = 30,
        sources: Sequence[str] = ACADEMIC_SOURCES,
        local_pdf_dir: Optional[Path] = None,
        demo: bool = False,
        max_queries: Optional[int] = None,
    ) -> SearchResult:
        expanded_queries = self.expand_queries(seed_topics)
        query_limit = max_queries if max_queries is not None else self.settings.max_expanded_queries
        if query_limit and query_limit > 0:
            used_queries = expanded_queries[:query_limit]
        else:
            used_queries = expanded_queries
        manifest = SearchManifest(
            seed_topics=list(seed_topics),
            expanded_queries=used_queries,
            sources={source: SourceStats() for source in sources},
        )
        if len(used_queries) < len(expanded_queries):
            manifest.warnings.append(
                f"Limited expanded queries from {len(expanded_queries)} to {len(used_queries)} to reduce API rate-limit risk."
            )
        if "openalex" in sources and not self.settings.openalex_mailto:
            manifest.warnings.append("OPENALEX_MAILTO is not set; OpenAlex may use the slower common pool.")
        if "semantic_scholar" in sources and not self.settings.s2_api_key:
            manifest.warnings.append("SEMANTIC_SCHOLAR_API_KEY is not set; Semantic Scholar rate limits may be stricter.")
        if demo:
            papers = self._demo_papers(seed_topics[0] if seed_topics else "AI Scientist")
            manifest.warnings.append("Demo mode uses built-in sample records; do not use demo papers as final academic evidence.")
            manifest.before_dedup = len(papers)
            manifest.after_dedup = len(papers)
            manifest.verified = len(papers)
            manifest.pdf_available = 0
            manifest.abstract_only = len(papers)
            manifest.selected = min(limit, len(papers))
            for source in sources:
                manifest.sources[source] = SourceStats(queries=["demo"], returned=2)
            scored = self.score_papers(papers[:limit], seed_topics)
            return SearchResult(scored, manifest)

        if requests is None:
            manifest.warnings.append("requests is not installed; external search skipped.")
            papers = []
        else:
            papers = []
            per_query_source_limit = max(2, min(8, math.ceil(limit / max(1, len(manifest.expanded_queries))) + 1))
            for query in manifest.expanded_queries:
                for source in sources:
                    stats = manifest.sources.setdefault(source, SourceStats())
                    stats.queries.append(query)
                    try:
                        found = self._search_source(source, query, per_query_source_limit)
                        stats.returned += len(found)
                        papers.extend(found)
                    except Exception as exc:  # noqa: BLE001 - keep fan-out robust
                        stats.errors.append(f"{query}: {exc}")
                        manifest.warnings.append(f"{source} failed for query '{query}': {exc}")

        if local_pdf_dir:
            local_papers = self._local_pdf_records(local_pdf_dir)
            if local_papers:
                manifest.sources.setdefault("local_pdf", SourceStats()).returned = len(local_papers)
                papers.extend(local_papers)

        manifest.before_dedup = len(papers)
        papers = deduplicate_papers(papers)
        manifest.after_dedup = len(papers)
        papers = self.score_papers(papers, seed_topics)
        papers.sort(key=paper_rank_score, reverse=True)
        selected = papers[:limit]
        manifest.verified = sum(1 for p in selected if p.verification_status == "verified")
        manifest.pdf_available = sum(1 for p in selected if p.pdf_available)
        manifest.abstract_only = sum(1 for p in selected if p.evidence_level == "abstract_only")
        manifest.selected = len(selected)
        return SearchResult(selected, manifest)

    def _search_source(self, source: str, query: str, limit: int) -> List[PaperRecord]:
        if source == "arxiv":
            return self._search_arxiv(query, limit)
        if source == "openalex":
            return self._search_openalex(query, limit)
        if source == "semantic_scholar":
            return self._search_semantic_scholar(query, limit)
        raise ValueError(f"Unsupported source: {source}")

    def _search_arxiv(self, query: str, limit: int) -> List[PaperRecord]:
        assert requests is not None
        params = {
            "search_query": arxiv_query(query),
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        response = self._get_with_retries(
            "http://export.arxiv.org/api/query",
            source="arxiv",
            params=params,
        )
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers: List[PaperRecord] = []
        for entry in root.findall("atom:entry", ns):
            title = clean_xml_text(entry.findtext("atom:title", default="", namespaces=ns))
            abstract = clean_xml_text(entry.findtext("atom:summary", default="", namespaces=ns))
            entry_id = entry.findtext("atom:id", default="", namespaces=ns)
            arxiv_id = entry_id.rsplit("/abs/", 1)[-1] if "/abs/" in entry_id else entry_id.rsplit("/", 1)[-1]
            authors = [
                clean_xml_text(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)
            ]
            categories = [node.attrib.get("term", "") for node in entry.findall("atom:category", ns)]
            published = entry.findtext("atom:published", default="", namespaces=ns)
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else ""
            paper_id = stable_id("paper", f"arxiv:{arxiv_id or title}")
            papers.append(
                PaperRecord(
                    paper_id=paper_id,
                    title=title,
                    normalized_title=normalize_title(title),
                    authors=[a for a in authors if a],
                    year=safe_year(published),
                    arxiv_id=arxiv_id,
                    abstract=abstract,
                    url=entry_id,
                    pdf_url=pdf_url,
                    sources=["arxiv"],
                    verification_status="verified" if arxiv_id else "unverified",
                    pdf_available=bool(pdf_url),
                    evidence_level="metadata_with_pdf" if pdf_url else "abstract_only",
                    topics=categories,
                )
            )
        return papers

    def _search_openalex(self, query: str, limit: int) -> List[PaperRecord]:
        assert requests is not None
        params = {
            "search": query,
            "per-page": limit,
            "sort": "relevance_score:desc",
        }
        headers = {}
        if self.settings.openalex_mailto:
            params["mailto"] = self.settings.openalex_mailto
            headers["User-Agent"] = f"literature-hybrid-rag-mvp/0.1 (mailto:{self.settings.openalex_mailto})"
        response = self._get_with_retries(
            "https://api.openalex.org/works",
            source="openalex",
            params=params,
            headers=headers,
        )
        data = response.json()
        papers: List[PaperRecord] = []
        for item in data.get("results", []):
            title = item.get("title") or ""
            abstract = reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
            authors = [
                auth.get("author", {}).get("display_name", "")
                for auth in item.get("authorships", [])
                if auth.get("author", {}).get("display_name")
            ]
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            best_oa = item.get("best_oa_location") or {}
            pdf_url = primary_location.get("pdf_url") or best_oa.get("pdf_url") or ""
            url = primary_location.get("landing_page_url") or item.get("doi") or item.get("id") or ""
            arxiv_id = extract_arxiv_id(" ".join([url, pdf_url, item.get("doi") or "", item.get("id") or ""]))
            topics = [
                topic.get("display_name", "")
                for topic in item.get("topics", [])
                if topic.get("display_name")
            ]
            primary_topic = (item.get("primary_topic") or {}).get("display_name")
            if primary_topic:
                topics.insert(0, primary_topic)
            paper_id = stable_id("paper", item.get("id") or item.get("doi") or title)
            papers.append(
                PaperRecord(
                    paper_id=paper_id,
                    title=title,
                    normalized_title=normalize_title(title),
                    authors=authors,
                    year=safe_year(item.get("publication_year") or item.get("publication_date")),
                    venue=source.get("display_name", "") if isinstance(source, dict) else "",
                    doi=(item.get("doi") or "").replace("https://doi.org/", ""),
                    arxiv_id=arxiv_id,
                    openalex_id=item.get("id", ""),
                    abstract=abstract,
                    url=url,
                    pdf_url=pdf_url,
                    citation_count=int(item.get("cited_by_count") or 0),
                    sources=["openalex"],
                    verification_status="verified" if item.get("id") else "unverified",
                    pdf_available=bool(pdf_url),
                    evidence_level="metadata_with_pdf" if pdf_url else ("abstract_only" if abstract else "metadata_only"),
                    topics=unique_keep_order(topics),
                )
            )
        return papers

    def _search_semantic_scholar(self, query: str, limit: int) -> List[PaperRecord]:
        assert requests is not None
        fields = ",".join(
            [
                "title",
                "authors",
                "abstract",
                "year",
                "externalIds",
                "url",
                "publicationDate",
                "citationCount",
                "openAccessPdf",
                "publicationVenue",
                "fieldsOfStudy",
            ]
        )
        headers = {}
        if self.settings.s2_api_key:
            headers["x-api-key"] = self.settings.s2_api_key
        params = {"query": query, "limit": limit, "fields": fields}
        response = self._get_with_retries(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            source="semantic_scholar",
            params=params,
            headers=headers,
        )
        papers: List[PaperRecord] = []
        for item in response.json().get("data", []):
            title = item.get("title") or ""
            external = item.get("externalIds") or {}
            venue = item.get("publicationVenue") or {}
            pdf_url = (item.get("openAccessPdf") or {}).get("url") or ""
            url = item.get("url") or ""
            arxiv_id = external.get("ArXiv", "") or extract_arxiv_id(" ".join([url, pdf_url]))
            doi = external.get("DOI", "")
            paper_id = stable_id("paper", item.get("paperId") or doi or arxiv_id or title)
            papers.append(
                PaperRecord(
                    paper_id=paper_id,
                    title=title,
                    normalized_title=normalize_title(title),
                    authors=[a.get("name", "") for a in item.get("authors", []) if a.get("name")],
                    year=safe_year(item.get("year") or item.get("publicationDate")),
                    venue=venue.get("name", "") if isinstance(venue, dict) else "",
                    doi=doi,
                    arxiv_id=arxiv_id,
                    s2_id=item.get("paperId", ""),
                    abstract=item.get("abstract") or "",
                    url=url,
                    pdf_url=pdf_url,
                    citation_count=int(item.get("citationCount") or 0),
                    sources=["semantic_scholar"],
                    verification_status="verified" if item.get("paperId") else "unverified",
                    pdf_available=bool(pdf_url),
                    evidence_level="metadata_with_pdf" if pdf_url else ("abstract_only" if item.get("abstract") else "metadata_only"),
                    topics=item.get("fieldsOfStudy") or [],
                )
            )
        return papers

    def _get_with_retries(self, url: str, source: str, params: Dict, headers: Optional[Dict] = None):
        assert requests is not None
        delay = self._source_delay(source)
        last_error = None
        for attempt in range(self.settings.request_retries + 1):
            if delay > 0:
                time.sleep(delay)
            response = requests.get(
                url,
                params=params,
                headers=headers or {},
                timeout=self.settings.request_timeout,
            )
            if response.status_code != 429:
                response.raise_for_status()
                return response
            last_error = requests.HTTPError(f"429 Too Many Requests for {source}: {response.url}")
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = delay * (attempt + 2)
            else:
                wait = max(delay, 1.0) * (attempt + 2)
            time.sleep(wait)
        raise last_error or RuntimeError(f"Request failed for {source}")

    def _source_delay(self, source: str) -> float:
        if source == "arxiv":
            return self.settings.arxiv_delay_seconds
        if source == "openalex":
            if self.settings.openalex_mailto:
                return min(self.settings.openalex_delay_seconds, 0.25)
            return self.settings.openalex_delay_seconds
        if source == "semantic_scholar":
            return self.settings.s2_delay_seconds
        return 0.0

    def _local_pdf_records(self, local_pdf_dir: Path) -> List[PaperRecord]:
        if not local_pdf_dir.exists():
            return []
        papers = []
        for pdf_path in sorted(local_pdf_dir.glob("*.pdf")):
            title = pdf_path.stem.replace("_", " ").replace("-", " ")
            papers.append(
                PaperRecord(
                    paper_id=stable_id("paper", str(pdf_path.resolve())),
                    title=title,
                    normalized_title=normalize_title(title),
                    url=str(pdf_path.resolve()),
                    sources=["local_pdf"],
                    verification_status="verified",
                    pdf_available=True,
                    evidence_level="full_text",
                    local_pdf_path=str(pdf_path.resolve()),
                )
            )
        return papers

    def score_papers(self, papers: List[PaperRecord], seed_topics: Sequence[str]) -> List[PaperRecord]:
        query_tokens = {
            token
            for token in tokenize(" ".join(seed_topics))
            if token not in SCORE_STOPWORDS and len(token) > 1
        }
        query_phrases = [normalize_title(topic) for topic in seed_topics if normalize_title(topic)]
        current_year = 2026
        for paper in papers:
            title_tokens = set(tokenize(paper.title))
            abstract_tokens = set(tokenize(paper.abstract))
            topic_tokens = set(tokenize(" ".join(paper.topics + paper.keywords)))
            title_overlap = len(query_tokens & title_tokens) / max(1, len(query_tokens))
            abstract_overlap = len(query_tokens & abstract_tokens) / max(1, len(query_tokens))
            topic_overlap = len(query_tokens & topic_tokens) / max(1, len(query_tokens))
            title_text = normalize_title(paper.title)
            body_text = normalize_title(" ".join([paper.title, paper.abstract, " ".join(paper.topics + paper.keywords)]))
            phrase_bonus = 0.0
            for phrase in query_phrases:
                phrase_tokens = [token for token in phrase.split() if token not in SCORE_STOPWORDS and len(token) > 1]
                if len(phrase_tokens) >= 2 and " ".join(phrase_tokens[:2]) in title_text:
                    phrase_bonus = max(phrase_bonus, 0.22)
                elif len(phrase_tokens) >= 3 and all(token in body_text for token in phrase_tokens[:3]):
                    phrase_bonus = max(phrase_bonus, 0.12)
            paper.relevance_score = round(
                min(1.0, 0.58 * title_overlap + 0.30 * abstract_overlap + 0.12 * topic_overlap + phrase_bonus),
                4,
            )
            source_bonus = min(1.0, len(paper.sources) / 3)
            recency = 0.0
            if paper.year:
                recency = max(0.0, min(1.0, 1 - ((current_year - paper.year) / 12)))
            paper.utility_score = round(
                min(
                    1.0,
                    0.45 * log_scale(paper.citation_count)
                    + 0.20 * recency
                    + 0.20 * source_bonus
                    + 0.15 * (1.0 if paper.pdf_available else 0.0),
                ),
                4,
            )
        return papers

    def _demo_papers(self, topic: str) -> List[PaperRecord]:
        raw = [
            (
                "The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery",
                ["Yamada", "Lange", "Lu"],
                2024,
                "An AI Scientist style system automates idea generation, experiment execution, paper writing, and review for machine learning research.",
                "https://arxiv.org/abs/2408.06292",
                "2408.06292",
                140,
                ["arxiv", "semantic_scholar"],
            ),
            (
                "Large Language Models as Scientific Agents",
                ["Research Team"],
                2024,
                "LLM agents can coordinate literature review, planning, tool use, and result interpretation, but robust evaluation remains difficult.",
                "https://example.org/llm-scientific-agents",
                "",
                52,
                ["openalex"],
            ),
            (
                "Hypothesis Generation with Retrieval-Augmented Language Models",
                ["Example", "Author"],
                2023,
                "Retrieval-augmented workflows can generate grounded hypotheses by linking claims to prior literature and explicit evidence snippets.",
                "https://example.org/rag-hypothesis",
                "",
                83,
                ["semantic_scholar", "openalex"],
            ),
            (
                "Automated Discovery in Simulation Benchmarks",
                ["Demo", "Scientist"],
                2022,
                "Most automated discovery systems are evaluated in simulation or benchmark-only settings, leaving real-world closed-loop validation underexplored.",
                "https://example.org/simulation-benchmarks",
                "",
                120,
                ["openalex"],
            ),
            (
                "Literature Review Agents with Citation-Grounded Synthesis",
                ["Citation", "Miner"],
                2025,
                "Citation-grounded agents improve research review reliability by preserving source metadata, evidence chunks, and conflict notes.",
                "https://example.org/citation-grounded-agents",
                "",
                19,
                ["arxiv"],
            ),
        ]
        papers = []
        for title, authors, year, abstract, url, arxiv_id, citations, sources in raw:
            papers.append(
                PaperRecord(
                    paper_id=stable_id("paper", title),
                    title=title,
                    normalized_title=normalize_title(title),
                    authors=authors,
                    year=year,
                    venue="Demo Corpus",
                    arxiv_id=arxiv_id,
                    abstract=abstract,
                    url=url,
                    citation_count=citations,
                    sources=sources,
                    verification_status="verified",
                    pdf_available=False,
                    evidence_level="abstract_only",
                    topics=["AI Scientist", "RAG", "scientific discovery", topic],
                    relevance_score=0.8,
                    utility_score=0.7,
                )
            )
        return papers


def arxiv_query(query: str) -> str:
    if any(operator in query for operator in ["cat:", "ti:", "abs:", "all:", " AND ", " OR "]):
        return query
    terms = tokenize(query)[:8]
    if not terms:
        return query
    return " AND ".join(f"all:{term}" for term in terms)


def clean_xml_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


SCORE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "towards",
    "toward",
    "using",
    "with",
}


def paper_rank_score(paper: PaperRecord) -> float:
    return paper.relevance_score * 0.82 + paper.utility_score * 0.18


def deduplicate_papers(papers: Iterable[PaperRecord]) -> List[PaperRecord]:
    by_key: Dict[str, PaperRecord] = {}
    for paper in papers:
        key = dedup_key(paper)
        if key not in by_key:
            by_key[key] = paper
            continue
        by_key[key] = merge_papers(by_key[key], paper)
    by_title: Dict[str, PaperRecord] = {}
    for paper in by_key.values():
        title_key = paper.normalized_title
        if title_key and title_key in by_title:
            by_title[title_key] = merge_papers(by_title[title_key], paper)
        elif title_key:
            by_title[title_key] = paper
        else:
            by_title[dedup_key(paper)] = paper
    return list(by_title.values())


def dedup_key(paper: PaperRecord) -> str:
    if paper.doi:
        return f"doi:{paper.doi.lower()}"
    if paper.arxiv_id:
        return f"arxiv:{canonical_arxiv_id(paper.arxiv_id)}"
    if paper.s2_id:
        return f"s2:{paper.s2_id.lower()}"
    if paper.openalex_id:
        return f"openalex:{paper.openalex_id.lower()}"
    return f"title:{paper.normalized_title}"


def merge_papers(a: PaperRecord, b: PaperRecord) -> PaperRecord:
    a.sources = unique_keep_order(a.sources + b.sources)
    for attr in ["doi", "arxiv_id", "openalex_id", "s2_id", "abstract", "url", "pdf_url", "venue", "local_pdf_path"]:
        if not getattr(a, attr) and getattr(b, attr):
            setattr(a, attr, getattr(b, attr))
    if not a.authors and b.authors:
        a.authors = b.authors
    if not a.year and b.year:
        a.year = b.year
    a.citation_count = max(a.citation_count, b.citation_count)
    a.topics = unique_keep_order(a.topics + b.topics)
    a.keywords = unique_keep_order(a.keywords + b.keywords)
    a.pdf_available = a.pdf_available or b.pdf_available
    if a.pdf_available:
        a.evidence_level = "metadata_with_pdf"
    if len(a.sources) > 1 or a.doi or a.arxiv_id or a.s2_id or a.openalex_id:
        a.verification_status = "verified"
    return a
