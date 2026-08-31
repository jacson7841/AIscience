"""Configuration helpers for the literature mining MVP."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    outputs_dir: Path = PROJECT_ROOT / "outputs"
    data_dir: Path = PROJECT_ROOT / "data_storage"
    pdf_dir: Path = PROJECT_ROOT / "data_storage" / "pdfs"
    knowledge_base_dir: Path = PROJECT_ROOT / "data_storage" / "knowledge_base"
    collection_name: str = "literature_chunks"

    llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek")
    llm_api_key: str = os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    llm_base_url: str = os.getenv("LLM_BASE_URL", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    llm_model: str = os.getenv("LLM_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "60"))

    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "sentence-transformers")
    enable_dense: bool = os.getenv("ENABLE_DENSE_RETRIEVAL", "true").lower() != "false"

    openalex_mailto: str = os.getenv("OPENALEX_MAILTO", "")
    s2_api_key: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    request_retries: int = int(os.getenv("REQUEST_RETRIES", "2"))
    max_expanded_queries: int = int(os.getenv("MAX_EXPANDED_QUERIES", "6"))
    arxiv_delay_seconds: float = float(os.getenv("ARXIV_DELAY_SECONDS", "3.1"))
    openalex_delay_seconds: float = float(os.getenv("OPENALEX_DELAY_SECONDS", "1.1"))
    s2_delay_seconds: float = float(os.getenv("SEMANTIC_SCHOLAR_DELAY_SECONDS", "1.2"))

    chunk_max_chars: int = int(os.getenv("CHUNK_MAX_CHARS", "1000"))
    chunk_overlap_chars: int = int(os.getenv("CHUNK_OVERLAP_CHARS", "150"))

    def ensure_dirs(self) -> None:
        for directory in [
            self.outputs_dir,
            self.data_dir,
            self.pdf_dir,
            self.knowledge_base_dir,
        ]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                if not directory.exists():
                    raise


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
