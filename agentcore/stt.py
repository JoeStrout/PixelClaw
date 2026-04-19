"""Speech-to-text using faster-whisper and sounddevice.

Model is downloaded automatically on first use (~145 MB for base.en).

Usage
-----
Call preload() at app start to warm up the model in the background.

Recording lifecycle
-------------------
1. start_recording()         — begin buffering mic audio
2a. commit_immediate(cb)     — stop now, transcribe what was captured  (push-to-talk)
2b. commit_vad(cb)           — keep going until 1 s of silence, then transcribe (tap mode)

cancel() aborts any active session without transcribing.
state() returns the current module state: "idle" | "recording" | "transcribing"
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import numpy as np

SAMPLE_RATE = 16_000        # Hz — required by Whisper

_CHUNK_S        = 0.05      # audio chunk duration (50 ms)
_VAD_THRESHOLD  = 0.02      # RMS below this = silence (laptop mic noise floor ~0.003–0.008)
_VAD_SILENCE_S  = 1.0       # seconds of post-speech silence → auto-stop
_VAD_TIMEOUT_S  = 5.0       # seconds with no speech at all → give up
_MIN_SPEECH_RMS = 0.005     # recordings quieter than this are not sent to Whisper

_model      = None
_model_lock = threading.Lock()

_lock     = threading.Lock()
_state    = "idle"                      # "idle" | "recording" | "transcribing"
_chunks:  list[np.ndarray] = []
_stop_evt: threading.Event | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def state() -> str:
    with _lock:
        return _state


def preload() -> None:
    """Start loading the Whisper model in the background; call at app launch."""
    threading.Thread(target=_get_model, daemon=True).start()


def start_recording() -> None:
    """Begin capturing microphone audio.  No-op if already recording."""
    global _state, _chunks, _stop_evt
    with _lock:
        if _state != "idle":
            return
        _state = "recording"
        _chunks = []
        _stop_evt = threading.Event()
        evt = _stop_evt
    threading.Thread(target=_record_worker, args=(evt,), daemon=True).start()


def commit_immediate(on_done: Callable[[str | None], None]) -> None:
    """Stop recording now and transcribe everything captured (push-to-talk mode)."""
    global _state, _stop_evt
    with _lock:
        if _state != "recording":
            return
        _state = "transcribing"
        _stop_evt.set()
        chunks = list(_chunks)
    threading.Thread(target=_transcribe, args=(chunks, on_done), daemon=True).start()


def commit_vad(on_done: Callable[[str | None], None]) -> None:
    """Keep recording until 1 s of silence, then transcribe (tap mode).
    Cancels automatically after 5 s if no speech is detected."""
    with _lock:
        if _state != "recording":
            return
    threading.Thread(target=_vad_worker, args=(on_done,), daemon=True).start()


def cancel() -> None:
    """Abort the current session without transcribing."""
    global _state, _stop_evt
    with _lock:
        if _state == "idle":
            return
        _state = "idle"
        if _stop_evt:
            _stop_evt.set()


# ---------------------------------------------------------------------------
# Internal workers
# ---------------------------------------------------------------------------

def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            # cpu_threads=1 prevents CTranslate2 from creating a libiomp5 thread
            # pool, avoiding a SIGSEGV when libomp (numpy/scipy) is also loaded.
            _model = WhisperModel("base.en", device="cpu", compute_type="int8",
                                  cpu_threads=1, num_workers=1)
    return _model


def _record_worker(stop_evt: threading.Event) -> None:
    import sounddevice as sd
    chunk_size = int(SAMPLE_RATE * _CHUNK_S)
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=chunk_size) as stream:
            while not stop_evt.is_set():
                data, _ = stream.read(chunk_size)
                with _lock:
                    _chunks.append(data.flatten().copy())
    except Exception as e:
        print(f"[stt] Recording error: {e}")


def _vad_worker(on_done: Callable[[str | None], None]) -> None:
    global _state, _stop_evt
    t_start     = time.monotonic()
    has_speech  = False
    silence_t: float | None = None
    prev_len    = 0

    while True:
        time.sleep(_CHUNK_S)

        with _lock:
            if _state != "recording":
                return          # cancelled externally
            n = len(_chunks)
            chunk = _chunks[n - 1] if n > prev_len else None
        prev_len = n

        if chunk is not None:
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if rms >= _VAD_THRESHOLD:
                has_speech = True
                silence_t  = None
            elif has_speech and silence_t is None:
                silence_t = time.monotonic()

        now = time.monotonic()

        if has_speech and silence_t is not None:
            if now - silence_t >= _VAD_SILENCE_S:
                break           # silence after speech — time to transcribe

        if not has_speech and now - t_start >= _VAD_TIMEOUT_S:
            print("[stt] No speech detected — please check microphone and sound settings.")
            with _lock:
                _state = "idle"
                _stop_evt.set()
            on_done(None)
            return

    with _lock:
        _state = "transcribing"
        _stop_evt.set()
        chunks = list(_chunks)
    _transcribe(chunks, on_done)


def _transcribe(chunks: list[np.ndarray], on_done: Callable[[str | None], None]) -> None:
    global _state
    try:
        if not chunks:
            on_done(None)
            return

        audio = np.concatenate(chunks)
        if float(np.sqrt(np.mean(audio ** 2))) < _MIN_SPEECH_RMS:
            on_done(None)
            return

        model = _get_model()
        segments, _ = model.transcribe(audio, language="en")
        text = " ".join(s.text.strip() for s in segments).strip()
        on_done(text or None)
    except Exception as e:
        print(f"[stt] Transcription error: {e}")
        on_done(None)
    finally:
        with _lock:
            _state = "idle"


# ---------------------------------------------------------------------------
# Manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import queue as _queue

    print("Loading model...")
    _get_model()
    print("Model ready.")

    result_q: _queue.SimpleQueue[str | None] = _queue.SimpleQueue()

    print("Recording for 4 s (VAD mode) — speak now...")
    start_recording()
    commit_vad(result_q.put)
    result = result_q.get(timeout=15)
    if result:
        print(f"Transcription: {result!r}")
    else:
        print("No speech detected.")
