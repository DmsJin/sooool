"""Export an applied-action simulation replay; never calls a model."""
import argparse
import json
from pathlib import Path
import subprocess
from environment import BrowserEnv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('episode', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--url', default='http://127.0.0.1:18791')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    summary = json.loads((args.episode / 'summary.json').read_text())
    assert summary['mode'] == 'sim' and summary['complete']
    actions = [json.loads(line) for line in (args.episode / 'actions.jsonl').read_text().splitlines()]
    actions = [a for a in actions if a.get('status') == 'applied']
    assert actions == sorted(actions, key=lambda a: a['visual_frame'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoder = None if args.verify_only else subprocess.Popen([args.ffmpeg, '-y', '-v', 'error', '-f', 'image2pipe',
        '-framerate', '30', '-vcodec', 'png', '-i', '-', '-an', '-c:v', 'libx264',
        '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags',
        '+faststart', str(args.output)], stdin=subprocess.PIPE)
    count = 0
    try:
        with BrowserEnv(args.url) as env:
            env.reset(seed=summary['seed'], mode='sim', speed=1)
            cursor = 0
            final_visual = summary['visual_frames']
            visual = 0
            while True:
                while cursor < len(actions) and actions[cursor]['visual_frame'] == visual:
                    clock = env.apply(actions[cursor]['plan'])
                    assert clock['frame'] == actions[cursor]['logical_frame']
                    cursor += 1
                if visual % 2 == 0:
                    if encoder:
                        encoder.stdin.write(env.capture()['png'])
                    count += 1
                if visual == final_visual:
                    break
                next_visual = min(final_visual, visual + (2 if visual % 2 == 0 else 1))
                if cursor < len(actions):
                    next_visual = min(next_visual, actions[cursor]['visual_frame'])
                assert next_visual > visual
                clock = env.advance(next_visual - visual)
                assert clock['visual_frame'] == next_visual, (clock, next_visual)
                visual = next_visual
                if visual % 600 == 0:
                    print(json.dumps({'visual_frame': visual, 'frames_encoded': count}), flush=True)
            final = env.diagnostics()
            state = final['state']
            expected = json.loads((args.episode / 'final_state.json').read_text())
            expected.pop('clock', None)
            assert state == expected, 'Replay differs from recorded final engine state'
            assert final['clock']['frame'] == summary['tick']
            assert final['clock']['visual_frame'] == final_visual
            assert cursor == len(actions)
            report = {'kind': 'applied_action_replay', 'fps': 30, 'speed': 1,
                'frames': count, 'episode': str(args.episode), 'summary': summary,
                'verified_final_state': state, 'verified_clock': final['clock']}
            args.output.with_suffix('.json').write_text(json.dumps(report, indent=2))
            print(json.dumps({'verified': True, 'tick': state['tick'], 'status': state['status']}), flush=True)
    finally:
        if encoder:
            encoder.stdin.close()
        result = encoder.wait() if encoder else 0
    if result:
        raise RuntimeError(f'ffmpeg failed: {result}')


if __name__ == '__main__':
    main()
