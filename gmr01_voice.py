#!/usr/bin/env python3
"""
GMR-01 voice module — PROPOSED extension.

'can it speak' — text-to-speech for the pipeline via macOS `say`
(native, offline, no deps). Fallback chain: `say` -> pyttsx3 if
installed -> silent no-op with notice.

Usage:
  .venv/bin/python gmr01_voice.py "text to speak"
  .venv/bin/python gmr01_voice.py --file transcript.txt --lines 3
  .venv/bin/python gmr01_voice.py --handoff            # speak HANDOFF stmts
"""

import argparse
import subprocess
import sys


def speak(text: str, voice: str = None, rate: int = 200):
    """Speak text via macOS say. Returns True if audio played."""
    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    cmd += ["-r", str(rate), text]
    try:
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def speak_lines(path: str, n: int = 5, voice=None, rate=200):
    """Speak the first n non-empty lines of a text file."""
    try:
        with open(path) as f:
            lines = [l.strip() for l in f if l.strip()][:n]
    except FileNotFoundError:
        print(f"no such file: {path}")
        return False
    ok = True
    for l in lines:
        ok &= speak(l, voice, rate)
    return ok


def speak_handoffs(path: str = "handoff_statements.txt", n: int = 10,
                   voice=None, rate=200):
    """Speak HANDOFF statements verbatim (embedded-model feed)."""
    try:
        with open(path) as f:
            lines = [l.strip() for l in f if l.strip().startswith("HANDOFF")]
    except FileNotFoundError:
        print(f"no such file: {path}")
        return False
    ok = True
    for l in lines[:n]:
        # strip the key= prefix noise for spoken clarity
        spoken = l.replace("HANDOFF key=", "handoff ").replace("=", " ")
        ok &= speak(spoken, voice, rate)
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--lines", type=int, default=5)
    ap.add_argument("--handoff", action="store_true")
    ap.add_argument("--voice")
    ap.add_argument("--rate", type=int, default=200)
    a = ap.parse_args()

    if a.handoff:
        ok = speak_handoffs(n=a.lines, voice=a.voice, rate=a.rate)
    elif a.file:
        ok = speak_lines(a.file, n=a.lines, voice=a.voice, rate=a.rate)
    elif a.text:
        ok = speak(a.text, voice=a.voice, rate=a.rate)
    else:
        ap.print_help()
        sys.exit(0)
    sys.exit(0 if ok else 1)
