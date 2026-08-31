"""Render structured review/answer JSON into stable plain text files."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Dict, Iterable, List


def render_review_txt(review: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"研究主题：{review.get('topic', '')}")
    lines.append("")
    lines.append("一、核心论文")
    for idx, paper in enumerate(review.get("core_papers", []), start=1):
        lines.extend(render_paper(idx, paper))
    lines.append("")
    lines.append("二、相关论文")
    for idx, paper in enumerate(review.get("related_papers", []), start=1):
        lines.extend(render_paper(idx, paper))
    lines.append("")
    lines.append("三、已有研究结论")
    for idx, item in enumerate(review.get("existing_conclusions", []), start=1):
        lines.append(f"{idx}. 结论：{item.get('claim', '')}")
        lines.append(f"   对应来源：{format_sources(item.get('supporting_sources', []))}")
    lines.append("")
    lines.append("四、研究不足")
    for idx, item in enumerate(review.get("research_gaps", []), start=1):
        lines.append(f"{idx}. 不足：{item.get('gap', '')}")
        lines.append(f"   类型：{item.get('gap_type', '')}")
        lines.append(f"   证据类型：{item.get('evidence_type', '')}")
        lines.append(f"   置信度：{item.get('confidence', '')}")
        lines.append(f"   为什么重要：{item.get('why_it_matters', '')}")
        lines.append(f"   对应来源：{format_sources(item.get('supporting_sources', []))}")
    lines.append("")
    lines.append("五、来源清单")
    for idx, source in enumerate(review.get("source_map", []), start=1):
        normalized = normalize_source(source)
        lines.append(f"{idx}. {normalized.get('title', '')} | {normalized.get('url', '')}")
    lines.append("")
    lines.append("六、检索与建库说明")
    manifest = review.get("search_manifest", {})
    if manifest:
        lines.append(f"检索主题：{', '.join(manifest.get('seed_topics', []))}")
        lines.append(f"扩展检索式数量：{len(manifest.get('expanded_queries', []))}")
        lines.append(f"合并前：{manifest.get('before_dedup', 0)}，去重后：{manifest.get('after_dedup', 0)}，最终入库：{manifest.get('selected', 0)}")
    if review.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for warning in review.get("warnings", []):
            lines.append(f"- {warning}")
    return "\n".join(lines).strip() + "\n"


def render_answer_txt(answer: Dict[str, Any]) -> str:
    lines = [
        f"问题：{answer.get('question', '')}",
        "",
        f"回答：{answer.get('answer', '')}",
        "",
        "对应来源：",
    ]
    for idx, source in enumerate(answer.get("supporting_sources", []), start=1):
        normalized = normalize_source(source)
        lines.append(f"{idx}. {normalized.get('title', '')} | page={normalized.get('page')} | {normalized.get('url', '')}")
    if answer.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for warning in answer.get("warnings", []):
            lines.append(f"- {warning}")
    return "\n".join(lines).strip() + "\n"


def render_paper(index: int, paper: Dict[str, Any]) -> List[str]:
    authors = paper.get("authors", [])
    if isinstance(authors, str):
        authors = [authors]
    contribution = paper.get("key_contribution") or paper.get("abstract") or paper.get("summary") or ""
    reason = paper.get("reason") or paper.get("selection_reason") or ""
    return [
        f"{index}. {paper.get('title', '')}",
        f"   作者：{', '.join(authors[:6])}",
        f"   年份：{paper.get('year', '')}",
        f"   核心贡献：{contribution}",
        f"   选择理由：{reason}",
        f"   来源：{paper.get('url', '')}",
    ]


def format_sources(sources: Iterable[Any]) -> str:
    parts = []
    for source in sources:
        source = normalize_source(source)
        page = source.get("page")
        page_text = f", page {page}" if page not in (None, "") else ""
        parts.append(f"{source.get('title', '')}{page_text} ({source.get('url', '')})")
    return "; ".join(parts)


def normalize_source(source: Any) -> Dict[str, Any]:
    if isinstance(source, dict):
        title = source.get("title") or source.get("paper_title") or source.get("source") or ""
        url = source.get("url") or source.get("source_url") or source.get("link") or ""
        page = source.get("page", source.get("page_number", ""))
        section = source.get("section", "")
        return {"title": title, "url": url, "page": page, "section": section}
    if isinstance(source, str):
        value = source.strip()
        if value.startswith("http://") or value.startswith("https://"):
            return {"title": value, "url": value, "page": "", "section": ""}
        return {"title": value, "url": "", "page": "", "section": ""}
    return {"title": str(source), "url": "", "page": "", "section": ""}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    last_error = None
    for attempt in range(5):
        try:
            temp_path.write_text(text, encoding="utf-8")
            temp_path.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.15 * (attempt + 1))
    raise last_error
