import importlib.util
import io
import pathlib
import tarfile
import tempfile
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class FakeResponse:
    status_code = 200

    def __init__(self, payload, content=b""):
        self.payload = payload
        self.content = content

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if url == "https://api.openalex.org/works":
            return FakeResponse(
                {
                    "results": [
                        {
                            "title": "A Test Paper",
                            "publication_year": 2026,
                            "authorships": [
                                {
                                    "author": {"display_name": "Alice First", "id": "https://openalex.org/A1"},
                                    "institutions": [{"display_name": "Stanford University"}],
                                },
                                {
                                    "author": {"display_name": "Bob Last", "id": "https://openalex.org/A2"},
                                    "institutions": [{"display_name": "OpenAI"}],
                                },
                            ],
                        }
                    ]
                }
            )
        if url == "https://openalex.org/A1":
            return FakeResponse({"works_count": 12, "cited_by_count": 345})
        if url == "https://openalex.org/A2":
            return FakeResponse({"works_count": 40, "cited_by_count": 1200})
        if url == "https://api.semanticscholar.org/graph/v1/paper/search":
            return FakeResponse(
                {
                    "data": [
                        {
                            "title": "A Test Paper",
                            "year": 2026,
                            "authors": [
                                {
                                    "name": "Alice First",
                                    "authorId": "s1",
                                    "affiliations": ["Stanford AI Lab"],
                                    "paperCount": 20,
                                    "citationCount": 500,
                                },
                                {
                                    "name": "Bob Last",
                                    "authorId": "s2",
                                    "affiliations": ["OpenAI"],
                                    "paperCount": 60,
                                    "citationCount": 1600,
                                },
                            ],
                        }
                    ]
                }
            )
        return FakeResponse({})


class FakeClient:
    def __init__(self):
        self.messages = []

    def chat_structured(self, messages, schema_name, schema, strict, allow_json_object_fallback):
        self.messages = messages
        return {
            "parsed": {
                "author_score": 9.0,
                "author_rating_explanation": "Focus authors have verified affiliations at Stanford University and OpenAI.",
                "author_profiles": [
                    {
                        "name": "Alice First",
                        "role": "first_author",
                        "affiliation": "Stanford University",
                        "citation_hints": "Semantic Scholar citation_count=500",
                        "confidence": "high",
                        "evidence_source": "openalex, semantic_scholar",
                    },
                    {
                        "name": "Bob Last",
                        "role": "last_author",
                        "affiliation": "OpenAI",
                        "citation_hints": "Semantic Scholar citation_count=1600",
                        "confidence": "high",
                        "evidence_source": "openalex, semantic_scholar",
                    },
                ],
            },
            "parse_error": None,
            "refusal": "",
        }


class FakeSchemaWarningClient:
    def chat_structured(self, messages, schema_name, schema, strict, allow_json_object_fallback):
        return {
            "parsed": {
                "author_score": 8.5,
                "author_rating_explanation": "Verified CUHK and Tsinghua affiliations.",
                "extra_model_note": "non-schema field",
            },
            "parse_error": ValueError("JSON schema validation failed: unexpected fields"),
            "refusal": "",
        }


class FakeMissingExplanationClient:
    def chat_structured(self, messages, schema_name, schema, strict, allow_json_object_fallback):
        return {
            "parsed": {
                "author_score": 7.0,
                "author_profiles": [
                    {
                        "name": "Seth Dobrin",
                        "role": "first_author",
                        "affiliation": "ARYA Labs PBC",
                        "citation_hints": "",
                        "confidence": "medium",
                        "evidence_source": "arxiv_source",
                    }
                ],
            },
            "parse_error": None,
            "refusal": "",
        }


class FakeGenericExplanationClient:
    def chat_structured(self, messages, schema_name, schema, strict, allow_json_object_fallback):
        return {
            "parsed": {
                "author_score": 7.0,
                "author_rating_explanation": "Author rating synthesized from available public metadata.",
                "author_profiles": [
                    {
                        "name": "Seth Dobrin",
                        "role": "first_author",
                        "affiliation": "ARYA Labs PBC",
                        "citation_hints": "",
                        "confidence": "medium",
                        "evidence_source": "arxiv_source",
                    }
                ],
            },
            "parse_error": None,
            "refusal": "",
        }


