"""Text-to-speech using Kokoro-ONNX.

Model files are downloaded automatically on first use to ~/.cache/kokoro-onnx/.

Raylib audio (miniaudio) is used for playback. Unlike OpenGL/textures, miniaudio
is thread-safe and can be called from background threads. InitAudioDevice() must
be called before first use — the app calls it in on_start().
"""

import re
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

VOICE = "bf_emma"
SPEED = 1.2

_RESOURCES = Path.home() / ".cache" / "kokoro-onnx"
_MODEL_URL  = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

_kokoro = None
_init_lock = threading.Lock()
_stop_evt = threading.Event()


def _get_engine():
    global _kokoro
    with _init_lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            _RESOURCES.mkdir(parents=True, exist_ok=True)
            model_path  = _RESOURCES / "kokoro-v1.0.onnx"
            voices_path = _RESOURCES / "voices-v1.0.bin"
            if not model_path.exists():
                print("[speech] Downloading kokoro model...", flush=True)
                urllib.request.urlretrieve(_MODEL_URL, model_path)
            if not voices_path.exists():
                print("[speech] Downloading kokoro voices...", flush=True)
                urllib.request.urlretrieve(_VOICES_URL, voices_path)
            _kokoro = Kokoro(str(model_path), str(voices_path))
    return _kokoro


def mod_ring(audio: np.ndarray, sample_rate: int, hz: float = 75.0) -> np.ndarray:
    t = np.linspace(0, len(audio) / sample_rate, len(audio), endpoint=False)
    return (audio * np.sin(2 * np.pi * hz * t)).astype(audio.dtype)


def mod_echo(audio: np.ndarray, sample_rate: int, delay_s: float = 0.020, amp: float = 0.50) -> np.ndarray:
    d = int(sample_rate * delay_s)
    echo = np.zeros_like(audio)
    echo[d:] = audio[:-d] * amp
    return (audio + echo).astype(audio.dtype)


_SYMBOL_MAP = {
    '×': 'by', '÷': 'divided by', '±': 'plus or minus',
    '≈': 'approximately', '≠': 'not equal to', '≤': 'less than or equal to',
    '≥': 'greater than or equal to', '→': 'to', '←': 'from',
    '°': ' degrees', '%': ' percent', '&': 'and', '@': 'at',
    '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
    '\u2014': ', ', '\u2013': ' to ', '=': ' equals ', ' px': ' pixels',
    '(s)': 's', 'i.e.': 'that is',
}


# (pattern, replacement, flags) applied in order before symbol substitution
_REGEX_MAP = [
    (r'\*\*(.+?)\*\*',  r'\1',          0),               # bold
    (r'\*(.+?)\*',      r'\1',          0),               # italic
    (r'`+(.+?)`+',      r'\1',          0),               # code
    (r'^#{1,6}\s*',     r'',            re.MULTILINE),    # headings
    (r'(\w{2,})\.(\S)',  r'\1 dot \2', 0),                   # intra-token dots: file.png → "file dot png"; skips e.g./i.e.
    (r'(\d)px',         r'\1 pixels',   0),               # 256px → 256 pixels
]


def _clean(text: str) -> str:
    for pat, rep, flags in _REGEX_MAP:
        text = re.sub(pat, rep, text, flags=flags)
    for sym, word in _SYMBOL_MAP.items():
        text = text.replace(sym, word)
    return text.encode('ascii', errors='ignore').decode('ascii')


def _play_raylib(audio: np.ndarray, sample_rate: int) -> None:
    import raylib as rl
    audio = audio.astype(np.float32)
    n = len(audio)
    buf = rl.ffi.new(f"float[{n}]")
    rl.ffi.buffer(buf)[:] = audio.tobytes()
    wave = rl.ffi.new("Wave *", {
        "frameCount": n,
        "sampleRate": sample_rate,
        "sampleSize": 32,
        "channels": 1,
        "data": buf,
    })
    sound = rl.LoadSoundFromWave(wave[0])
    _stop_evt.clear()
    rl.PlaySound(sound)
    while rl.IsSoundPlaying(sound) and not _stop_evt.is_set():
        time.sleep(0.01)
    rl.StopSound(sound)
    rl.UnloadSound(sound)


def stop() -> None:
    """Interrupt any currently playing TTS immediately."""
    _stop_evt.set()


def preload() -> None:
    """Start loading the TTS engine in the background; call at app launch."""
    threading.Thread(target=_get_engine, daemon=True).start()


def speak(text: str) -> None:
    """Speak text asynchronously; returns immediately."""
    _stop_evt.set()
    threading.Thread(target=_speak_worker, args=(text,), daemon=True).start()


def _speak_worker(text: str) -> None:
    try:
        kokoro = _get_engine()
        clean_text = _clean(text)
        print(f"[speech] {clean_text}")
        audio, sample_rate = kokoro.create(_clean(text), voice=VOICE, speed=SPEED, lang="en-us")
        audio = mod_echo(audio, sample_rate)
        _play_raylib(audio, sample_rate)
    except Exception as e:
        print(f"[speech] ERROR: {e}")


if __name__ == "__main__":
    import sys
    import raylib as rl

    # fmt: off
    # American voices: af_heart, af_bella, af_nicole, af_sarah, af_sky
    #                  am_adam, am_michael
    # British voices:  bf_emma, bf_isabella, bm_george, bm_lewis
    KNOWN_VOICES = [
        "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
        "am_adam", "am_michael",
        "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
    ]
    # fmt: on

    #sample_text = "Hello! This is a test of the text-to-speech system. This image is 1024 by 768 pixels."
    #sample_text = "Hello! 👋  Tell me what you’d like to do with your image(s)—e.g., crop/resize, remove background, pixelate, or edit something specific."
    #sample_text = "Updated `alpha_channel.png` to be a **grayscale rendering of `bear_trouble.png`’s alpha** and made `alpha_channel.png` **fully opaque**."
    #sample_text = "Padded the image to **1024×1024** by adding **256px** on all sides."
    sample_text = "Load a file, e.g., somePicture.png."

    if len(sys.argv) > 1:
        voices_to_test = sys.argv[1:]
    else:
        print("Known voices:", ", ".join(KNOWN_VOICES))
        choice = input("Voice to test (default bf_emma, or 'all'): ").strip() or "bf_emma"
        voices_to_test = KNOWN_VOICES if choice == "all" else [choice]

    sample_text = input("Speech (press return for default): ") or sample_text
    speed = float(input(f"Synth speed (default {SPEED}): ") or SPEED)
    effect = input("Effect: ring / echo / none (default echo): ").strip() or "echo"

    rl.InitWindow(400, 120, b"Speech Test")
    rl.InitAudioDevice()
    rl.SetTargetFPS(60)

    _get_engine()  # pre-load model before first voice test

    for v in voices_to_test:
        if rl.WindowShouldClose():
            break
        print(f"Testing voice {v}...")
        # Drive _speak_worker directly so cleaning, echo, and playback path are identical to the app.
        VOICE = v
        SPEED = speed
        t = threading.Thread(target=_speak_worker, args=(sample_text,))
        t.start()
        label = f"Playing: {v}".encode()
        while t.is_alive() and not rl.WindowShouldClose():
            rl.BeginDrawing()
            rl.ClearBackground((30, 30, 30, 255))
            rl.DrawText(label, 20, 45, 20, (200, 200, 200, 255))
            rl.EndDrawing()
        t.join()

    rl.CloseAudioDevice()
    rl.CloseWindow()
    print("Done.")
