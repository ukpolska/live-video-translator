"""Live translation server. The browser extension streams raw audio over a local websocket;
speech pieces are recognised and translated (see pipeline.py) and English text goes back.

Protocol:
  extension -> server: one JSON text message {"type": "hello", "sampleRate": 48000},
                       then binary messages of mono float32 audio at that sample rate
  server -> extension: JSON {"text": <English>, "original": <source text>, "lang": <ru|es|en>}"""
import asyncio
import functools
import json
import os
import sys
import time

import numpy as np
import websockets

import pipeline as pl

# Russian text in the log would crash on a legacy Windows console code page.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print = functools.partial(print, flush=True)

MAX_QUEUE = 3

config = pl.load_config()
args = sys.argv[1:]
idle_exit_minutes = 0.0  # 0 = never; the extension's helper starts the program with --idle-exit 10
if "--idle-exit" in args:
    position = args.index("--idle-exit")
    idle_exit_minutes = float(args[position + 1])
    del args[position : position + 2]
if args and args[0] in ("auto", "ru", "es"):
    config["language"] = args[0]  # e.g. "python server.py ru" locks the server to Russian
markers = config.get("markers", {})
markers_enabled = markers.get("enabled", True)
inaudible_min_seconds = markers.get("inaudible_min_seconds", 2.0)
inaudible_cooldown = markers.get("inaudible_cooldown_seconds", 6.0)
print(f"Language mode: {config['language']}")
print("Loading speech and translation models (about 10 seconds)...")
pipe = pl.Pipeline(config)
print("Models loaded.")


async def translate_worker(websocket, queue, clock):
    while True:
        speech, pause_wait, queued_at = await queue.get()
        queue_wait = time.time() - queued_at
        result = await asyncio.to_thread(pipe.process, speech)
        if "skipped" in result:
            print(f"({result['skipped']})")
            # Sound was detected for a while but nothing could be made out (speech under
            # music, mumbling, noise). Say so, but not repeatedly and not for short blips.
            seconds = len(speech) / pl.TARGET_RATE
            if (
                markers_enabled
                and result["skipped"].startswith("nothing recognised")
                and seconds >= inaudible_min_seconds
                and time.time() - clock.get("last_marker", 0) > inaudible_cooldown
            ):
                clock["last_marker"] = time.time()
                try:
                    await websocket.send(json.dumps({"text": "[inaudible]", "kind": "inaudible"}))
                except websockets.ConnectionClosed:
                    return
            continue
        # clock["drift"]: how far the audio we have received is behind real time. Near 0 is
        # healthy; a number that keeps growing means the browser is sending audio late.
        drift = (time.time() - clock["t0"]) - clock["received"]
        after_speech = pause_wait + queue_wait + result["asr_seconds"] + result["translate_seconds"]
        confidence = result["confidence"]
        confidence_text = "n/a" if confidence is None else f"{confidence:.3f}"
        print(
            f"[{result['lang']}{' via Whisper' if result['fallback_used'] else ''}"
            f"{' - Parakeet had written ' + repr(result['heard']) if result['heard'] else ''}] "
            f"{result['original']!r} -> {result['text']!r}\n"
            f"    speech-model confidence {confidence_text} (0 = certain, more negative = less sure)\n"
            f"    {result['speech_seconds']:.1f}s speech; caption sent {after_speech:.1f}s after the speaker stopped "
            f"(pause wait {pause_wait:.1f}, queue {queue_wait:.1f}, recognise {result['asr_seconds']:.1f}, "
            f"translate {result['translate_seconds']:.1f}); audio clock drift {drift:+.1f}s"
        )
        text, kind = result["text"], ""
        if markers_enabled:
            if result["sound"]:
                kind = "music"
            elif result["unclear"]:
                text, kind = "[unclear] " + text, "unclear"
        clock["last_marker"] = 0 if not kind else time.time()
        try:
            await websocket.send(
                json.dumps({"text": text, "original": result["original"], "lang": result["lang"], "kind": kind})
            )
        except websockets.ConnectionClosed:
            return


activity = {"connections": 0, "idle_since": time.time()}


async def idle_watchdog():
    """Quits when nobody has been connected for a while, so the models stop using memory."""
    while True:
        await asyncio.sleep(15)
        idle_for = time.time() - activity["idle_since"]
        if activity["connections"] == 0 and idle_for > idle_exit_minutes * 60:
            print(f"Nobody has used the translator for {idle_exit_minutes:g} minutes: shutting down to free memory.")
            sys.stdout.flush()
            os._exit(0)


async def handle(websocket):
    activity["connections"] += 1
    print("Extension connected.")
    queue = asyncio.Queue()
    clock = {"t0": time.time(), "received": 0.0}
    worker = asyncio.create_task(translate_worker(websocket, queue, clock))
    stream = None
    rate = 48000
    window = {"start": time.time(), "audio": 0.0, "messages": 0}  # for the speed check below
    try:
        async for message in websocket:
            if isinstance(message, str):
                rate = int(json.loads(message)["sampleRate"])
                stream = pipe.new_stream(rate)
                clock["t0"], clock["received"] = time.time(), 0.0
                window.update(start=time.time(), audio=0.0, messages=0)
                print(f"Browser says it is sending audio at {rate} Hz.")
                continue
            if stream is None:
                continue
            samples = np.frombuffer(message, dtype=np.float32)
            clock["received"] += len(samples) / rate
            window["audio"] += len(samples) / rate
            window["messages"] += 1
            elapsed = time.time() - window["start"]
            if elapsed >= 15:
                # Should be about 1.00: the browser sends audio as fast as it plays.
                print(
                    f"Audio is arriving at {window['audio'] / elapsed:.2f}x real time "
                    f"({window['messages'] / elapsed:.1f} messages/s, "
                    f"{len(samples) / rate * 1000:.0f} ms of audio each)."
                )
                window.update(start=time.time(), audio=0.0, messages=0)
            pieces = stream.feed(samples)
            if (
                markers_enabled
                and stream.take_no_speech_event()
                and time.time() - clock.get("last_marker", 0) > inaudible_cooldown
            ):
                clock["last_marker"] = time.time()
                try:
                    await websocket.send(json.dumps({"text": "♪ [no speech]", "kind": "music"}))
                except websockets.ConnectionClosed:
                    break
            for speech, pause_wait in pieces:
                while queue.qsize() >= MAX_QUEUE:
                    queue.get_nowait()
                    print("Falling behind: dropped an old speech piece to catch up.")
                queue.put_nowait((speech, pause_wait, time.time()))
    finally:
        worker.cancel()
        activity["connections"] -= 1
        activity["idle_since"] = time.time()
        print("Extension disconnected.")


async def main():
    port = config["port"]
    async with websockets.serve(handle, "localhost", port, max_size=None, ping_interval=None):
        print(f"Translation server listening on ws://localhost:{port}")
        if idle_exit_minutes > 0:
            asyncio.create_task(idle_watchdog())
            activity["idle_since"] = time.time()
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
