import os

import pytest
import requests

import app as app_module

SAMPLE = [{
    "id": "abc123", "description": "hello", "html_url": "https://gist.github.com/abc123",
    "created_at": "2020-01-01T00:00:00Z", "updated_at": "2020-01-02T00:00:00Z",
    "files": {"a.py": {"language": "Python", "size": 5, "raw_url": "https://raw/a.py"}},
}]


class FakeResp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code, self._data, self.headers = status, data, headers or {}
        self.ok = status < 400

    def json(self):
        return self._data


@pytest.fixture
def client(monkeypatch):
    calls = []

    def fake_get(self, url, **kw):
        calls.append((url, kw))
        user = url.split("/users/")[1].split("/")[0]
        if user == "ghost":
            return FakeResp(404)
        if user == "limited":
            return FakeResp(403)
        if user == "down":
            raise requests.ConnectionError()
        return FakeResp(200, SAMPLE, {"Link": '<x>; rel="next"'})

    monkeypatch.setattr(requests.Session, "get", fake_get)
    c = app_module.create_app().test_client()
    c.calls = calls
    return c


def test_lists_gists(client):
    r = client.get("/octocat")
    assert r.status_code == 200
    body = r.get_json()
    assert body["user"] == "octocat" and body["has_next_page"] is True
    assert body["gists"][0]["id"] == "abc123"
    assert body["gists"][0]["files"][0]["name"] == "a.py"


def test_pagination_params_forwarded(client):
    client.get("/octocat?page=2&per_page=5")
    assert client.calls[0][1]["params"] == {"page": 2, "per_page": 5}


def test_results_are_cached(client):
    client.get("/octocat"); client.get("/octocat")
    assert len(client.calls) == 1


@pytest.mark.parametrize("path,status", [
    ("/ghost", 404), ("/limited", 503), ("/down", 502),
    ("/-bad-", 400), ("/octocat?per_page=500", 400), ("/octocat?page=abc", 400),
])
def test_error_handling(client, path, status):
    assert client.get(path).status_code == status


def test_healthz(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}


@pytest.mark.skipif(os.environ.get("LIVE_TESTS") != "1", reason="set LIVE_TESTS=1")
def test_live_octocat():
    r = app_module.create_app().test_client().get("/octocat")
    assert r.status_code == 200
    assert len(r.get_json()["gists"]) > 0
