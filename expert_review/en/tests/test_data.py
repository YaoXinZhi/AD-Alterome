"""Release checks for the anonymous English review dataset.

Run with ``python3 -m unittest discover -s tests`` from the package directory.
The optional ADALTEROME_CHINESE_SOURCE environment variable additionally checks
the untouched source file in a developer checkout; public users do not need it.
"""

import collections
import hashlib
import json
import os
import re
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
DATA_FILE = PACKAGE / "data" / "review-data.js"
MANIFEST_FILE = Path(__file__).with_name("data-integrity.json")
PREFIX = "window.REVIEW_DATA = "
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def digest(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def canonical_hash(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)
    elif isinstance(value, str):
        yield value


class EnglishDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = DATA_FILE.read_text(encoding="utf-8")
        if not cls.raw.startswith(PREFIX) or not cls.raw.endswith(";\n"):
            raise AssertionError("Invalid dataset wrapper")
        cls.data = json.loads(cls.raw[len(PREFIX):].rstrip().removesuffix(";"))
        cls.manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))

    def test_frozen_dataset_identity_and_rubric(self):
        self.assertEqual(self.data["dataset_id"], "adalterome-all15-skills-v2-20261015-rubric3-en-20261020")
        self.assertEqual(self.data["rubric_version"], "three-dim-1to4-20261015-v2")
        self.assertEqual(self.data["dataset_id"], self.manifest["dataset_id"])
        self.assertEqual(self.data["rubric_version"], self.manifest["rubric_version"])
        self.assertEqual(digest(DATA_FILE.read_bytes()), self.manifest["english_data_sha256"])

    def test_forty_five_pages_and_fifteen_questions(self):
        pages = self.data["pages"]
        self.assertEqual(len(pages), 45)
        self.assertEqual(len({page["id"] for page in pages}), 45)
        expected = {prefix + str(number): 3 for prefix in "GPH" for number in range(1, 6)}
        self.assertEqual(dict(collections.Counter(page["question_id"] for page in pages)), expected)
        kinds = collections.Counter(page["question_kind"] for page in pages)
        self.assertEqual(kinds, {"gene": 15, "term": 15, "hypothesis": 15})

    def test_original_page_order_and_english_scientific_content(self):
        pages = self.data["pages"]
        frozen = self.manifest["pages"]
        self.assertEqual([page["id"] for page in pages], [page["id"] for page in frozen])
        for page, record in zip(pages, frozen):
            with self.subTest(page=page["id"]):
                self.assertEqual(page["question_id"], record["question_id"])
                self.assertEqual(digest(page["original_en"]), record["original_en_sha256"])
                self.assertEqual(canonical_hash(page), record["page_sha256"])

    def test_no_chinese_or_translation_fields(self):
        self.assertIsNone(CJK.search(self.raw))
        self.assertFalse(any(value == "zh" or value.endswith("_zh") for value in walk(self.data)))

    def test_public_data_has_no_condition_or_private_metadata(self):
        self.assertEqual(set(self.data), {"dataset_id", "title", "schema_version", "rubric_version", "pages", "content_version"})
        expected = {"id", "question_id", "question_en", "question_kind", "reference_points", "answer_blocks", "references", "original_en"}
        forbidden = {"condition", "method", "source_answer", "source_sha256", "expert_id", "records", "ratings", "reviewer", "reviewer_name", "score", "accuracy", "evidence", "coverage"}
        for page in self.data["pages"]:
            self.assertEqual(set(page), expected)
        def keys_only(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from keys_only(item)
            elif isinstance(value, list):
                for item in value:
                    yield from keys_only(item)
        self.assertFalse(set(keys_only(self.data)) & forbidden)
        self.assertNotRegex(self.raw, r"/(?:Users|home)/[^/]+/")
        self.assertNotIn("OPENAI_API_KEY", self.raw)
        self.assertNotIn("DEEPSEEK_API_KEY", self.raw)

    def test_evidence_metadata_is_english_and_counts_are_preserved(self):
        references = [ref for page in self.data["pages"] for ref in page["references"]]
        self.assertEqual(len(references), 512)
        self.assertEqual(sum(len(ref["excerpts"]) for ref in references), 535)
        self.assertEqual({ref["status"] for ref in references}, {"available", "unavailable"})
        labels = {excerpt["source_label"] for ref in references for excerpt in ref["excerpts"]}
        self.assertEqual(labels, {"Publication excerpt", "Abstract excerpt"})
        for ref in references:
            self.assertTrue(re.fullmatch(r"\d+", ref["pmid"]))
            self.assertEqual(ref["url"], "https://pubmed.ncbi.nlm.nih.gov/" + ref["pmid"] + "/")

    def test_public_release_has_no_real_ratings_or_coordinator_map(self):
        self.assertEqual(list((PACKAGE / "ratings").glob("*.json")), [])
        self.assertEqual(list(PACKAGE.rglob("page-map*.json")), [])
        self.assertFalse((PACKAGE / "coordinator").exists())

    @unittest.skipUnless(os.environ.get("ADALTEROME_CHINESE_SOURCE"), "Optional source-file check: set ADALTEROME_CHINESE_SOURCE")
    def test_original_chinese_source_is_unchanged(self):
        source = Path(os.environ["ADALTEROME_CHINESE_SOURCE"])
        self.assertEqual(digest(source.read_bytes()), self.manifest["source_sha256"])


if __name__ == "__main__":
    unittest.main()
