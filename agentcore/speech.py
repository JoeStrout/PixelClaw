"""Text-to-speech. Replace this module to swap TTS backends."""

import re
import threading

# sounddevice is used instead of Raylib audio because _speak_worker runs on a
# background thread and Raylib audio (like textures) requires the main thread.
# librosa is used for pitch-preserving time-stretch; Raylib has no equivalent.
import librosa
import numpy as np
import sounddevice as sd

VOICE = "F3"
SPEED = 1.0        # synthesize slowly for reliability; supertonic garbles at high speeds
PLAYBACK_RATE = 1.4  # pitch-preserving time-stretch applied at playback via librosa


def mod_ring(audio: np.ndarray, duration: float, hz: float = 75.0) -> np.ndarray:
    n = audio.shape[-1]
    t = np.linspace(0, duration, n, endpoint=False)
    return (audio * np.sin(2 * np.pi * hz * t)).astype(audio.dtype)


def mod_echo(audio: np.ndarray, duration: float, delay_s: float = 0.020, amp: float = 0.50) -> np.ndarray:
    sr = audio.shape[-1] / duration
    d = int(sr * delay_s)
    echo = np.zeros_like(audio)
    echo[..., d:] = audio[..., :-d] * amp
    return (audio + echo).astype(audio.dtype)

_tts = None
_style = None
_init_lock = threading.Lock()


def _get_engine():
    global _tts, _style
    with _init_lock:
        if _tts is None:
            from supertonic import TTS
            _tts = TTS(auto_download=True)
            _style = _tts.get_voice_style(voice_name=VOICE)
    return _tts, _style


def speak(text: str) -> None:
    """Speak text asynchronously; returns immediately."""
    threading.Thread(target=_speak_worker, args=(text,), daemon=True).start()


_SYMBOL_MAP = {
    '×': 'by', '÷': 'divided by', '±': 'plus or minus',
    '≈': 'approximately', '≠': 'not equal to', '≤': 'less than or equal to',
    '≥': 'greater than or equal to', '→': 'to', '←': 'from',
    '°': ' degrees', '%': ' percent', '&': 'and', '@': 'at',
    '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
    '\u2014': ', ', '\u2013': ' to ',
    '=': ' equals ',
    ' px' ' pixels'
}

def _clean(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)   # bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)        # italic
    text = re.sub(r'`+(.+?)`+', r'\1', text)        # code
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)  # headings
    for sym, word in _SYMBOL_MAP.items():
        text = text.replace(sym, word)
    return text.encode('ascii', errors='ignore').decode('ascii')


def _speak_worker(text: str) -> None:
    try:
        tts, style = _get_engine()
        clean_text = _clean(text)
        print(f"TTS: {clean_text}")
        audio, sample_rate = tts.synthesize(_clean(text), voice_style=style, lang="en", speed=SPEED)
        duration = float(np.squeeze(sample_rate))  # supertonic returns duration, not sample rate
        audio = mod_echo(audio, duration * PLAYBACK_RATE)
        audio_mono = audio.squeeze()
        actual_sr = int(audio_mono.shape[-1] / duration)
        if PLAYBACK_RATE != 1.0:
            audio_mono = librosa.effects.time_stretch(audio_mono, rate=PLAYBACK_RATE)
        sd.stop()
        sd.play(audio_mono, samplerate=actual_sr)
        sd.wait()
    except Exception as e:
        print(f"[speech] {e}")


if __name__ == "__main__":
    import sys

    KNOWN_VOICES = ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]
    sample_text = "Hello! This is a test of the text-to-speech system."

    from supertonic import TTS
    tts = TTS(auto_download=True)

    if len(sys.argv) > 1:
        voices_to_test = sys.argv[1:]
    else:
        print("Known voices:", ", ".join(KNOWN_VOICES))
        choice = input("Voice to test (default F5, or 'all'): ").strip() or "F5"
        voices_to_test = KNOWN_VOICES if choice == "all" else [choice]

    sample_text = input("Speech (press return for default): ") or sample_text
    speed = float(input(f"Synth speed 0.7–2.0 (default {SPEED}): ") or SPEED)
    rate = float(input(f"Playback rate (default {PLAYBACK_RATE}): ") or PLAYBACK_RATE)
    effect = input("Effect: ring / echo / none (default echo): ").strip() or "echo"

    for v in voices_to_test:
        print(f"Testing voice {v}...")
        style = tts.get_voice_style(voice_name=v)
        audio, sample_rate = tts.synthesize(sample_text, voice_style=style, lang="en", speed=speed)
        duration = float(np.squeeze(sample_rate))
        if effect == "ring":
            audio = mod_ring(audio, duration)
        elif effect == "echo":
            audio = mod_echo(audio, duration)
        audio_mono = audio.squeeze()
        dur = float(np.squeeze(sample_rate))
        actual_sr = int(audio_mono.shape[-1] / dur)
        if rate != 1.0:
            audio_mono = librosa.effects.time_stretch(audio_mono, rate=rate)
        sd.play(audio_mono, samplerate=actual_sr)
        sd.wait()

    print("Done.")
