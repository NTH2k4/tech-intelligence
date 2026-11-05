import unittest
from unittest.mock import Mock

import httpx

from integrations.gemini_client import _retry_gemini_call


class HttpFailure(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class GeminiRetryTests(unittest.TestCase):
    def test_retries_transient_server_error_then_succeeds(self):
        call = Mock(side_effect=[HttpFailure(503), "ok"])

        result = _retry_gemini_call(call, {"input": "prompt"})

        self.assertEqual(result, "ok")
        self.assertEqual(call.call_count, 2)

    def test_does_not_retry_permanent_client_error(self):
        call = Mock(side_effect=HttpFailure(400))

        with self.assertRaises(HttpFailure):
            _retry_gemini_call(call, {"input": "prompt"})

        self.assertEqual(call.call_count, 1)

    def test_retries_transport_error_then_succeeds(self):
        call = Mock(side_effect=[
            httpx.ConnectError("temporary network issue"),
            "ok",
        ])

        result = _retry_gemini_call(call, {"input": "prompt"})

        self.assertEqual(result, "ok")
        self.assertEqual(call.call_count, 2)


if __name__ == "__main__":
    unittest.main()
