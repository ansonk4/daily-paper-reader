import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


class GenerateDocsMetaParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        if "fitz" not in sys.modules:
            import types

            fitz_stub = types.ModuleType("fitz")
            fitz_stub.open = lambda *args, **kwargs: None
            sys.modules["fitz"] = fitz_stub
        if "llm" not in sys.modules:
            import types

            llm_stub = types.ModuleType("llm")

            class DummyDeepSeekClient:
                def __init__(self, *args, **kwargs):
                    pass

            llm_stub.DeepSeekClient = DummyDeepSeekClient
            llm_stub.resolve_max_output_tokens = lambda default=393216: default
            sys.modules["llm"] = llm_stub

        src_path = root / "src" / "6.generate_docs.py"
        spec = importlib.util.spec_from_file_location("gen6_mod", src_path)
        cls.mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(cls.mod)

    def test_parse_meta_from_front_matter(self):
        md_path = Path("docs/201706/12/1706.03762v1-attention-is-all-you-need.md")
        item = self.mod._parse_generated_md_to_meta(str(md_path), "pid", "quick")
        self.assertEqual(item["title_en"], "Attention Is All You Need")
        self.assertTrue(item["authors"].startswith("Ashish Vaswani"))
        self.assertIn("query:transformer", item["tags"])
        self.assertEqual(item["date"], "20170612")
        self.assertIn("https://arxiv.org/pdf", item["pdf"])
        self.assertEqual(item["selection_source"], "fresh_fetch")

    def test_parse_fallback_to_legacy_meta_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "paper.md"
            path.write_text(
                "\n".join(
                    [
                        "---",
                        "selection_source: fresh_fetch",
                        "title: Legacy title",
                        "---",
                        "**Authors**: Legacy A, Legacy B",
                        "**Date**: 20260301",
                        "**PDF**: https://example.com/paper.pdf",
                        "**TLDR**: legacy tldr text",
                        "",
                        "## Abstract",
                        "abstract body",
                    ]
                ),
                encoding="utf-8",
            )
            item = self.mod._parse_generated_md_to_meta(
                str(path),
                "legacy",
                "deep",
                "cache_hint",
            )
            self.assertEqual(item["authors"], "Legacy A, Legacy B")
            self.assertEqual(item["date"], "20260301")
            self.assertEqual(item["pdf"], "https://example.com/paper.pdf")
            self.assertEqual(item["tldr"], "legacy tldr text")
            self.assertEqual(item["selection_source"], "cache_hint")

    def test_parse_source_from_front_matter(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "paper.md"
            path.write_text(
                "\n".join(
                    [
                        "---",
                        "title: Test title",
                        "source: biorxiv",
                        "selection_source: fresh_fetch",
                        "---",
                        "## Abstract",
                        "abstract body",
                    ]
                ),
                encoding="utf-8",
            )
            item = self.mod._parse_generated_md_to_meta(str(path), "pid", "quick")
            self.assertEqual(item["source"], "biorxiv")
            self.assertEqual(item["selection_source"], "fresh_fetch")

    def test_extract_sidebar_tags_hides_composite_suffix(self):
        paper = {
            "llm_score": 8.0,
            "llm_tags": [
                "query:sr:composite",
                "query:sr",
                "keyword:equation-discovery",
            ],
        }
        tags = self.mod.extract_sidebar_tags(paper)
        self.assertEqual(tags[0], ("score", "8.0"))
        self.assertIn(("query", "sr"), tags)
        self.assertIn(("query", "equation-discovery"), tags)
        self.assertNotIn(("query", "sr:composite"), tags)
        self.assertEqual(tags.count(("query", "sr")), 1)

    def test_build_markdown_content_writes_media_json_front_matter(self):
        paper = {
            "title": "Figure Test",
            "authors": ["Ada Lovelace"],
            "published": "2026-03-26T00:00:00+00:00",
            "link": "https://arxiv.org/pdf/1234.5678",
            "abstract": "abstract body",
            "source": "arxiv",
            "llm_score": 8.4,
            "relevance_score": 8.0,
            "author_score": 9.0,
            "author_rating_explanation": "Verified Stanford and OpenAI author backgrounds.",
            "author_profiles": [
                {
                    "name": "Ada Lovelace",
                    "role": "first_author",
                    "affiliation": "Stanford University",
                }
            ],
            "_figure_assets": [
                {
                    "url": "assets/figures/arxiv/1234.5678/fig-001.webp",
                    "caption": "",
                    "page": 2,
                    "index": 1,
                    "width": 1280,
                    "height": 720,
                }
            ],
            "_table_assets": [
                {
                    "url": "assets/tables/arxiv/1234.5678/table-001.webp",
                    "caption": "",
                    "page": 3,
                    "index": 1,
                    "width": 1000,
                    "height": 560,
                }
            ],
        }
        md = self.mod.build_markdown_content(paper, "quick", "", "", [])
        meta = self.mod._parse_front_matter(md)
        self.assertIn("figures_json", meta)
        self.assertIn("tables_json", meta)
        self.assertEqual(meta["score"], "8.4")
        self.assertEqual(meta["relevance_score"], "8.0")
        self.assertEqual(meta["author_score"], "9.0")
        self.assertIn("Ada Lovelace", meta["author_affiliations"])
        self.assertIn("Stanford University", meta["author_affiliations"])
        self.assertIn("Verified Stanford", meta["author_rating_explanation"])
        figures = json.loads(meta["figures_json"])
        tables = json.loads(meta["tables_json"])
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["url"], "assets/figures/arxiv/1234.5678/fig-001.webp")
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["url"], "assets/tables/arxiv/1234.5678/table-001.webp")

    def test_parse_author_score_fields_from_front_matter(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "paper.md"
            path.write_text(
                "\n".join(
                    [
                        "---",
                        "title: Test title",
                        "authors: Ada Lovelace",
                        "score: 8.4",
                        "relevance_score: 8.0",
                        "author_score: 9.0",
                        "author_affiliations: \"Ada Lovelace (first_author): OpenAI\"",
                        "author_rating_explanation: \"Verified OpenAI affiliation.\"",
                        "---",
                        "## Abstract",
                        "abstract body",
                    ]
                ),
                encoding="utf-8",
            )
            item = self.mod._parse_generated_md_to_meta(str(path), "pid", "quick")
            self.assertEqual(item["score"], "8.4")
            self.assertEqual(item["relevance_score"], "8.0")
            self.assertEqual(item["author_score"], "9.0")
            self.assertIn("OpenAI", item["author_affiliations"])
            self.assertIn("Verified OpenAI", item["author_rating_explanation"])

    def test_maybe_generate_paper_media_accepts_biorxiv(self):
        calls = []

        def fake_ensure_paper_media(**kwargs):
            calls.append(kwargs)
            return (
                [{"url": "assets/figures/biorxiv/pid/fig-001.webp"}],
                [{"url": "assets/tables/biorxiv/pid/table-001.webp"}],
            )

        original = self.mod.ensure_paper_media
        self.mod.ensure_paper_media = fake_ensure_paper_media
        try:
            figures, tables = self.mod.maybe_generate_paper_media(
                {
                    "id": "biorxiv-abc",
                    "source": "biorxiv",
                },
                docs_dir="docs",
                paper_id="202603/26/biorxiv-abc",
                pdf_url="https://www.biorxiv.org/content/test.full.pdf",
            )
        finally:
            self.mod.ensure_paper_media = original

        self.assertEqual(len(figures), 1)
        self.assertEqual(len(tables), 1)
        self.assertEqual(calls[0]["source_key"], "biorxiv")

    def test_maybe_generate_paper_figures_keeps_legacy_return(self):
        original = self.mod.ensure_paper_media
        self.mod.ensure_paper_media = lambda **kwargs: (
            [{"url": "assets/figures/arxiv/pid/fig-001.webp"}],
            [{"url": "assets/tables/arxiv/pid/table-001.webp"}],
        )
        try:
            figures = self.mod.maybe_generate_paper_figures(
                {"id": "1234.5678", "source": "arxiv"},
                docs_dir="docs",
                paper_id="1234.5678",
                pdf_url="https://arxiv.org/pdf/1234.5678",
            )
        finally:
            self.mod.ensure_paper_media = original

        self.assertEqual(figures, [{"url": "assets/figures/arxiv/pid/fig-001.webp"}])

    def test_generate_glance_prompt_requires_richer_fields(self):
        captured = {}

        def fake_call_llm_structured_json(client, messages, **kwargs):
            captured["client"] = client
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return {
                "tldr": "This overview explains the problem, method, result, and contribution in concise English for the paper page.",
                "motivation": "The paper targets a concrete research gap.",
                "method": "The method follows the approach described in the abstract.",
                "result": "The results indicate a measurable improvement.",
                "conclusion": "The work offers a reusable direction for follow-up research.",
            }

        fallback_client = object()
        original_client = self.mod.LLM_CLIENT
        original_call = self.mod.call_llm_structured_json
        self.mod.LLM_CLIENT = fallback_client
        self.mod.call_llm_structured_json = fake_call_llm_structured_json
        try:
            out = self.mod.generate_glance_overview("Title", "Abstract")
        finally:
            self.mod.LLM_CLIENT = original_client
            self.mod.call_llm_structured_json = original_call

        self.assertIn("**TLDR**", out)
        self.assertIs(captured["client"], fallback_client)
        self.assertEqual(captured["kwargs"]["max_tokens"], 16 * 1024)
        prompt = captured["messages"][2]["content"]
        self.assertIn("90-140 English words", prompt)
        self.assertIn("18-45 English words", prompt)
        self.assertIn("problem setting -> core method -> key result -> contribution/significance", prompt)
        self.assertIn("All values must be English", prompt)
        self.assertNotIn("每个字段一句话概括", prompt)

    def test_generate_glance_uses_explicit_client(self):
        explicit_client = object()
        global_client = object()
        captured = {}

        def fake_call_llm_structured_json(client, messages, **kwargs):
            captured["client"] = client
            return {
                "tldr": "This overview explains the problem, method, result, and contribution in concise English for the paper page.",
                "motivation": "The paper targets a concrete research gap.",
                "method": "The method follows the approach described in the abstract.",
                "result": "The results indicate a measurable improvement.",
                "conclusion": "The work offers a reusable direction for follow-up research.",
            }

        original_client = self.mod.LLM_CLIENT
        original_call = self.mod.call_llm_structured_json
        self.mod.LLM_CLIENT = global_client
        self.mod.call_llm_structured_json = fake_call_llm_structured_json
        try:
            out = self.mod.generate_glance_overview("Title", "Abstract", client=explicit_client)
        finally:
            self.mod.LLM_CLIENT = original_client
            self.mod.call_llm_structured_json = original_call

        self.assertIn("**TLDR**", out)
        self.assertIs(captured["client"], explicit_client)

    def test_translate_uses_16k_and_explicit_client(self):
        explicit_client = object()
        global_client = object()
        captured = {}

        def fake_call_llm_structured_json(client, messages, **kwargs):
            captured["client"] = client
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return {"title_zh": "廣東話標題", "abstract_zh": "廣東話摘要"}

        original_client = self.mod.LLM_CLIENT
        original_call = self.mod.call_llm_structured_json
        self.mod.LLM_CLIENT = global_client
        self.mod.call_llm_structured_json = fake_call_llm_structured_json
        try:
            title_zh, abstract_zh = self.mod.translate_title_and_abstract_to_zh(
                "Title",
                "Abstract",
                client=explicit_client,
            )
        finally:
            self.mod.LLM_CLIENT = original_client
            self.mod.call_llm_structured_json = original_call

        self.assertEqual(title_zh, "廣東話標題")
        self.assertEqual(abstract_zh, "廣東話摘要")
        self.assertIs(captured["client"], explicit_client)
        self.assertEqual(captured["kwargs"]["max_tokens"], 16 * 1024)
        prompt_text = "\n".join(message["content"] for message in captured["messages"])
        self.assertIn("written Cantonese", prompt_text)
        self.assertIn("Traditional Chinese characters", prompt_text)
        self.assertIn("avoid Simplified Chinese", prompt_text)


if __name__ == "__main__":
    unittest.main()
