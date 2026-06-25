import importlib.util
import pathlib
import sys
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class LlmRefineRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("llm_refine_mod_recovery", src_dir / "4.llm_refine_papers.py")

    def relevant_result(self, paper_id="p-1", score=8):
        return {
            "id": paper_id,
            "matched_requirement_index": 1,
            "evidence_en": "relevant method",
            "evidence_cn": "relevant method",
            "tldr_en": "This paper is relevant because it studies a method that matches the requested research direction and provides useful technical evidence.",
            "tldr_cn": "This paper addresses the user-requested research direction with a closely related method. It describes the core problem and technical route, provides evidence useful for relevance judgment, and can serve as a candidate for deeper reading and method comparison.",
            "title_zh": "廣東話標題",
            "motivation_cn": "The motivation directly matches the user's retrieval need and focuses on a key limitation in the target task.",
            "method_cn": "The method centers on the requested technical core and gives a clear modeling idea, algorithmic flow, or implementation strategy.",
            "result_cn": "The results indicate that the method improves performance in related tasks or experimental settings.",
            "conclusion_cn": "The conclusion suggests the direction is worth further exploration and can provide reusable ideas for the user's problem.",
            "score": score,
        }

    def test_recover_filter_results_retries_for_missing_ids(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
            {"id": "p-2", "content": "doc2"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            calls.append((tuple(item["id"] for item in batch_docs), attempt, retry_note))
            if attempt == 1:
                return [
                    self.relevant_result("p-1"),
                ]
            return [
                self.relevant_result("p-1"),
                self.relevant_result("p-2", score=7),
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=2, debug_tag="batch_test")
        self.assertEqual([item["id"] for item in out], ["p-1", "p-2"])
        self.assertEqual(len(calls), 2)
        self.assertIn("p-1, p-2", calls[1][2])
        self.assertIn("missing ids=p-2", calls[1][2])

    def test_recover_filter_results_split_batch_after_retry_exhausted(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
            {"id": "p-2", "content": "doc2"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            doc_ids = tuple(item["id"] for item in batch_docs)
            calls.append((doc_ids, attempt))
            if len(batch_docs) == 1:
                return [
                    self.relevant_result(batch_docs[0]["id"], score=6)
                ]
            return [
                self.relevant_result("p-1", score=6),
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=1, debug_tag="split_test")
        self.assertEqual([item["id"] for item in out], ["p-1", "p-2"])
        self.assertIn((("p-1",), 1), calls)
        self.assertIn((("p-2",), 1), calls)

    def test_recover_filter_results_splits_immediately_on_truncated_output(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
            {"id": "p-2", "content": "doc2"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            doc_ids = tuple(item["id"] for item in batch_docs)
            calls.append((doc_ids, attempt))
            if len(batch_docs) > 1:
                raise self.mod.FilterOutputTruncatedError("unexpected finish_reason: length")
            return [
                self.relevant_result(batch_docs[0]["id"], score=6)
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=3, debug_tag="length_test")

        self.assertEqual([item["id"] for item in out], ["p-1", "p-2"])
        self.assertEqual(calls.count((("p-1", "p-2"), 1)), 1)
        self.assertNotIn((("p-1", "p-2"), 2), calls)
        self.assertIn((("p-1",), 1), calls)
        self.assertIn((("p-2",), 1), calls)

    def test_recover_filter_results_accepts_short_best_effort_fields(self):
        docs = [
            {"id": "p-1", "content": "doc1"},
        ]
        calls = []

        def runner(batch_docs, attempt, retry_note):
            calls.append((tuple(item["id"] for item in batch_docs), attempt, retry_note))
            return [
                {
                    **self.relevant_result("p-1", score=8),
                    "tldr_cn": "Relevant, but the abstract contains limited detail.",
                    "motivation_cn": "Limited detail is available.",
                    "method_cn": "Limited detail is available.",
                    "result_cn": "Limited detail is available.",
                    "conclusion_cn": "Limited detail is available.",
                }
            ]

        out = self.mod.recover_filter_results(docs, runner, max_attempts=3, debug_tag="short_test")

        self.assertEqual(out[0]["id"], "p-1")
        self.assertEqual(out[0]["tldr_cn"], "Relevant, but the abstract contains limited detail.")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 1)
        self.assertEqual(calls[0][2], "")

    def test_call_filter_repeats_user_prompt_with_separator(self):
        captured = {}
        test_case = self

        class FakeClient:
            model = "gemini-3-flash-preview-nothinking"

            def chat_structured(self, messages, schema_name, schema, strict, allow_json_object_fallback):
                captured["messages"] = messages
                captured["schema_name"] = schema_name
                captured["schema"] = schema
                captured["strict"] = strict
                captured["allow_json_object_fallback"] = allow_json_object_fallback
                return {
                    "content": (
                        '{"results":[{"id":"p-1","matched_requirement_index":1,'
                        '"evidence_en":"ok","evidence_cn":"ok","tldr_en":"ok","tldr_cn":"ok","score":8}]}'
                    ),
                    "parsed": {
                        "results": [test_case.relevant_result("p-1")]
                    },
                    "parse_error": None,
                    "refusal": "",
                    "finish_reason": "stop",
                }

        out = self.mod.call_filter(
            client=FakeClient(),
            all_requirements=[
                {
                    "id": "req-1",
                    "query": "symbolic regression methods",
                    "tag": "query:sr",
                    "kind": "direct",
                    "description_en": "Find papers relevant to symbolic regression methods",
                }
            ],
            docs=[{"id": "p-1", "content": "Title: A\nAbstract: B"}],
            debug_dir="",
            debug_tag="prompt_test",
        )

        self.assertEqual(out[0]["id"], "p-1")
        self.assertEqual(out[0]["title_zh"], "廣東話標題")
        self.assertIn("requested technical core", out[0]["method_cn"])
        user_content = captured["messages"][1]["content"]
        self.assertEqual(captured["schema_name"], "rerank_batch")
        self.assertTrue(captured["strict"])
        self.assertTrue(captured["allow_json_object_fallback"])
        self.assertIn("Let me repeat that:", user_content)
        self.assertEqual(user_content.count("User requirements list:"), 2)
        self.assertEqual(user_content.count("Papers:"), 2)
        self.assertIn("method_cn", user_content)
        self.assertIn("title_zh", user_content)
        self.assertIn("90-140 English words", user_content)
        self.assertIn("18-45 English words", user_content)
        self.assertIn("written Cantonese", user_content)
        self.assertIn("values must be English", user_content)
        self.assertIn("length targets are guidance", user_content)
        self.assertIn("same style as a paper-page TLDR abstract", user_content)
        self.assertNotIn("<= 60 Chinese characters", user_content)
        self.assertTrue(user_content.rstrip().endswith("Output must be strict JSON only, no markdown, no fences, no extra text."))

    def test_apply_author_ratings_recomputes_final_score(self):
        class FakeRater:
            def rate_paper(self, paper):
                return {
                    "author_score": 9,
                    "author_rating_explanation": "Verified elite lab affiliation.",
                    "author_profiles": [
                        {
                            "name": "Ada",
                            "role": "first_author",
                            "affiliation": "OpenAI",
                            "confidence": "high",
                            "evidence_source": "mock",
                        }
                    ],
                }

        merged = {
            "p-1": {
                "paper_id": "p-1",
                "relevance_score": 8,
                "score": 8,
            }
        }
        self.mod.apply_author_ratings(merged, {"p-1": {"id": "p-1", "title": "T"}}, FakeRater())
        self.assertEqual(merged["p-1"]["relevance_score"], 8)
        self.assertEqual(merged["p-1"]["author_score"], 9)
        self.assertEqual(merged["p-1"]["score"], 8.4)
        self.assertEqual(merged["p-1"]["author_profiles"][0]["affiliation"], "OpenAI")


if __name__ == "__main__":
    unittest.main()
