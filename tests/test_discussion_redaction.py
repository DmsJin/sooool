import importlib.util
import json
import tempfile
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


class ArchiveScope(unittest.TestCase):
    def check_refresh(self, game):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source.jsonl'
            row = {'type':'response_item','timestamp':'2026-10-15T00:00:00Z',
                   'payload':{'type':'message','role':'assistant',
                              'content':[{'type':'output_text','text':'52 PERFECT'}]}}
            source.write_text(json.dumps(row)+'\n')
            dest = root/game
            for _ in range(2):
                exporter.export(source, dest)
                body = (dest/'conversation.md').read_text()
                self.assertTrue(body.startswith('> **Historical conversation export.**'))
                self.assertEqual(body.count('Historical conversation export'), 1)
                self.assertEqual(body.split('\n\n',1)[1],
                                 '### assistant 2026-10-15T00:00:00Z\n\n52 PERFECT')
                manifest = json.loads((dest/'manifest.json').read_text())
                self.assertEqual(manifest['messages'], 1)

    def test_rhythm_refresh_retains_scope_without_changing_exported_message(self):
        self.check_refresh('rhythm')

    def test_racing_refresh_retains_scope_without_changing_exported_message(self):
        self.check_refresh('racing')

    def test_asterix_refresh_retains_scope_without_changing_exported_message(self):
        self.check_refresh('asterix')

    def test_pingpong_refresh_retains_scope_without_changing_exported_message(self):
        self.check_refresh('pingpong')

    def test_touhou_refresh_retains_scope_without_changing_exported_message(self):
        self.check_refresh('touhou')
