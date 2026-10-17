"""Original soft electronic sports groove; no recordings or audio samples."""
import argparse
from pathlib import Path
import wave
import numpy as np


def soundtrack(path, seconds):
    if not np.isfinite(seconds) or not 0 < seconds <= 600:
        raise ValueError('Duration must be between zero and 600 seconds')
    rate, beat = 44100, 60 / 112
    audio = np.zeros(round(seconds * rate), dtype=np.float64)
    rng = np.random.default_rng(11228)
    chords = [(50, 57, 60, 65), (46, 53, 57, 62), (53, 60, 64, 69), (48, 55, 58, 64)]

    def add(start, signal):
        first = round(start * rate)
        count = min(len(signal), len(audio) - first)
        if count > 0:
            audio[first:first + count] += signal[:count]

    def note(start, duration, midi, gain, kind='keys'):
        t = np.arange(round(duration * rate)) / rate
        phase = 2 * np.pi * (440 * 2 ** ((midi - 69) / 12)) * t
        if kind == 'bass':
            signal = np.sin(phase) + .22 * np.sin(2 * phase)
            decay = np.exp(-t * 5)
        else:
            signal = np.sin(phase) + .18 * np.sin(2 * phase) + .08 * np.sin(3 * phase) * np.exp(-t * 9)
            decay = np.exp(-t * (4 if kind == 'lead' else 2.5))
        envelope = np.minimum(t / .006, 1) * np.minimum((duration - t) / .06, 1)
        add(start, gain * signal * decay * np.maximum(envelope, 0))

    for bar in range(int(seconds / (4 * beat)) + 1):
        start, chord = bar * 4 * beat, chords[bar % len(chords)]
        for position in (0, 1.5, 2.75):
            for midi in chord:
                note(start + position * beat, .7, midi + 12, .026)
        for position, interval in ((0, 0), (.75, 12), (1.5, 0), (2.5, 7), (3.25, 0)):
            note(start + position * beat, .3, chord[0] - 12 + interval, .13, 'bass')
        melody = (chord[2] + 24, chord[1] + 24, chord[3] + 12, chord[2] + 24)
        for position, midi in zip((.5, 1.25, 2.5, 3.5), melody):
            if bar % 4 != 3 or position < 2:
                note(start + position * beat, .26, midi, .043, 'lead')
        for position in (0, 1.5, 2, 3.25):
            t = np.arange(round(.2 * rate)) / rate
            phase = 2 * np.pi * (48 * t + 55 * .025 * (1 - np.exp(-t / .025)))
            add(start + position * beat, .25 * np.sin(phase) * np.exp(-t * 24))
        for position in (1, 3):
            t = np.arange(round(.14 * rate)) / rate
            noise = rng.normal(size=len(t))
            add(start + position * beat, .045 * (noise - np.roll(noise, 1)) * np.exp(-t * 35))
        for tick in range(8):
            t = np.arange(round(.045 * rate)) / rate
            noise = rng.normal(size=len(t))
            hat = .008 * (noise - np.roll(noise, 1)) * np.exp(-t * 90)
            add(start + (tick * .5 + (.035 if tick % 2 else 0)) * beat, hat)
    fade = np.minimum(np.arange(len(audio)) / (rate * 1.5), 1)
    fade *= np.minimum((len(audio) - np.arange(len(audio))) / (rate * 2.5), 1)
    audio = np.tanh(audio) * fade
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=float, required=True)
    args = parser.parse_args()
    soundtrack(args.output, args.seconds)
