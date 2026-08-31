"""CLI entry point for the literature mining MVP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from literature_miner.config import get_settings
from literature_miner.pipeline import ask_question, bootstrap, generate_review, test_llm


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="AI Scientist literature mining MVP")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bootstrap = sub.add_parser("bootstrap", help="Build the initial literature knowledge base")
    p_bootstrap.add_argument("--seed", type=Path, required=True, help="JSON list of seed topics")
    p_bootstrap.add_argument("--limit", type=int, default=30, help="Final paper count to keep")
    p_bootstrap.add_argument("--local-pdf-dir", type=Path, default=None, help="Optional folder of local PDFs")
    p_bootstrap.add_argument("--demo", action="store_true", help="Use built-in demo papers instead of external APIs")
    p_bootstrap.add_argument("--skip-pdf-download", action="store_true", help="Use abstracts only")
    p_bootstrap.add_argument("--no-dense", action="store_true", help="Disable Chroma dense retrieval for offline smoke tests")
    p_bootstrap.add_argument("--max-queries", type=int, default=None, help="Limit expanded online search queries to reduce rate-limit risk")
    p_bootstrap.add_argument("--sources", default=None, help="Comma-separated sources, e.g. arxiv,openalex")

    p_review = sub.add_parser("review", help="Generate sourced literature review JSON and TXT")
    p_review.add_argument("--topic", required=True)
    p_review.add_argument("--top-k", type=int, default=20)
    p_review.add_argument("--core-count", type=int, default=5)
    p_review.add_argument("--related-count", type=int, default=10)
    p_review.add_argument("--no-dense", action="store_true", help="Disable Chroma dense retrieval")

    p_ask = sub.add_parser("ask", help="Ask a question against the local knowledge base")
    p_ask.add_argument("--question", required=True)
    p_ask.add_argument("--top-k", type=int, default=8)
    p_ask.add_argument("--no-dense", action="store_true", help="Disable Chroma dense retrieval")

    sub.add_parser("test-llm", help="Run a minimal configured LLM JSON call")

    args = parser.parse_args()
    settings = get_settings()
    if getattr(args, "no_dense", False):
        settings.enable_dense = False

    if args.command == "bootstrap":
        sources = None
        if args.sources:
            sources = [source.strip() for source in args.sources.split(",") if source.strip()]
        result = bootstrap(
            seed_path=args.seed,
            limit=args.limit,
            settings=settings,
            local_pdf_dir=args.local_pdf_dir,
            demo=args.demo,
            skip_pdf_download=args.skip_pdf_download,
            max_queries=args.max_queries,
            sources=sources,
        )
        print(f"bootstrap complete: papers={result['papers']} chunks={result['chunks']} outputs={result['outputs_dir']}")
        if result["warnings"]:
            print("warnings:")
            for warning in result["warnings"]:
                print(f"- {warning}")
    elif args.command == "review":
        review = generate_review(args.topic, args.top_k, args.core_count, args.related_count, settings=settings)
        print(f"review complete: {settings.outputs_dir / 'literature_review.json'}")
        print(f"text complete: {settings.outputs_dir / 'literature_review.txt'}")
        print(f"core_papers={len(review.get('core_papers', []))} gaps={len(review.get('research_gaps', []))}")
    elif args.command == "ask":
        answer = ask_question(args.question, args.top_k, settings=settings)
        print(f"answer complete: {settings.outputs_dir / 'answer.json'}")
        print(answer.get("answer", ""))
    elif args.command == "test-llm":
        print(test_llm(settings))


if __name__ == "__main__":
    main()
