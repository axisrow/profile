from __future__ import annotations

import io
import json
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from sync import github


def _response(body, status=200):
    """A minimal stand-in for an http.client.HTTPResponse context manager."""
    response = mock.MagicMock()
    response.status = status
    response.read.return_value = json.dumps(body).encode()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=code,
        msg=f"HTTP {code}",
        hdrs=Message(),
        fp=io.BytesIO(b"{}"),
    )


class ApiGetTests(unittest.TestCase):
    def setUp(self) -> None:
        # Clear the token so each test asserts deterministic header state.
        self._token = mock.patch.dict("os.environ", {}, clear=False)
        self._token.start()

    def tearDown(self) -> None:
        self._token.stop()

    def test_sends_default_headers_without_token(self) -> None:
        with mock.patch("sync.github.urllib.request.urlopen", return_value=_response({"ok": True})) as opened:
            data, status = github.api_get("repos/foo/bar")
        self.assertEqual(data, {"ok": True})
        self.assertEqual(status, 200)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/foo/bar")
        self.assertEqual(request.headers, {"Accept": "application/vnd.github+json",
                                           "User-agent": "axisrow-profile-sync"})

    def test_attaches_bearer_token_and_custom_accept(self) -> None:
        mock.patch.dict("os.environ", {"GH_TOKEN": "abc123"}).start()
        with mock.patch("sync.github.urllib.request.urlopen", return_value=_response([])) as opened:
            github.api_get("repos/foo/bar", "application/vnd.github.star+json")
        request = opened.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer abc123")
        self.assertEqual(request.headers["Accept"], "application/vnd.github.star+json")

    def test_tolerated_code_returns_none(self) -> None:
        err = _http_error(404)
        with mock.patch("sync.github.urllib.request.urlopen", side_effect=err):
            data, status = github.api_get("repos/foo/bar", tolerate=(403, 404))
        self.assertIsNone(data)
        self.assertEqual(status, 404)

    def test_non_tolerated_code_raises(self) -> None:
        with mock.patch("sync.github.urllib.request.urlopen", side_effect=_http_error(500)):
            with self.assertRaises(urllib.error.HTTPError):
                github.api_get("repos/foo/bar", tolerate=(403, 404))

    def test_passes_timeout_through(self) -> None:
        with mock.patch("sync.github.urllib.request.urlopen", return_value=_response({})) as opened:
            github.api_get("repos/foo/bar", timeout=7)
        self.assertEqual(opened.call_args.kwargs["timeout"], 7)


class PagedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._token = mock.patch.dict("os.environ", {}, clear=False)
        self._token.start()

    def tearDown(self) -> None:
        self._token.stop()

    def test_walks_pages_until_short_page(self) -> None:
        pages = [_response([{"id": i} for i in range(100)]), _response([{"id": 100}])]
        with mock.patch("sync.github.urllib.request.urlopen", side_effect=pages) as opened:
            rows = github.paged("repos/foo/bar/stargazers", "application/vnd.github.star+json")
        self.assertEqual(len(rows), 101)
        urls = [c.args[0].full_url for c in opened.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://api.github.com/repos/foo/bar/stargazers?per_page=100&page=1",
                "https://api.github.com/repos/foo/bar/stargazers?per_page=100&page=2",
            ],
        )
        # Custom accept propagates to every paged request.
        self.assertEqual(opened.call_args_list[0].args[0].headers["Accept"],
                         "application/vnd.github.star+json")

    def test_appends_query_separator_for_prefiltered_path(self) -> None:
        # Real callers (owned_original_repositories) page a path that already
        # carries a query string; pagination must join with "&", not "?".
        with mock.patch("sync.github.urllib.request.urlopen",
                        return_value=_response([{"id": 1}])) as opened:
            github.paged("user/repos?affiliation=owner&visibility=all")
        self.assertEqual(
            opened.call_args.args[0].full_url,
            "https://api.github.com/user/repos?affiliation=owner&visibility=all&per_page=100&page=1",
        )

    def test_non_list_payload_raises(self) -> None:
        with mock.patch("sync.github.urllib.request.urlopen", return_value=_response({"not": "a list"})):
            with self.assertRaises(RuntimeError):
                github.paged("repos/foo/bar/stargazers")


if __name__ == "__main__":
    unittest.main()
