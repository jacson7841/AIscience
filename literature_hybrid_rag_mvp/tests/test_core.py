from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from literature_miner.bm25 import BM25Document, BM25Index
from literature_miner.config import Settings
from literature_miner.pipeline import bootstrap, generate_review
from literature_miner.review import sanitize_review
from literature_miner.render_txt import render_review_txt
from literature_miner.search import deduplicate_papers
from literature_miner.schemas import PaperRecord
from literature_miner.utils import normalize_title, reconstruct_openalex_abstract


class CoreTests(unittest.TestCase):
    def test_openalex_abstract_reconstruction(self):
        index = {"hello": [0], "world": [1], "again": [2]}
        self.assertEqual(reconstruct_openalex_abstract(index), "hello world again")

    def test_dedup_merges_sources(self):
        a = PaperRecord(
            paper_id="a",
            title="Same Paper",
            normalized_title=normalize_title("Same Paper"),
            doi="10.1/demo",
            sources=["openalex"],
        )
        b = PaperRecord(
            paper_id="b",
            title="Same Paper",
            normalized_title=normalize_title("Same Paper"),
            doi="10.1/demo",
            sources=["semantic_scholar"],
            citation_count=10,
        )
        merged = deduplicate_papers([a, b])
        self.assertEqual(len(merged), 1)
        self.assertIn("openalex", merged[0].sources)
        self.assertIn("semantic_scholar", merged[0].sources)
        self.assertEqual(merged[0].citation_count, 10)

    def test_dedup_merges_arxiv_url_title_duplicates(self):
        a = PaperRecord(
            paper_id="a",
            title="The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery",
            normalized_title=normalize_title("The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery"),
            arxiv_id="2408.06292v1",
            sources=["arxiv"],
        )
        b = PaperRecord(
            paper_id="b",
            title="The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery",
            normalized_title=normalize_title("The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery"),
            arxiv_id="2408.06292",
            openalex_id="https://openalex.org/W4400000000",
            sources=["openalex"],
            citation_count=25,
        )
        merged = deduplicate_papers([a, b])
        self.assertEqual(len(merged), 1)
        self.assertIn("arxiv", merged[0].sources)
        self.assertIn("openalex", merged[0].sources)
        self.assertEqual(merged[0].citation_count, 25)

    def test_bm25_prefers_exact_terms(self):
        index = BM25Index(
            [
                BM25Document("a", "AI Scientist benchmark and hypothesis generation"),
                BM25Document("b", "unrelated biology protocol"),
            ]
        )
        self.assertEqual(index.search("AI Scientist", top_k=1)[0][0], "a")

    def test_gap_confidence_downgrade(self):
        review = sanitize_review(
            {
                "research_gaps": [
                    {
                        "gap": "single source gap",
                        "supporting_sources": [{"title": "A", "url": "u"}],
                        "confidence": "high",
                    }
                ]
            }
        )
        self.assertEqual(review["research_gaps"][0]["confidence"], "low")

    def test_gap_confidence_counts_distinct_sources(self):
        review = sanitize_review(
            {
                "research_gaps": [
                    {
                        "gap": "duplicate chunk gap",
                        "supporting_sources": [
                            {"title": "A", "url": "https://example.org/a", "page": 1},
                            {"title": "A", "url": "https://example.org/a", "page": 2},
                        ],
                        "confidence": "medium",
                    }
                ]
            }
        )
        self.assertEqual(review["research_gaps"][0]["confidence"], "low")
        self.assertEqual(len(review["research_gaps"][0]["supporting_sources"]), 1)

    def test_string_sources_are_renderable(self):
        review = sanitize_review(
            {
                "topic": "demo",
                "core_papers": [],
                "related_papers": [],
                "existing_conclusions": [{"claim": "claim", "supporting_sources": ["Paper A"]}],
                "research_gaps": [{"gap": "gap", "supporting_sources": ["https://example.org/a"], "confidence": "medium"}],
                "source_map": ["Paper A"],
            }
        )
        text = render_review_txt(review)
        self.assertIn("Paper A", text)
        self.assertIn("https://example.org/a", text)

    def test_demo_pipeline_outputs_json_and_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed_topics.json"
            seed.write_text(json.dumps(["AI Scientist automated scientific discovery"]), encoding="utf-8")
            settings = Settings(
                project_root=root,
                outputs_dir=root / "outputs",
                data_dir=root / "data_storage",
                pdf_dir=root / "data_storage" / "pdfs",
                knowledge_base_dir=root / "data_storage" / "knowledge_base",
                embedding_backend="hashing",
                enable_dense=False,
            )
            bootstrap(seed, limit=5, settings=settings, demo=True, skip_pdf_download=True)
            generate_review("AI Scientist automated scientific discovery", settings=settings)
            self.assertTrue((settings.outputs_dir / "search_manifest.json").exists())
            self.assertTrue((settings.outputs_dir / "papers.json").exists())
            self.assertTrue((settings.outputs_dir / "chunks.json").exists())
            self.assertTrue((settings.outputs_dir / "literature_review.json").exists())
            self.assertTrue((settings.outputs_dir / "literature_review.txt").exists())


if __name__ == "__main__":
    unittest.main()
