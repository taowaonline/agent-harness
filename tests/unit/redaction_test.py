"""Unit tests for ai_harness.redaction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.redaction import (  # noqa: E402
    is_sensitive_env_var,
    redact,
    redact_argv,
    safe_env_for_logging,
)


class RedactionTests(unittest.TestCase):
    def test_redact_generic_api_key(self) -> None:
        out = redact("api_key=sk-1234567890abcdef call complete")
        self.assertIn("***REDACTED***", out)
        self.assertNotIn("sk-1234567890abcdef", out)

    def test_redact_bearer(self) -> None:
        out = redact("Authorization: Bearer abc.def.ghi")
        self.assertIn("***REDACTED***", out)
        self.assertNotIn("abc.def.ghi", out)

    def test_redact_aws_access_key(self) -> None:
        # AWS documented example key id, constructed at runtime so the
        # literal never lands in source.
        aws_example = "AKIA" + "IOSFODNN7EXAMPLE"
        out = redact(f"aws key {aws_example} used at noon")
        self.assertIn("***REDACTED***", out)
        self.assertNotIn(aws_example, out)

    def test_redact_github_pat(self) -> None:
        out = redact("env GITHUB_TOKEN=ghp_" + "a" * 36)
        self.assertIn("***REDACTED***", out)
        self.assertNotIn("ghp_", out)

    def test_redact_jwt(self) -> None:
        # A JWT-like string with header.payload.signature, each long enough.
        out = redact("token eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0NTY3.NnSo5T6sE7wvRZc")
        self.assertIn("***REDACTED***", out)
        self.assertNotIn("eyJhbGciOiJIUzI1", out)

    def test_redact_argv(self) -> None:
        argv = ["curl", "-H", "Authorization: Bearer abc.def.ghi", "https://x"]
        out = redact_argv(argv)
        self.assertEqual(out[0], "curl")
        self.assertEqual(out[1], "-H")
        self.assertIn("***REDACTED***", out[2])
        self.assertNotIn("abc.def.ghi", out[2])

    def test_redact_leaves_normal_text_intact(self) -> None:
        out = redact("hello world this is a normal log line")
        self.assertEqual(out, "hello world this is a normal log line")

    def test_sensitive_env_var_detection(self) -> None:
        self.assertTrue(is_sensitive_env_var("OPENAI_API_KEY"))
        self.assertTrue(is_sensitive_env_var("DATABASE_PASSWORD"))
        self.assertTrue(is_sensitive_env_var("AUTHORIZATION"))
        self.assertFalse(is_sensitive_env_var("LOG_LEVEL"))
        self.assertFalse(is_sensitive_env_var("PATH"))

    def test_safe_env_for_logging(self) -> None:
        out = safe_env_for_logging(
            {"OPENAI_API_KEY": "sk-live-secret", "PATH": "/usr/bin"}
        )
        self.assertEqual(out["OPENAI_API_KEY"], "***REDACTED***")
        self.assertEqual(out["PATH"], "/usr/bin")

    def test_redact_empty(self) -> None:
        self.assertEqual(redact(""), "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
