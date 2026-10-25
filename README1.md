# Gist API

Lists a GitHub user's public Gists.

    GET /<user>?page=1&per_page=30

Returns JSON: `{user, page, per_page, has_next_page, gists:[{id, description, url, created_at, updated_at, files:[...]}]}`.
Errors: `400` bad username/params, `404` unknown user, `503` GitHub rate-limited, `502` GitHub unreachable.
Extras: pagination, 60s in-memory cache (`CACHE_TTL_SECONDS`), optional `GITHUB_TOKEN` for higher rate limits, `/healthz`.

## Run
    docker build -t gist-api .
    docker run --rm -p 8080:8080 gist-api
    curl localhost:8080/octocat

## Test
    pip install -r requirements-dev.txt
    pytest                      # unit tests (GitHub mocked)
    LIVE_TESTS=1 pytest         # also hits the real GitHub API with octocat
