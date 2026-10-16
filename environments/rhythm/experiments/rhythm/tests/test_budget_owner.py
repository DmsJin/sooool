import pathlib
import tempfile
import unittest
from unittest.mock import patch
from experiments.rhythm.providers import APIProvider

class BudgetOwnerTests(unittest.TestCase):
    def test_remote_ownership_blocks_local_transport_before_client_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path / 'budget.remote-owner.json').write_text('{}')
            with patch('experiments.rhythm.providers.httpx.AsyncClient') as client:
                with self.assertRaisesRegex(RuntimeError, 'temporarily owned'):
                    APIProvider('test-placeholder', path)
                client.assert_not_called()
            self.assertFalse((path / 'budget.json').exists())