def make_source_tar(tex_text):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = tex_text.encode("utf-8")
        info = tarfile.TarInfo("main.tex")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeArxivSourceSession:
    def __init__(self):
        self.source = make_source_tar(
            r"""
            \title{A Test Paper}
            \author{
              \IEEEauthorblockN{
                Alice First\IEEEauthorrefmark{1},
                Bob Last\IEEEauthorrefmark{2}
              }
              \IEEEauthorblockA{\IEEEauthorrefmark{1}Stanford AI Lab, Stanford University}
              \IEEEauthorblockA{\IEEEauthorrefmark{2}OpenAI}
            }
            """
        )

    def get(self, url, params=None, timeout=None):
        if url == "https://arxiv.org/e-print/2606.17114":
            return FakeResponse({}, self.source)
        return FakeResponse({})


class AuthorProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.mod = _load_module("author_profile_mod", root / "src" / "author_profile.py")

    def test_select_focus_authors_includes_first_cofirst_and_last(self):
        paper = {
            "authors": [
                {"name": "Alice First", "equal_contribution": True},
                {"name": "Bea Co", "note": "equal contribution"},
                {"name": "Chen Middle"},
                {"name": "Dana Last"},
            ]
        }
        selected = self.mod.select_focus_authors(paper)
        self.assertEqual(
            [(item["name"], item["role"]) for item in selected],
            [
                ("Alice First", "first_author"),
                ("Bea Co", "co_first_author"),
                ("Dana Last", "last_author"),
            ],
        )

    def test_select_focus_authors_accepts_paper_level_cofirst_names(self):
        paper = {
            "authors": ["Alice First", "Bea Co", "Dana Last"],
            "co_first_authors": ["Bea Co"],
        }
        selected = self.mod.select_focus_authors(paper)
        self.assertEqual([item["name"] for item in selected], ["Alice First", "Bea Co", "Dana Last"])

    def test_weighted_final_score_is_clamped(self):
        self.assertEqual(self.mod.combine_relevance_author_scores(8, 9), 8.4)
        self.assertEqual(self.mod.combine_relevance_author_scores(20, 20), 10.0)
        self.assertEqual(self.mod.combine_relevance_author_scores(-2, -1), 0.0)

    def test_author_rater_uses_public_metadata_and_llm(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            client = FakeClient()
            rater = self.mod.AuthorProfileRater(
                cache_dir=cache_dir,
                client=client,
                session=FakeSession(),
                timeout=1,
            )
            rating = rater.rate_paper(
                {
                    "id": "p1",
                    "title": "A Test Paper",
                    "published": "2026-01-01",
                    "authors": ["Alice First", "Bob Last"],
                }
            )

        self.assertEqual(rating["author_score"], 9.0)
        self.assertIn("Stanford", rating["author_rating_explanation"])
        self.assertIn("OpenAI", client.messages[1]["content"])
        self.assertIn('"author_score"', client.messages[1]["content"])
        self.assertIn('"author_rating_explanation"', client.messages[1]["content"])
        self.assertIn('"author_profiles"', client.messages[1]["content"])
        self.assertIn("no extra top-level keys", client.messages[1]["content"])
        self.assertIn("Score bands are ranges, not ordinal list numbers", client.messages[1]["content"])
        self.assertIn("Schools not included in the top or mid-tier bands above", client.messages[1]["content"])
        self.assertIn("must not receive 6+", client.messages[1]["content"])
        self.assertNotIn('"group"', client.messages[1]["content"])
        self.assertNotIn('"school"', client.messages[1]["content"])
        self.assertNotIn('"company"', client.messages[1]["content"])
        self.assertNotIn("group", rating["author_profiles"][0])
        self.assertNotIn("school", rating["author_profiles"][0])
        self.assertNotIn("company", rating["author_profiles"][0])

    def test_author_rater_accepts_usable_payload_with_schema_warning(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            rater = self.mod.AuthorProfileRater(
                cache_dir=cache_dir,
                client=FakeSchemaWarningClient(),
                session=FakeSession(),
                timeout=1,
            )
            rating = rater.rate_paper(
                {
                    "id": "p-schema-warning",
                    "title": "A Test Paper",
                    "published": "2026-01-01",
                    "authors": ["Alice First", "Bob Last"],
                    "author_affiliations": "Alice First: CUHK; Bob Last: Tsinghua University",
                }
            )

        self.assertEqual(rating["author_score"], 8.5)
        self.assertEqual(rating["author_rating_status"], "rated")
        self.assertIn("CUHK", rating["author_rating_explanation"])
        self.assertTrue(rating["author_profiles"])

    def test_author_rater_rejects_missing_rating_explanation(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            rater = self.mod.AuthorProfileRater(
                cache_dir=cache_dir,
                client=FakeMissingExplanationClient(),
                session=FakeSession(),
                timeout=1,
            )
            rating = rater._call_llm_rating(
                {"id": "p-weak", "title": "Weak Lab Paper", "published": "2026-01-01"},
                [
                    {
                        "name": "Seth Dobrin",
                        "role": "first_author",
                        "affiliation": "ARYA Labs PBC",
                        "citation_hints": "",
                        "confidence": "medium",
                        "evidence_source": "arxiv_source",
                    }
                ],
            )

        self.assertEqual(rating["author_score"], 4.5)
        self.assertEqual(rating["author_rating_status"], "fallback")
        self.assertIn("low-confidence", rating["author_rating_explanation"])

    def test_author_rater_rejects_generic_rating_explanation(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            rater = self.mod.AuthorProfileRater(
                cache_dir=cache_dir,
                client=FakeGenericExplanationClient(),
                session=FakeSession(),
                timeout=1,
            )
            rating = rater._call_llm_rating(
                {"id": "p-weak", "title": "Weak Lab Paper", "published": "2026-01-01"},
                [
                    {
                        "name": "Seth Dobrin",
                        "role": "first_author",
                        "affiliation": "ARYA Labs PBC",
                        "citation_hints": "",
                        "confidence": "medium",
                        "evidence_source": "arxiv_source",
                    }
                ],
            )

        self.assertEqual(rating["author_score"], 4.5)
        self.assertEqual(rating["author_rating_status"], "fallback")

    def test_author_rating_cache_key_includes_rubric_version(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            rater = self.mod.AuthorProfileRater(cache_dir=cache_dir, session=FakeSession(), timeout=1)
            key = rater._rating_key(
                {"id": "p1", "title": "A Test Paper", "published": "2026-01-01"},
                [{"name": "Alice First"}, {"name": "Bob Last"}],
            )

        self.assertTrue(key.startswith(self.mod.AUTHOR_RATING_RUBRIC_VERSION + "|"))

    def test_author_rater_prefers_paper_author_row_from_arxiv_source(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            rater = self.mod.AuthorProfileRater(
                cache_dir=cache_dir,
                client=None,
                session=FakeArxivSourceSession(),
                timeout=1,
            )
            profile = rater.fetch_author_profile(
                {
                    "id": "2606.17114v1",
                    "title": "A Test Paper",
                    "published": "2026-01-01",
                    "authors": ["Alice First", "Bob Last"],
                },
                {"name": "Alice First", "role": "first_author", "index": 0, "metadata": {}},
            )

        self.assertEqual(profile["affiliation"], "Stanford AI Lab, Stanford University")
        self.assertIn("arxiv_source", profile["evidence_source"])

    def test_author_rater_uses_local_author_affiliations_before_search_metadata(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            rater = self.mod.AuthorProfileRater(
                cache_dir=cache_dir,
                client=None,
                session=FakeSession(),
                timeout=1,
            )
            profile = rater.fetch_author_profile(
                {
                    "id": "p-local",
                    "title": "A Local Paper",
                    "published": "2026-01-01",
                    "authors": ["Alice First", "Bob Last"],
                    "author_affiliations": "Alice First (first_author): Korea AI Safety Institute; Bob Last (last_author): Singapore AI Safety Institute",
                },
                {"name": "Alice First", "role": "first_author", "index": 0, "metadata": {}},
            )

        self.assertTrue(profile["affiliation"].startswith("Korea AI Safety Institute"))
        self.assertEqual(profile["evidence_source"].split(", ")[0], "paper_author_row")


if __name__ == "__main__":
    unittest.main()
