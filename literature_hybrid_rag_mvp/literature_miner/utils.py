"""Small deterministic utilities shared by the MVP modules."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]*|[\u4e00-\u9fff]")


def normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r"https?://\S+", " ", title)
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def extract_arxiv_id(value: str) -> str:
    match = re.search(
        r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)",
        value or "",
        flags=re.I,
    )
    if match:
        return match.group(1)
    match = re.search(r"\b([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)\b", value or "")
    return match.group(1) if match else ""


def canonical_arxiv_id(value: str) -> str:
    return re.sub(r"v\d+$", "", value or "", flags=re.I).lower()


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def tokenize(text: str) -> List[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text or "")]


def unique_keep_order(values: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if not value:
            continue
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value.strip())
    return out


def safe_year(value: Any) -> Optional[int]:
    if value is None:
        return None
    match = re.search(r"(19|20)\d{2}", str(value))
    if not match:
        return None
    return int(match.group(0))


def reconstruct_openalex_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    if not inverted_index:
        return ""
    positions: Dict[int, str] = {}
    for word, word_positions in inverted_index.items():
        for pos in word_positions:
            positions[int(pos)] = word
    if not positions:
        return ""
    return " ".join(positions[index] for index in sorted(positions))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_with_retry(path, json.dumps(data, ensure_ascii=False, indent=2))


def short_text(text: str, max_chars: int = 900) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def log_scale(value: int, max_value: int = 1000) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(max_value))


def source_ref_from_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": chunk.get("title", ""),
        "page": chunk.get("page_number"),
        "url": chunk.get("source_url", ""),
        "section": chunk.get("section", ""),
    }


def _write_text_with_retry(path: Path, text: str, attempts: int = 5) -> None:
    last_error: Exception | None = None
    temp_path = path.with_name(f"{path.name}.tmp")
    for attempt in range(attempts):
        try:
            temp_path.write_text(text, encoding="utf-8")
            temp_path.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.15 * (attempt + 1))
    raise last_error  # type: ignore[misc]
