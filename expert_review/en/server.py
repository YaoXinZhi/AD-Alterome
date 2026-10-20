#!/usr/bin/env python3
"""Dependency-free, loopback-only server for the expert review package."""

import argparse
import contextlib
import datetime
import http.server
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import urllib.parse
import webbrowser

if os.name == "nt":
    import msvcrt
else:
    import fcntl


MAX_BODY_BYTES = 65536
MAX_NOTE_CHARS = 10000
EXPERT_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,40}\Z")
SCORE_KEYS = ("accuracy", "evidence", "coverage")
RATING_KEYS = set(SCORE_KEYS) | {"note"}
RECORD_KEYS = RATING_KEYS | {"revision", "updated_at"}
SESSION_KEYS = {"dataset_id", "rubric_version", "expert_id", "records", "updated_at"}
PUBLIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/data/review-data.js": ("data/review-data.js", "text/javascript; charset=utf-8"),
}


class InvalidInput(ValueError):
    pass


class StorageError(Exception):
    pass


class Conflict(Exception):
    def __init__(self, record):
        self.record = record


def _no_constant(value):
    raise InvalidInput("JSON must not contain NaN or Infinity.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput("JSON contains duplicate fields.")
        result[key] = value
    return result


def parse_json(text):
    try:
        return json.loads(text, parse_constant=_no_constant, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise InvalidInput("Invalid JSON format.") from exc


def validate_expert(expert_id):
    if not isinstance(expert_id, str) or not EXPERT_PATTERN.fullmatch(expert_id):
        raise InvalidInput("Reviewer ID must contain 1–40 letters, digits, underscores, or hyphens.")
    return expert_id


def validate_rating(rating):
    if not isinstance(rating, dict) or set(rating) != RATING_KEYS:
        raise InvalidInput("A rating must contain exactly accuracy, evidence, coverage, and note.")
    for key in SCORE_KEYS:
        value = rating[key]
        if value is not None and (type(value) is not int or not 1 <= value <= 4):
            raise InvalidInput("Scores must be integers from 1 to 4, or null.")
    note = rating["note"]
    if not isinstance(note, str) or len(note) > MAX_NOTE_CHARS:
        raise InvalidInput("Comments must be text with at most 10,000 characters.")
    # Reject lone Unicode surrogates before encoding the on-disk UTF-8 record.
    try:
        note.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidInput("Comments contain invalid Unicode characters.") from exc
    return dict(rating)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")


def load_dataset(package_dir):
    source = (Path(package_dir) / "data" / "review-data.js").read_text(encoding="utf-8")
    match = re.fullmatch(r"\s*window\.REVIEW_DATA\s*=\s*(\{.*\})\s*;?\s*", source, re.DOTALL)
    if not match:
        raise InvalidInput("Invalid data/review-data.js format.")
    data = parse_json(match.group(1))
    for key in ("dataset_id", "rubric_version"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise InvalidInput("Review data is missing " + key + ".")
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise InvalidInput("Review data contains no pages.")
    page_ids = [page.get("id") if isinstance(page, dict) else None for page in pages]
    if any(not isinstance(pid, str) or not pid for pid in page_ids) or len(set(page_ids)) != len(page_ids):
        raise InvalidInput("Review data contains invalid or duplicate page IDs.")
    return data


class RatingsStore:
    """Each update rereads disk under a per-expert thread AND process lock."""

    def __init__(self, ratings_dir, dataset):
        self.ratings_dir = Path(ratings_dir).resolve()
        self.dataset_id = dataset["dataset_id"]
        self.rubric_version = dataset["rubric_version"]
        self.page_ids = frozenset(page["id"] for page in dataset["pages"])
        self._locks = {}
        self._locks_guard = threading.Lock()

    def _empty(self, expert_id):
        return {"dataset_id": self.dataset_id, "rubric_version": self.rubric_version,
                "expert_id": expert_id, "records": {}, "updated_at": None}

    @contextlib.contextmanager
    def _locked(self, expert_id):
        validate_expert(expert_id)
        with self._locks_guard:
            lock = self._locks.setdefault(expert_id, threading.Lock())
        with lock:
            try:
                self.ratings_dir.mkdir(parents=True, exist_ok=True)
                lock_path = self.ratings_dir / ("." + expert_id + ".lock")
                if lock_path.is_symlink():
                    raise StorageError("Invalid rating lock file; no ratings were changed.")
                with open(lock_path, "a+b") as handle:
                    if os.name == "nt":
                        if handle.seek(0, os.SEEK_END) == 0:
                            handle.write(b"\0")
                            handle.flush()
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        if os.name == "nt":
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError as exc:
                raise StorageError("Cannot access rating files; check folder permissions and available disk space.") from exc

    def _read(self, expert_id):
        path = self.ratings_dir / (expert_id + ".json")
        if path.is_symlink():
            raise StorageError("The rating file is a symbolic link; it was neither read nor changed.")
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._empty(expert_id)
        try:
            session = parse_json(content)
            if not isinstance(session, dict) or set(session) != SESSION_KEYS:
                raise InvalidInput("Invalid rating file structure.")
            if (session["dataset_id"] != self.dataset_id or
                    session["rubric_version"] != self.rubric_version or
                    session["expert_id"] != expert_id):
                raise InvalidInput("The rating file has a different dataset, rubric, or reviewer ID.")
            if not isinstance(session["records"], dict):
                raise InvalidInput("Invalid rating record structure.")
            if session["updated_at"] is not None and not isinstance(session["updated_at"], str):
                raise InvalidInput("Invalid rating file timestamp.")
            for page_id, record in session["records"].items():
                if page_id not in self.page_ids or not isinstance(record, dict) or set(record) != RECORD_KEYS:
                    raise InvalidInput("The rating file contains an invalid page or record.")
                validate_rating({key: record[key] for key in RATING_KEYS})
                if type(record["revision"]) is not int or record["revision"] < 1:
                    raise InvalidInput("Invalid rating revision.")
                if not isinstance(record["updated_at"], str) or not record["updated_at"]:
                    raise InvalidInput("Invalid rating record timestamp.")
            return session
        except (InvalidInput, UnicodeError) as exc:
            raise StorageError("The existing rating file is damaged or does not match the current dataset, three-dimension rubric, or reviewer. The original was preserved without changes. Ask the coordinator to back it up and check compatibility.") from exc

    def read_session(self, expert_id):
        with self._locked(expert_id):
            try:
                return self._read(expert_id)
            except UnicodeError as exc:
                raise StorageError("The existing rating file cannot be decoded. The original was preserved without changes.") from exc

    def _atomic_write(self, expert_id, session):
        content = (json.dumps(session, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.ratings_dir,
                                             prefix="." + expert_id + ".", suffix=".tmp", delete=False) as handle:
                temp_path = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.ratings_dir / (expert_id + ".json"))
            if os.name != "nt":
                directory_fd = os.open(self.ratings_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

    def save_rating(self, expert_id, page_id, base_revision, rating):
        validate_expert(expert_id)
        if not isinstance(page_id, str) or page_id not in self.page_ids:
            raise InvalidInput("Unknown review page.")
        if type(base_revision) is not int or base_revision < 0:
            raise InvalidInput("base_revision must be a nonnegative integer.")
        rating = validate_rating(rating)
        with self._locked(expert_id):
            try:
                session = self._read(expert_id)
            except UnicodeError as exc:
                raise StorageError("The existing rating file cannot be decoded. The original was preserved without changes.") from exc
            previous = session["records"].get(page_id)
            revision = previous["revision"] if previous else 0
            if revision != base_revision:
                raise Conflict(previous)
            now = utc_now()
            record = dict(rating, revision=revision + 1, updated_at=now)
            session["records"][page_id] = record
            session["updated_at"] = now
            self._atomic_write(expert_id, session)
            return record


class ReviewServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, package_dir, ratings_dir=None, port=0):
        self.package_dir = Path(package_dir).resolve()
        self.dataset = load_dataset(self.package_dir)
        self.store = RatingsStore(ratings_dir or self.package_dir / "ratings", self.dataset)
        super().__init__(("127.0.0.1", port), ReviewHandler)


class ReviewHandler(http.server.BaseHTTPRequestHandler):
    server_version = "LocalReview/1"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def _headers(self, status, content_type, length):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()

    def _json(self, status, value):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _local_request(self):
        port = self.server.server_port
        hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port)}
        if port == 80:
            hosts |= {"127.0.0.1", "localhost"}
        host_headers = self.headers.get_all("Host", [])
        if len(host_headers) != 1 or host_headers[0].lower() not in hosts:
            self._json(403, {"error": "forbidden_host", "message": "Only loopback addresses are allowed."})
            return False
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0] not in {"http://" + host for host in hosts}):
            self._json(403, {"error": "forbidden_origin", "message": "Requests must originate from the local review page."})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self._json(403, {"error": "forbidden_origin", "message": "Cross-site requests are not allowed."})
            return False
        return True

    def _target(self):
        if not self.path.startswith("/") or self.path.startswith("//") or "#" in self.path:
            raise InvalidInput("Invalid request path.")
        try:
            return urllib.parse.urlsplit(self.path)
        except ValueError as exc:
            raise InvalidInput("Invalid request path.") from exc

    def _handle_error(self, exc):
        if isinstance(exc, InvalidInput):
            self._json(400, {"error": "invalid_input", "message": str(exc)})
        elif isinstance(exc, Conflict):
            self._json(409, {"error": "conflict", "record": exc.record})
        else:
            self.log_error("Storage error: %s", exc)
            message = str(exc) if isinstance(exc, StorageError) else "Disk access failed; saving has not been confirmed."
            self._json(500, {"error": "storage_error", "message": message})

    def do_GET(self):
        if not self._local_request():
            return
        try:
            target = self._target()
            if target.path == "/api/health":
                self._json(200, {"ok": True, "dataset_id": self.server.store.dataset_id,
                                 "rubric_version": self.server.store.rubric_version,
                                 "page_count": len(self.server.store.page_ids)})
            elif target.path == "/api/session":
                query = urllib.parse.parse_qs(target.query, keep_blank_values=True)
                if set(query) != {"expert"} or len(query["expert"]) != 1:
                    raise InvalidInput("Provide exactly one expert ID.")
                expert_id = validate_expert(query["expert"][0])
                self._json(200, self.server.store.read_session(expert_id))
            elif target.path in PUBLIC_ASSETS:
                relative_path, mime = PUBLIC_ASSETS[target.path]
                path = self.server.package_dir / relative_path
                # Public names cannot be redirected to private files, even within the package.
                if path.resolve() != path:
                    self._json(404, {"error": "not_found"})
                    return
                try:
                    body = path.read_bytes()
                except FileNotFoundError:
                    self._json(404, {"error": "not_found"})
                    return
                self._headers(200, mime, len(body))
                if self.command != "HEAD":
                    self.wfile.write(body)
            else:
                self._json(404, {"error": "not_found"})
        except (InvalidInput, StorageError, OSError) as exc:
            self._handle_error(exc)

    def do_HEAD(self):
        self.do_GET()

    def do_PUT(self):
        if not self._local_request():
            return
        try:
            target = self._target()
            if target.path != "/api/ratings" or target.query:
                self._json(404, {"error": "not_found"})
                return
            if self.headers.get_all("X-Review-App", []) != ["1"]:
                self._json(403, {"error": "missing_app_header"})
                return
            if self.headers.get_content_type() != "application/json":
                raise InvalidInput("Requests must use application/json.")
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") is not None or len(lengths) != 1 or not lengths[0].isdigit():
                raise InvalidInput("Requests must provide one valid Content-Length header.")
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY_BYTES:
                self._json(413, {"error": "body_too_large", "message": "Request size must be from 1 to 65,536 bytes."})
                return
            body = self.rfile.read(length)
            if len(body) != length:
                raise InvalidInput("Incomplete request body.")
            try:
                payload = parse_json(body.decode("utf-8"))
            except UnicodeError as exc:
                raise InvalidInput("Requests must contain UTF-8 JSON.") from exc
            if not isinstance(payload, dict) or set(payload) != {"expert_id", "page_id", "base_revision", "rating"}:
                raise InvalidInput("Invalid save request fields.")
            record = self.server.store.save_rating(**payload)
            self._json(200, {"saved": True, "record": record, "expert_id": payload["expert_id"], "page_id": payload["page_id"]})
        except (InvalidInput, Conflict, StorageError, OSError) as exc:
            self._handle_error(exc)

    def do_OPTIONS(self):
        if self._local_request():
            self._json(405, {"error": "method_not_allowed"})

    def do_POST(self):
        if self._local_request():
            self._json(405, {"error": "method_not_allowed"})

    do_DELETE = do_POST
    do_PATCH = do_POST


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local AD-Alterome expert review. Uses only the Python 3 standard library.")
    parser.add_argument("--port", type=int, default=0, help="Local port; 0 (default) selects an available port")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically")
    parser.add_argument("--ratings-dir", type=Path, help="Rating directory; defaults to the ratings folder in this package")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535.")
    try:
        server = ReviewServer(Path(__file__).resolve().parent, args.ratings_dir, args.port)
    except (OSError, InvalidInput) as exc:
        print("Cannot start the review page: " + str(exc), file=sys.stderr)
        return 1
    url = "http://127.0.0.1:" + str(server.server_port) + "/"
    print("\nAD-Alterome expert review is running", flush=True)
    print("Page: " + url, flush=True)
    print("Rating folder: " + str(server.store.ratings_dir), flush=True)
    print("Keep this window open. Confirm that the page shows Saved before pressing Ctrl+C to stop.\n", flush=True)
    if not args.no_open:
        def open_browser():
            try:
                if not webbrowser.open(url):
                    print("The browser did not open automatically. Visit the local address shown above.", flush=True)
            except Exception:
                print("The browser did not open automatically. Visit the local address shown above.", flush=True)
        threading.Thread(target=open_browser, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nReview server stopped. Ratings already saved to disk are retained.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
