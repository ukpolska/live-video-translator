"""Starts the translator program when the Chrome extension asks for it.

Chrome runs this ("native messaging") when you click the extension's button. It starts
server.py in the background if it is not already running, so nobody has to open
start_server.bat by hand. server.py shuts itself down again after a few idle minutes.

Chrome sends one message (4 length bytes, then JSON) on stdin and expects a reply the same way."""
import json
import os
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, "server.starting")
STARTUP_GRACE_SECONDS = 90  # loading the models takes 10-20 s on an ordinary PC


def read_message():
    header = sys.stdin.buffer.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def send_message(message):
    data = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def load_config():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def is_running(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def process_alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    return f'"{pid}"' in out.stdout


def recently_started():
    """True if a start was requested a moment ago and that program is still loading."""
    try:
        if time.time() - os.path.getmtime(LOCK) >= STARTUP_GRACE_SECONDS:
            return False
        with open(LOCK) as f:
            return process_alive(int(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return False


def start_server(idle_minutes):
    python = os.path.join(HERE, "venv", "Scripts", "python.exe")
    if not os.path.exists(python):
        return False
    log = open(os.path.join(HERE, "server.log"), "ab")
    DETACHED_PROCESS, NEW_PROCESS_GROUP, BREAKAWAY_FROM_JOB = 0x00000008, 0x00000200, 0x01000000
    base = DETACHED_PROCESS | NEW_PROCESS_GROUP
    # Chrome may keep its helpers in a "job" that is closed with Chrome: try to break away from
    # it so the translator keeps running; if that is not allowed, start it without.
    for flags in (base | BREAKAWAY_FROM_JOB, base):
        try:
            process = subprocess.Popen(
                [python, "server.py", "--idle-exit", str(idle_minutes)],
                cwd=HERE, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags, close_fds=True,
            )
            with open(LOCK, "w") as f:
                f.write(str(process.pid))
            return True
        except OSError:
            continue
    return False


def main():
    message = read_message() or {}
    config = load_config()
    port = config.get("port", 8765)
    command = message.get("command")
    if command == "start":
        if is_running(port):
            send_message({"ok": True, "state": "running"})
        elif recently_started():
            send_message({"ok": True, "state": "starting"})
        elif start_server(config.get("idle_exit_minutes", 10)):
            send_message({"ok": True, "state": "starting"})
        else:
            send_message({"ok": False, "error": "could not start the translator program"})
    elif command == "status":
        send_message({"ok": True, "state": "running" if is_running(port) else "stopped"})
    else:
        send_message({"ok": False, "error": "unknown command"})


if __name__ == "__main__":
    main()
