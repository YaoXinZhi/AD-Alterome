"""Run from the package folder: python3 -m unittest discover -s tests -v"""

import concurrent.futures
import copy
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("review_server", SERVER_PATH)
server_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server_module)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="review server tests ")
        self.root = Path(self.temporary.name)
        self.package = self.root / "package with spaces"
        (self.package / "data").mkdir(parents=True)
        self.dataset = {"dataset_id": "fixture-v1", "rubric_version": "three-dim-1to4-20261015-v2",
                        "pages": [{"id": "R-one"}, {"id": "R-two"}, {"id": "R-three"}]}
        (self.package / "data" / "review-data.js").write_text(
            "window.REVIEW_DATA = " + json.dumps(self.dataset) + ";\n", encoding="utf-8")
        for name in ("index.html", "app.js", "styles.css"):
            (self.package / name).write_text("public fixture", encoding="utf-8")
        (self.package / ".env").write_text("private fixture", encoding="utf-8")
        (self.package / "server.py").write_text("private fixture", encoding="utf-8")
        (self.root / "coordinator").mkdir()
        (self.root / "coordinator" / "mapping.json").write_text("private fixture", encoding="utf-8")
        self.ratings = self.root / "isolated ratings"
        self.servers = []
        self.server = self.start_server()

    def tearDown(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.temporary.cleanup()

    def start_server(self):
        server = server_module.ReviewServer(self.package, self.ratings)
        server.RequestHandlerClass.log_message = lambda *args: None
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return server

    def request(self, method, path, payload=None, headers=None, body=None, server=None):
        server = server or self.server
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if method == "PUT":
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault("X-Review-App", "1")
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            content = response.read()
            response_headers = dict(response.getheaders())
            value = json.loads(content) if "application/json" in response_headers.get("Content-Type", "") and content else content
            return response.status, value, response_headers
        finally:
            connection.close()

    def payload(self, page="R-one", expert="E01", revision=0, score=None):
        return {"expert_id": expert, "page_id": page, "base_revision": revision,
                "rating": {"accuracy": score, "evidence": None, "coverage": None, "note": ""}}

    def session(self, expert="E01"):
        status, session, _ = self.request("GET", "/api/session?expert=" + expert)
        self.assertEqual(status, 200)
        return session

    def test_missing_or_invalid_dataset_fails_before_startup(self):
        data_path = self.package / "data" / "review-data.js"
        original = data_path.read_bytes()
        data_path.unlink()
        with self.assertRaises(FileNotFoundError):
            server_module.load_dataset(self.package)
        invalid_sources = (
            "not a dataset",
            "window.REVIEW_DATA = {};",
            'window.REVIEW_DATA = {"dataset_id":"d", "rubric_version":"r", "pages":[]};',
            'window.REVIEW_DATA = {"dataset_id":"d", "rubric_version":"r", "pages":[{"id":"x"},{"id":"x"}]};',
        )
        for source in invalid_sources:
            with self.subTest(source=source):
                data_path.write_text(source, encoding="utf-8")
                with self.assertRaises(server_module.InvalidInput):
                    server_module.load_dataset(self.package)
        data_path.write_bytes(original)

    def test_empty_session_and_health(self):
        status, health, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertEqual(health["page_count"], 3)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        session = self.session()
        self.assertEqual(session["records"], {})
        self.assertIsNone(session["updated_at"])
        self.assertFalse((self.ratings / "E01.json").exists())

    def test_partial_ratings_roundtrip_preserves_other_pages_and_experts(self):
        first = self.payload(score=1)
        first["rating"]["note"] = "Verify PMID 123; Unicode note: café."
        status, saved, _ = self.request("PUT", "/api/ratings", first)
        self.assertEqual(status, 200)
        self.assertTrue(saved["saved"])
        self.assertEqual(saved["record"]["revision"], 1)
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(page="R-two", score=4))[0], 200)
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(expert="E02", score=2))[0], 200)
        again = self.payload(revision=1, score=3)
        self.assertEqual(self.request("PUT", "/api/ratings", again)[0], 200)
        records = self.session()["records"]
        self.assertEqual(records["R-one"]["accuracy"], 3)
        self.assertEqual(records["R-one"]["revision"], 2)
        self.assertEqual(records["R-two"]["accuracy"], 4)
        self.assertEqual(self.session("E02")["records"]["R-one"]["accuracy"], 2)

    def test_restart_recovers_exact_disk_record(self):
        self.request("PUT", "/api/ratings", self.payload(score=4))
        original = self.session()
        server, thread = self.servers.pop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        self.server = self.start_server()
        self.assertEqual(self.session(), original)
        self.assertEqual(json.loads((self.ratings / "E01.json").read_text(encoding="utf-8")), original)
        self.assertEqual(list(self.ratings.glob("*.tmp")), [])

    def test_fifteen_to_forty_five_pages_preserves_existing_ratings(self):
        # Keep the historical dataset identifier, rubric and original opaque IDs.
        original_ids = ["R-original-{:02d}".format(index) for index in range(15)]
        appended_ids = ["R-appended-{:02d}".format(index) for index in range(30)]
        self.dataset = {
            "dataset_id": "adalterome-fifteen-20261015-rubric3-v2",
            "rubric_version": "three-dim-1to4-20261015-v2",
            "pages": [{"id": page_id} for page_id in original_ids],
        }
        data_path = self.package / "data" / "review-data.js"

        def publish_dataset():
            temporary_data = data_path.with_suffix(".tmp")
            temporary_data.write_text("window.REVIEW_DATA = " + json.dumps(self.dataset) + ";\n", encoding="utf-8")
            temporary_data.replace(data_path)

        def restart():
            server, thread = self.servers.pop()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            self.server = self.start_server()

        publish_dataset()
        restart()
        self.assertEqual(self.request("GET", "/api/health")[1]["page_count"], 15)
        for page_id, score in ((original_ids[0], 2), (original_ids[-1], 4)):
            payload = self.payload(page=page_id, score=score)
            payload["rating"]["note"] = "Rating and verification note saved before adding pages"
            self.assertEqual(self.request("PUT", "/api/ratings", payload)[0], 200)
        old_session = self.session()
        old_bytes = (self.ratings / "E01.json").read_bytes()

        self.dataset["pages"].extend({"id": page_id} for page_id in appended_ids)
        publish_dataset()
        # A running server retains its startup whitelist; the coordinator must restart it.
        self.assertEqual(self.request("GET", "/api/health")[1]["page_count"], 15)
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(page=appended_ids[0], score=3))[0], 400)
        self.assertEqual((self.ratings / "E01.json").read_bytes(), old_bytes)

        restart()
        self.assertEqual(self.request("GET", "/api/health")[1]["page_count"], 45)
        self.assertEqual(self.session(), old_session)
        self.assertEqual((self.ratings / "E01.json").read_bytes(), old_bytes)
        self.assertEqual(set(self.session()["records"]), {original_ids[0], original_ids[-1]})
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(page=appended_ids[0], score=3))[0], 200)
        expanded_session = self.session()
        for page_id, record in old_session["records"].items():
            self.assertEqual(expanded_session["records"][page_id], record)
        self.assertEqual(expanded_session["records"][appended_ids[0]]["accuracy"], 3)
        self.assertEqual(expanded_session["records"][appended_ids[0]]["revision"], 1)
        self.assertEqual(len(expanded_session["records"]), 3)
        restart()
        self.assertEqual(self.session(), expanded_session)

    def test_concurrent_different_pages_merge(self):
        barrier = threading.Barrier(3)
        def save(page):
            barrier.wait(timeout=3)
            return self.request("PUT", "/api/ratings", self.payload(page=page, score=3))[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(save, ("R-one", "R-two", "R-three")))
        self.assertEqual(results, [200, 200, 200])
        self.assertEqual(set(self.session()["records"]), {"R-one", "R-two", "R-three"})

    def test_concurrent_same_page_conflicts_then_explicit_retry(self):
        barrier = threading.Barrier(2)
        def save(score):
            barrier.wait(timeout=3)
            return self.request("PUT", "/api/ratings", self.payload(score=score))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, (1, 4)))
        self.assertEqual(sorted(result[0] for result in results), [200, 409])
        conflict = next(result[1] for result in results if result[0] == 409)
        self.assertEqual(conflict["error"], "conflict")
        self.assertEqual(conflict["record"], self.session()["records"]["R-one"])
        status, saved, _ = self.request("PUT", "/api/ratings", self.payload(revision=1, score=2))
        self.assertEqual(status, 200)
        self.assertEqual(saved["record"]["revision"], 2)

    def test_two_server_instances_share_disk_lock(self):
        second = self.start_server()
        barrier = threading.Barrier(2)
        def save(pair):
            server, page = pair
            barrier.wait(timeout=3)
            return self.request("PUT", "/api/ratings", self.payload(page=page), server=server)[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ((self.server, "R-one"), (second, "R-two"))))
        self.assertEqual(results, [200, 200])
        self.assertEqual(set(self.session()["records"]), {"R-one", "R-two"})

    def test_invalid_payloads_do_not_create_record(self):
        invalid = []
        for value in (True, False, 0, 5, -1, 1.5, "4", [], {}, float("nan"), float("inf")):
            payload = self.payload()
            payload["rating"]["accuracy"] = value
            invalid.append(payload)
        for field, value in (("expert_id", "../escape"), ("expert_id", "A" * 41),
                             ("expert_id", "invalid reviewer!"), ("expert_id", ""),
                             ("page_id", "R-unknown"), ("page_id", []),
                             ("base_revision", True), ("base_revision", -1), ("base_revision", "0")):
            payload = self.payload()
            payload[field] = value
            invalid.append(payload)
        for field, value in (("note", None), ("note", "x" * 10001)):
            payload = self.payload()
            payload["rating"][field] = value
            invalid.append(payload)
        missing = self.payload()
        del missing["rating"]["coverage"]
        invalid.append(missing)
        extra = self.payload()
        extra["rating"]["fifth_score"] = 3
        invalid.append(extra)
        for payload in invalid:
            with self.subTest(payload=str(payload)[:160]):
                status, response, _ = self.request("PUT", "/api/ratings", payload)
                self.assertEqual(status, 400)
                self.assertNotIn("saved", response)
        self.assertFalse((self.ratings / "E01.json").exists())

    def test_long_unicode_note_and_partial_scores_are_valid_drafts(self):
        payload = self.payload(score=4)
        payload["rating"]["note"] = "🧠" * 10000
        self.assertEqual(self.request("PUT", "/api/ratings", payload)[0], 200)
        self.assertEqual(self.session()["records"]["R-one"]["note"], "🧠" * 10000)
        payload = self.payload(revision=1)
        self.assertEqual(self.request("PUT", "/api/ratings", payload)[0], 200)
        self.assertEqual(self.session()["records"]["R-one"]["note"], "")

    def test_three_dimension_record_has_no_retired_fields(self):
        payload = self.payload(score=4)
        payload["rating"].update(evidence=3, coverage=2)
        status, saved, _ = self.request("PUT", "/api/ratings", payload)
        self.assertEqual(status, 200)
        self.assertEqual(set(saved["record"]), {"accuracy", "evidence", "coverage", "note", "revision", "updated_at"})
        self.assertEqual(saved["record"]["note"], "")
        self.assertEqual(self.session()["records"]["R-one"], saved["record"])

    def test_legacy_payload_and_legacy_file_require_explicit_migration(self):
        legacy = self.payload(score=3)
        legacy["rating"].update(reasoning=4, hallucination="yes")
        self.assertEqual(self.request("PUT", "/api/ratings", legacy)[0], 400)
        self.assertFalse((self.ratings / "E01.json").exists())
        self.request("PUT", "/api/ratings", self.payload(score=3))
        session = self.session()
        session["rubric_version"] = "four-dim-1to4-20261014-v1"
        session["records"]["R-one"].update(reasoning=4, hallucination="yes")
        path = self.ratings / "E01.json"
        content = (json.dumps(session, ensure_ascii=False) + "\n").encode("utf-8")
        path.write_bytes(content)
        self.assertEqual(self.request("GET", "/api/session?expert=E01")[0], 500)
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(revision=1))[0], 500)
        self.assertEqual(path.read_bytes(), content)

    def test_new_dataset_does_not_reuse_same_page_ids_with_old_scores(self):
        self.request("PUT", "/api/ratings", self.payload(score=3))
        path = self.ratings / "E01.json"
        old_bytes = path.read_bytes()
        self.dataset["dataset_id"] = "revised-answers-v2"
        (self.package / "data" / "review-data.js").write_text(
            "window.REVIEW_DATA = " + json.dumps(self.dataset) + ";\n", encoding="utf-8")
        second = self.start_server()
        self.assertEqual(self.request("GET", "/api/session?expert=E01", server=second)[0], 500)
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(revision=1), server=second)[0], 500)
        self.assertEqual(path.read_bytes(), old_bytes)

    def test_malformed_json_and_duplicate_fields_rejected(self):
        for body in (b"{}", b"[]", b"{broken", b'{"expert_id":"E01","expert_id":"E02"}', b"\xff"):
            with self.subTest(body=body):
                self.assertEqual(self.request("PUT", "/api/ratings", body=body)[0], 400)
        payload = self.payload()
        payload["rating"]["note"] = "\ud800"
        body = json.dumps(payload).encode("ascii")
        self.assertEqual(self.request("PUT", "/api/ratings", body=body)[0], 400)

    def test_corrupt_or_mismatched_record_is_never_overwritten(self):
        self.request("PUT", "/api/ratings", self.payload())
        valid = self.session()
        bad_dataset = copy.deepcopy(valid)
        bad_dataset["dataset_id"] = "another-dataset"
        bad_score = copy.deepcopy(valid)
        bad_score["records"]["R-one"]["accuracy"] = 5
        bad_revision = copy.deepcopy(valid)
        bad_revision["records"]["R-one"]["revision"] = True
        variants = [b"{broken", b"\xff\xfe", b"[]", json.dumps(bad_dataset).encode(),
                    json.dumps(bad_score).encode(), json.dumps(bad_revision).encode()]
        path = self.ratings / "E01.json"
        for data in variants:
            with self.subTest(data=data[:60]):
                path.write_bytes(data)
                self.assertEqual(self.request("GET", "/api/session?expert=E01")[0], 500)
                status, response, _ = self.request("PUT", "/api/ratings", self.payload(revision=1))
                self.assertEqual(status, 500)
                self.assertNotIn("saved", response)
                self.assertEqual(path.read_bytes(), data)

    def test_replace_failure_keeps_previous_file_and_returns_error(self):
        self.request("PUT", "/api/ratings", self.payload(score=2))
        path = self.ratings / "E01.json"
        original = path.read_bytes()
        with mock.patch.object(server_module.os, "replace", side_effect=OSError("simulated disk failure")):
            status, response, _ = self.request("PUT", "/api/ratings", self.payload(revision=1, score=4))
        self.assertEqual(status, 500)
        self.assertNotIn("saved", response)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.ratings.glob("*.tmp")), [])
        self.assertEqual(self.session()["records"]["R-one"]["revision"], 1)

    def test_unwritable_ratings_directory_does_not_claim_success(self):
        self.ratings.write_text("a file where a directory is required", encoding="utf-8")
        status, response, _ = self.request("PUT", "/api/ratings", self.payload())
        self.assertEqual(status, 500)
        self.assertNotIn("saved", response)

    def test_only_allowlisted_public_assets_are_served(self):
        for path in ("/", "/index.html", "/app.js", "/styles.css", "/data/review-data.js"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 200)
        self.request("PUT", "/api/ratings", self.payload())
        for path in ("/ratings/E01.json", "/ratings/", "/.env", "/server.py", "/README.md",
                     "/coordinator/mapping.json", "/../coordinator/mapping.json",
                     "/%2e%2e/coordinator/mapping.json", "/data/../../.env", "/data/", "/missing",
                     "/index.html%00", "/%2f..%2f.env", "/api/ratings/E01.json"):
            with self.subTest(path=path):
                status, body, _ = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertEqual(body, {"error": "not_found"})

    def test_static_symlink_cannot_escape_package(self):
        asset = self.package / "app.js"
        asset.unlink()
        try:
            asset.symlink_to(self.root / "coordinator" / "mapping.json")
        except OSError:
            self.skipTest("This environment does not permit symbolic links")
        self.assertEqual(self.request("GET", "/app.js")[0], 404)
        asset.unlink()
        asset.symlink_to(self.package / ".env")
        self.assertEqual(self.request("GET", "/app.js")[0], 404)

    def test_host_origin_and_custom_header_checks(self):
        port = self.server.server_port
        forbidden = [{"Host": "attacker.example:" + str(port)}, {"Host": "127.0.0.1:1"},
                     {"Origin": "https://attacker.example"}, {"Origin": "null"},
                     {"Origin": "http://127.0.0.1:1"}, {"Origin": "http://localhost:" + str(port) + "/"},
                     {"Sec-Fetch-Site": "cross-site"}, {"X-Review-App": "0"}]
        for headers in forbidden:
            with self.subTest(headers=headers):
                status, body, response_headers = self.request("PUT", "/api/ratings", self.payload(), headers=headers)
                self.assertEqual(status, 403)
                self.assertNotIn("saved", body)
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        headers = {"Host": "localhost:" + str(port), "Origin": "http://localhost:" + str(port)}
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(), headers=headers)[0], 200)
        self.assertEqual(self.request("OPTIONS", "/api/ratings")[0], 405)

    def test_invalid_query_content_type_and_size(self):
        for query in ("", "?expert=", "?expert=E01&expert=E02", "?expert=E01&extra=1", "?expert=..%2FE01"):
            self.assertEqual(self.request("GET", "/api/session" + query)[0], 400)
        self.assertEqual(self.request("PUT", "/api/ratings", self.payload(), headers={"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.request("PUT", "/api/ratings", body=b"x" * (server_module.MAX_BODY_BYTES + 1))[0], 413)
        self.assertEqual(self.request("PUT", "/api/unknown", self.payload())[0], 404)


if __name__ == "__main__":
    unittest.main()
