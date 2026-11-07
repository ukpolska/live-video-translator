"""Feeds a WAV file through the pipeline as if it were a live stream and prints each caption.

Usage: python test_pipeline.py <file.wav> [browser_sample_rate] [language]
  browser_sample_rate: pretend the browser sends audio at this rate (default 16000; try 48000)
  language: auto (default), ru, es or en"""
import sys
import time
import wave

import numpy as np
import soxr

import pipeline as pl

wav_path = sys.argv[1]
rate = int(sys.argv[2]) if len(sys.argv) > 2 else 16000
config = pl.load_config()
if len(sys.argv) > 3:
    config["language"] = sys.argv[3]

with wave.open(wav_path) as w:
    channels, file_rate = w.getnchannels(), w.getframerate()
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
if channels > 1:
    audio = audio[::channels]
if file_rate != rate:
    audio = soxr.resample(audio, file_rate, rate)
duration = len(audio) / rate

t0 = time.time()
pipe = pl.Pipeline(config)
print(f"Models loaded in {time.time() - t0:.1f}s. Audio: {duration:.1f}s at {rate} Hz.\n")

stream = pipe.new_stream(rate)
asr_total = mt_total = 0.0


def show(speech):
    global asr_total, mt_total
    r = pipe.process(speech)
    if "skipped" in r:
        print(f"({r['skipped']})")
        return
    asr_total += r["asr_seconds"]
    mt_total += r["translate_seconds"]
    print(f"[{r['lang']}] {r['original']}\n     -> {r['text']}\n     ({r['speech_seconds']:.1f}s of speech, "
          f"recognised in {r['asr_seconds']:.2f}s, translated in {r['translate_seconds']:.2f}s)")


chunk = int(rate * 0.2)
for i in range(0, len(audio), chunk):
    for piece, _wait in stream.feed(audio[i : i + chunk]):
        show(piece)
for piece, _wait in stream.flush():
    show(piece)

print(f"\nTotal work: {asr_total + mt_total:.1f}s for {duration:.1f}s of audio "
      f"(speed {(asr_total + mt_total) / duration:.2f}x real time; below 1.0 keeps up)")
