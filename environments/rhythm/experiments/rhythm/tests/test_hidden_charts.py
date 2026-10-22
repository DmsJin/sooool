import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.rhythm.hidden_charts import generate


class HiddenChartTests(unittest.TestCase):
    def test_short_chart_is_same_seed_prefix_without_rescheduling_notes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);freeze=directory/'freeze.json';freeze.write_text('{"frozen":true}')
            with patch('experiments.rhythm.hidden_charts.secrets.token_bytes',return_value=b'1'*32):
                full=generate(directory/'full',freeze)
                short=generate(directory/'short',freeze,duration=20)
            full_notes=json.loads(full.chart_path.read_text())['notes']
            short_chart=json.loads(short.chart_path.read_text())
            self.assertEqual(short_chart['duration'],20)
            self.assertEqual(short_chart['notes'],[note for note in full_notes if note['time']<=19.3])
            self.assertGreater(len(short_chart['notes']),0)
            self.assertEqual(short.public_metadata()['note_count'],len(short_chart['notes']))

    def test_freeze_must_exist_before_secret_seed_is_drawn(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch('experiments.rhythm.hidden_charts.secrets.token_bytes') as seed:
                with self.assertRaises(FileNotFoundError):
                    generate(directory / 'private', directory / 'missing-freeze.json')
                seed.assert_not_called()

    def test_fresh_charts_keep_notes_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            freeze = directory / 'freeze.json'
            freeze.write_text('{"policy":"selected"}')
            first = generate(directory / 'private', freeze, model_workspace=directory / 'model')
            second = generate(directory / 'private', freeze, model_workspace=directory / 'model')
            public = first.public_metadata()
            self.assertNotEqual(first.chart_path.read_bytes(), second.chart_path.read_bytes())
            self.assertEqual(public['note_count'], 52)
            self.assertTrue({'notes', 'lanes', 'seed', 'chart_path', 'seed_path'}.isdisjoint(public))
            self.assertNotIn(str(first.chart_path), repr(first))
            chart = json.loads(first.chart_path.read_text())
            self.assertEqual(len(chart['notes']), 52)
            self.assertEqual({note['subdivision'] for note in chart['notes']}, {4, 8})
            self.assertTrue(all(0 <= note['lane'] < 4 and 0 < note['time'] < 30 for note in chart['notes']))
            self.assertEqual(first.seed_path.stat().st_mode & 0o777, 0o600)

    def test_refuses_private_evidence_under_model_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            freeze = directory / 'freeze.json'
            freeze.write_text('{"frozen":true}')
            with self.assertRaises(ValueError):
                generate(directory / 'model/private', freeze, model_workspace=directory / 'model')


if __name__ == '__main__':
    unittest.main()
