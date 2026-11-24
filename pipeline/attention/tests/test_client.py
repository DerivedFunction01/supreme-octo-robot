"""Client pins for the empty-answer cure (C1+C2): a
2xx with an empty or non-JSON body raises the
named EmptyAnswer — the call's landing is unknown —
instead of a raw JSONDecodeError. The transport is a
scripted fake opener — no socket, no live surface.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention import client  # noqa: E402


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _Opener:
    """Answers open() from a script: bytes become a
    response body, an exception instance is raised."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def open(self, req, timeout=None):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Response(item)


def _run(script, fn):
    opener = _Opener(script)
    with mock.patch.object(client, "OPENER", opener):
        return fn(), opener


class EmptyAnswerTests(unittest.TestCase):
    def test_empty_2xx_body_raises_empty_answer(self):
        with self.assertRaises(client.EmptyAnswer) as ctx:
            _run([b""], lambda: client.request("GET", "/api/v1/registries"))
        self.assertIn("landing is unknown", str(ctx.exception))

    def test_non_json_2xx_body_raises_empty_answer(self):
        with self.assertRaises(client.EmptyAnswer):
            _run([b"<html>not json</html>"], lambda: client.get_registries())

    def test_json_2xx_body_parses_as_before(self):
        result, opener = _run([b'{"handlers": []}'], client.get_registries)
        self.assertEqual(result, {"handlers": []})
        self.assertEqual(opener.calls, 1)


if __name__ == "__main__":
    unittest.main()
