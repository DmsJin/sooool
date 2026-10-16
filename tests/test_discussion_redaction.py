import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "export_discussions", Path(__file__).resolve().parents[1] / "scripts/export_discussions.py"
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class Redaction(unittest.TestCase):
    def test_key_after_real_or_encoded_newline(self):
        fake = "sk-" + "x" * 40
        for prefix in ["\n", r"\n", "key: "]:
            self.assertNotIn(fake, exporter.scrub(prefix + fake))

    def test_nested_tool_payload_and_auth_fields(self):
        fake = "sk-" + "x" * 40
        value = {"output": [{"text": "key\n" + fake}], "password": "example secret"}
        result = exporter.clean(value)
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertNotIn(fake, str(result))

    def test_signed_url_credentials_and_private_key(self):
        url = "https://example.test/?X-Amz-Credential=AKIA" + "A" * 16 + "&X-Amz-Signature=example"
        result = exporter.scrub(url)
        self.assertNotIn("AKIA", result)
        self.assertNotIn("Signature=example", result)
        marker = "OPENSSH " + "PRIVATE KEY"
        key = f"-----BEGIN {marker}-----\nexample\n-----END {marker}-----"
        self.assertEqual(exporter.scrub(key), "[REDACTED_PRIVATE_KEY]")
