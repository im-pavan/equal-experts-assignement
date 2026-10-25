"""Small HTTP API that lists a GitHub user's public Gists.

    GET /<user>?page=1&per_page=30  ->  JSON list of the user's public gists
    GET /healthz                    ->  liveness probe
"""
import os
import re
import threading
import time

import requests
from flask import Flask, jsonify, request

GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "60"))
TIMEOUT = float(os.environ.get("GITHUB_TIMEOUT_SECONDS", "10"))
# GitHub usernames: alphanumerics and single hyphens, max 39 chars.
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


class TTLCache:
    """Tiny thread-safe in-memory cache."""

    def __init__(self, ttl):
        self.ttl, self._data, self._lock = ttl, {}, threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            self._data.pop(key, None)
            return None

    def set(self, key, value):
        if self.ttl <= 0:
            return
        with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, value)


def _int_arg(name, default, lo, hi):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not raw.isdigit() or not lo <= int(raw) <= hi:
        raise ValueError(f"'{name}' must be an integer between {lo} and {hi}")
    return int(raw)


def _simplify(gist):
    return {
        "id": gist["id"],
        "description": gist.get("description"),
        "url": gist["html_url"],
        "created_at": gist["created_at"],
        "updated_at": gist["updated_at"],
        "files": [
            {"name": n, "language": f.get("language"), "size": f.get("size"),
             "raw_url": f.get("raw_url")}
            for n, f in gist.get("files", {}).items()
        ],
    }


def create_app():
    app = Flask(__name__)
    cache = TTLCache(CACHE_TTL)
    session = requests.Session()
    session.headers.update({"Accept": "application/vnd.github+json",
                            "User-Agent": "gist-api"})
    if os.environ.get("GITHUB_TOKEN"):  # optional: raises GitHub rate limit
        session.headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

    def err(status, msg):
        return jsonify(error=msg), status

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/<user>")
    def gists(user):
        if not USERNAME_RE.match(user):
            return err(400, "invalid GitHub username")
        try:
            page = _int_arg("page", 1, 1, 10**6)
            per_page = _int_arg("per_page", 30, 1, 100)
        except ValueError as e:
            return err(400, str(e))

        key = (user.lower(), page, per_page)
        body = cache.get(key)
        if body is None:
            try:
                r = session.get(f"{GITHUB_API}/users/{user}/gists",
                                params={"page": page, "per_page": per_page},
                                timeout=TIMEOUT)
            except requests.RequestException:
                return err(502, "could not reach GitHub")
            if r.status_code == 404:
                return err(404, f"user '{user}' not found")
            if r.status_code in (403, 429):
                return err(503, "GitHub rate limit reached, try again later")
            if not r.ok:
                return err(502, f"unexpected response from GitHub ({r.status_code})")
            body = {"user": user, "page": page, "per_page": per_page,
                    "has_next_page": 'rel="next"' in r.headers.get("Link", ""),
                    "gists": [_simplify(g) for g in r.json()]}
            cache.set(key, body)
        return jsonify(body)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
