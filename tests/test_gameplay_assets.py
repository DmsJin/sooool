"""README rebuilds preserve source recordings and identify generated evidence."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    'build_readme_gifs', Path(__file__).resolve().parents[1] / 'scripts/build_readme_gifs.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class GameplayAssetsTests(unittest.TestCase):
    def rebuild(self, retained_at_companion):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'assets/gameplay'
            output.mkdir(parents=True)
            source = output / 'rhythm.mp4' if retained_at_companion else root / 'original.mp4'
            original = b'complete source video with audio'
            source.write_bytes(original)
            item = dict(game='rhythm', source=str(source.relative_to(root)),
                        start_seconds=2, duration_seconds=8, fps=12, width=640)
            commands = []

            def render(command, check):
                commands.append(command)
                Path(command[-1]).write_bytes(b'generated asset')

            with patch.object(builder, 'ROOT', root), patch.object(builder, 'OUT', output), \
                    patch.object(builder.subprocess, 'run', side_effect=render):
                builder.build(item)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(item['source_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(item['gif_sha256'], hashlib.sha256((output/'rhythm.gif').read_bytes()).hexdigest())
            self.assertEqual(item['bytes'], (output/'rhythm.gif').stat().st_size)
            self.assertFalse((output/'rhythm-palette.png').exists())
            return len(commands), (output/'rhythm.mp4').read_bytes()

    def test_complete_rhythm_video_is_preserved_when_rebuilding_its_gif(self):
        calls, video = self.rebuild(retained_at_companion=True)
        self.assertEqual(calls, 2)
        self.assertEqual(video, b'complete source video with audio')

    def test_external_source_still_produces_a_compact_mp4(self):
        calls, video = self.rebuild(retained_at_companion=False)
        self.assertEqual(calls, 3)
        self.assertEqual(video, b'generated asset')


if __name__ == '__main__':
    unittest.main()
