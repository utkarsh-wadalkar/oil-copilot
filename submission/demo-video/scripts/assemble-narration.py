"""Assemble local speech at the exact visual beats; reject overlapping/clipped narration."""
import json
import wave
from pathlib import Path

root = Path(__file__).resolve().parents[1]
segments = json.loads((root / 'narration.json').read_text(encoding='utf-8'))
audio = root / 'public' / 'narration'
durations = {'Opening': 35, 'Architecture': 55, 'Compliance': 105,
             'Correction': 55, 'Memory': 40, 'Limits': 10}
rate = 22050
width = 2
combined = bytearray()
for chapter, duration in durations.items():
    track = bytearray(duration * rate * width)
    previous_end = 0
    for index, segment in enumerate(segments):
        if segment['chapter'] != chapter:
            continue
        with wave.open(str(audio / f'segment-{index:02}.wav'), 'rb') as source:
            assert (source.getframerate(), source.getsampwidth(), source.getnchannels()) == (rate, width, 1)
            samples = source.readframes(source.getnframes())
        start = round(segment['start'] * rate) * width
        limit = round(segment['end'] * rate) * width
        assert start >= previous_end and start + len(samples) <= limit <= len(track), segment
        track[start:start + len(samples)] = samples
        previous_end = start + len(samples)
    with wave.open(str(audio / f'{chapter}.wav'), 'wb') as target:
        target.setparams((1, width, rate, 0, 'NONE', 'not compressed'))
        target.writeframes(track)
    combined.extend(track)
with wave.open(str(audio / 'full-narration.wav'), 'wb') as target:
    target.setparams((1, width, rate, 0, 'NONE', 'not compressed'))
    target.writeframes(combined)
assert len(combined) == 300 * rate * width
print('Assembled 6 chapter tracks and exactly 300 seconds of narration.')
