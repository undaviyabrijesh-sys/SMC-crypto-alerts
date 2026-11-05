"""OpenAI credential formatting checks without network access."""
import os
import unittest
from unittest.mock import patch

from ai_analyst import _configured_api_key


class ApiKeyValidationTests(unittest.TestCase):
    def test_trims_outer_whitespace_from_secret(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "  sk-test-value\n"}):
            self.assertEqual(_configured_api_key(), "sk-test-value")

    def test_rejects_embedded_whitespace_without_echoing_secret(self):
        secret = "sk-test\nvalue"
        with patch.dict(os.environ, {"OPENAI_API_KEY": secret}):
            with self.assertRaisesRegex(RuntimeError, "embedded whitespace"):
                _configured_api_key()

    def test_rejects_non_ascii_secret(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test\u200b"}):
            with self.assertRaisesRegex(RuntimeError, "non-ASCII"):
                _configured_api_key()

    def test_missing_secret_has_clear_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                _configured_api_key()


if __name__ == "__main__":
    unittest.main(verbosity=2)
