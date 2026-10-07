"""Spoken queries: a short recording turned into text, on this machine.

An official can say what they need instead of typing it. The browser records
the microphone and sends a WAV; this module transcribes it with OpenAI's
Whisper, open weights, running locally on CPU. No audio leaves the engine:
the browser's own speech recognition (the Web Speech API) sends audio to the
browser maker's servers, which a government procurement tool cannot do.

The transcript is returned, not searched. The search screen puts it in the
query box for the official to read and correct first, because a misheard
grade or rating ("43 grade" heard as "40 grade") would otherwise search for
the wrong thing without anyone seeing it. A spoken query in an Indian
language comes back in its own script and is then translated like a typed
one.

Model: openai/whisper-small (SPEECH_MODEL picks another checkpoint), about
1 GB, downloaded on first use. Whisper covers English and every query
language this engine supports except Odia. SPEECH_INPUT=0 turns the feature
off; SPEECH_WARMUP=0 skips loading the model in the background at startup.
"""

import io
import logging
import os
import re
import threading
import time
import wave
from typing import Optional

import numpy as np

logger = logging.getLogger("standards-retrieval.speech")

MODEL_NAME = os.environ.get("SPEECH_MODEL", "openai/whisper-small")
ENABLED = os.environ.get("SPEECH_INPUT", "1") != "0"

SAMPLE_RATE = 16000          # what Whisper expects
MAX_SECONDS = 30             # one Whisper window; a query is a sentence or two
MAX_BYTES = 4 * 1024 * 1024  # 30 s of 16-bit stereo at 48 kHz is under 6 MB; mono 16 kHz is ~1 MB
# Below this RMS a recording is silence or room noise, on which Whisper
# invents text ("Thank you.") rather than returning nothing.
SILENCE_RMS = 0.004

# Query languages Whisper does not know. NLLB translates Odia, but Whisper
# was not trained on it, so a spoken Odia query cannot be transcribed.
UNSUPPORTED = {"or": "Odia"}


# Whisper writes English like a caption: Title Case ("GI Pipes Medium Class",
# which the case-sensitive tender short forms then missed), American spelling
# ("liter", "jewelry", "armored", where the standards write litre, jewellery,
# armoured), units spelled out, a closing full stop, and "two burner" as
# "2. Burner". Measured on 104 spoken queries, these cost more searches than
# misheard words did.
_UK_SPELLING = [
    (r"\bliters?\b", lambda m: "litre" + ("s" if m.group(0).endswith("s") else "")),
    (r"\bjewelry\b", "jewellery"),
    (r"\barmored\b", "armoured"),
    (r"\baluminum\b", "aluminium"),
    (r"\bmillimet(?:er|re)s?\b", "mm"),
    (r"\bcentimet(?:er|re)s?\b", "cm"),
]


def tidy(text: str) -> str:
    """A transcript as an official would type it. Latin-script text only."""
    text = " ".join(text.split())
    if re.search(r"[^\x00-ɏ]", text):          # an Indian script: left as heard
        return text
    text = re.sub(r"^(\d+)\.\s+", r"\1 ", text)     # "2. Burner" -> "2 Burner"
    text = re.sub(r"[.!?]+$", "", text)
    # Title Case words to lower case; acronyms (GI, XLPE) and "500D" stay.
    text = re.sub(r"\b[A-Z][a-z]+\b", lambda m: m.group(0).lower(), text)
    for pattern, repl in _UK_SPELLING:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


class SpeechError(Exception):
    """The recording could not be used; the message is written for the user."""


class SpeechUnavailable(Exception):
    """The model is turned off or could not be loaded."""


_lock = threading.Lock()        # one load, and one transcription at a time on the CPU
_model = None
_processor = None
_load_error: Optional[str] = None


def status() -> dict:
    """For /health: whether the microphone can be offered, and whether the model is loaded."""
    return {"enabled": ENABLED and _load_error is None, "ready": _model is not None,
            "model": MODEL_NAME, "error": _load_error}


