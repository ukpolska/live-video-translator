"""Pretends to be the browser extension: streams a WAV file to the running server in real time
at 48 kHz and prints the captions that come back, with how long after the speech they arrived.

Usage: python test_client.py <file.wav> [port]   (start server.py first; port defaults to 8765)"""
import asyncio
import json
import sys
import time
import wave

import numpy as np
import soxr
import websockets

RATE = 48000
CHUNK = int(RATE * 0.2)


async def main(path, port=8765):
    with wave.open(path) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        file_rate = w.getframerate()
    audio = soxr.resample(audio, file_rate, RATE)
    async with websockets.connect(f"ws://localhost:{port}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "sampleRate": RATE}))
        start = time.time()

        async def receive():
            async for message in ws:
                data = json.loads(message)
                print(f"{time.time() - start:6.1f}s  [{data['lang']}] {data['text']}")

        receiver = asyncio.create_task(receive())
        for i in range(0, len(audio), CHUNK):
            await ws.send(audio[i : i + CHUNK].astype(np.float32).tobytes())
            await asyncio.sleep(CHUNK / RATE)
        print(f"{time.time() - start:6.1f}s  (audio finished playing)")
        await asyncio.sleep(4)
        receiver.cancel()


asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8765))
