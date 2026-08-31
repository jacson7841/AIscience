"""PDF acquisition and page-level parsing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from .config import Settings
from .schemas import PaperRecord
from .utils import stable_id


SECTION_RE = re.compile(
    r"^(\d+(\.\d+)*\s+)?(abstract|introduction|related work|method|methodology|"
    r"experiments?|evaluation|results?|discussion|limitations?|conclusion|future work|references)\b",
    re.I,
)


def acquire_pdf(paper: PaperRecord, settings: Settings) -> Optional[Path]:
    if paper.local_pdf_path:
        local_path = Path(paper.local_pdf_path)
        if local_path.exists():
            return local_path
    if not paper.pdf_url or requests is None:
        return None
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{paper.paper_id}.pdf"
    path = settings.pdf_dir / filename
    if path.exists() and path.stat().st_size > 1024:
        return path
    try:
        response = requests.get(paper.pdf_url, stream=True, timeout=settings.request_timeout)
        response.raise_for_status()
        first = True
        with path.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                if first and b"%PDF" not in chunk[:32]:
                    raise ValueError("downloaded content does not look like a PDF")
                first = False
                stream.write(chunk)
        if path.stat().st_size < 1024:
            path.unlink(missing_ok=True)
            return None
        return path
    except Exception:
        path.unlink(missing_ok=True)
        return None


def parse_pdf_pages(pdf_path: Path) -> List[Dict]:
    if fitz is None:
        return []
    pages: List[Dict] = []
    current_section = ""
    with fitz.open(pdf_path) as doc:
        for idx, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            section = detect_section(text) or current_section
            if section:
                current_section = section
            pages.append(
                {
                    "page_number": idx,
                    "section": section or "",
                    "text": text.strip(),
                }
            )
    return pages


def detect_section(text: str) -> str:
    for raw_line in (text or "").splitlines()[:25]:
        line = re.sub(r"\s+", " ", raw_line).strip()
        if 3 <= len(line) <= 90 and SECTION_RE.search(line):
            return line
    return ""