def _ensure_model():
    global _model, _processor, _load_error
    if not ENABLED:
        raise SpeechUnavailable("Spoken queries are turned off on this engine (SPEECH_INPUT=0).")
    if _model is not None:
        return _model, _processor
    if _load_error:
        raise SpeechUnavailable(f"The speech model could not be loaded: {_load_error}")
    with _lock:
        if _model is None:
            try:
                from transformers import WhisperForConditionalGeneration, WhisperProcessor

                started = time.time()
                logger.info("[Speech] Loading %s...", MODEL_NAME)
                _processor = WhisperProcessor.from_pretrained(MODEL_NAME)
                _model = WhisperForConditionalGeneration.from_pretrained(MODEL_NAME)
                _model.eval()
                logger.info("[Speech] Ready in %.0f s.", time.time() - started)
            except Exception as exc:  # noqa: BLE001 -- reported, and the rest of the engine runs
                _load_error = str(exc)[:300]
                logger.error("[Speech] Could not load %s: %s", MODEL_NAME, exc)
                raise SpeechUnavailable(f"The speech model could not be loaded: {_load_error}") from exc
    return _model, _processor


def warm_up() -> None:
    """Load the model in the background so the first spoken query does not wait for it."""
    if not ENABLED:
        return

    def _load():
        try:
            _ensure_model()
        except SpeechUnavailable:
            pass

    threading.Thread(target=_load, name="speech-warm-up", daemon=True).start()


def read_wav(data: bytes) -> np.ndarray:
    """16-bit PCM WAV (any rate, mono or stereo) as mono float32 at 16 kHz."""
    if len(data) > MAX_BYTES:
        raise SpeechError(f"The recording is too long. Keep a spoken query under {MAX_SECONDS} seconds.")
    try:
        with wave.open(io.BytesIO(data)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as exc:
        raise SpeechError("The recording is not a WAV file the engine can read.") from exc
    if width != 2:
        raise SpeechError("The recording must be 16-bit PCM audio.")

    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and len(audio):
        # Linear resampling: plenty for speech recognition, and no extra library.
        target = int(round(len(audio) * SAMPLE_RATE / rate))
        audio = np.interp(np.linspace(0, len(audio) - 1, target), np.arange(len(audio)), audio).astype(np.float32)

    seconds = len(audio) / SAMPLE_RATE
    if seconds > MAX_SECONDS + 0.5:
        raise SpeechError(f"The recording is {seconds:.0f} seconds long. Keep a spoken query under {MAX_SECONDS} seconds.")
    if seconds < 0.3:
        raise SpeechError("The recording is too short. Hold the microphone button a moment longer.")
    return audio


def transcribe(data: bytes, language: Optional[str] = None) -> dict:
    """Text of a spoken query.

    `language` is a query-language code ('hi', 'ta', ...) when the official
    chose one; otherwise Whisper detects it. Returns {text, seconds, model,
    language_hint}.
    """
    if language in UNSUPPORTED:
        raise SpeechError(f"Spoken queries in {UNSUPPORTED[language]} are not supported yet. Type the query instead.")
    audio = read_wav(data)
    if float(np.sqrt(np.mean(audio ** 2))) < SILENCE_RMS:
        raise SpeechError("No speech was heard. Check the microphone and speak a little closer to it.")

    model, processor = _ensure_model()
    import torch

    features = processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_features
    kwargs = {"task": "transcribe", "max_new_tokens": 160}
    if language and language != "auto":
        kwargs["language"] = language
    started = time.time()
    with _lock, torch.inference_mode():
        ids = model.generate(features, **kwargs)
    heard = " ".join(processor.batch_decode(ids, skip_special_tokens=True)[0].split())
    text = tidy(heard)
    logger.info("[Speech] %.1f s of audio in %.1f s", len(audio) / SAMPLE_RATE, time.time() - started)
    if not text:
        raise SpeechError("No words were recognised. Try again, or type the query.")
    return {"text": text, "heard": heard, "seconds": round(len(audio) / SAMPLE_RATE, 1), "model": MODEL_NAME,
            "language_hint": language if language and language != "auto" else None}
