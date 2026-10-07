"""Spoken queries: reading the recording, refusing what cannot be used, and the endpoint."""

import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import speech  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "spoken_query_en.wav"


def wav(seconds=1.0, rate=16000, channels=1, amplitude=0.3, width=2):
    """A tone, as the browser's recorder would send it."""
    n = int(seconds * rate)
    tone = amplitude * np.sin(2 * np.pi * 220 * np.arange(n) / rate)
    samples = np.repeat(tone[:, None], channels, axis=1).ravel()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        if width == 2:
            w.writeframes((samples * 32767).astype("<i2").tobytes())
        else:
            w.writeframes(((samples + 1) * 127).astype(np.uint8).tobytes())
    return buf.getvalue()


class TestReading:
    def test_16khz_mono_is_read_as_is(self):
        audio = speech.read_wav(wav(1.0))
        assert audio.dtype == np.float32 and len(audio) == 16000

    def test_other_rates_and_stereo_become_16khz_mono(self):
        audio = speech.read_wav(wav(1.0, rate=48000, channels=2))
        assert abs(len(audio) - 16000) <= 1

    def test_too_long_too_short_and_not_a_wav_are_refused(self):
        with pytest.raises(speech.SpeechError, match="under 30 seconds"):
            speech.read_wav(wav(32))
        with pytest.raises(speech.SpeechError, match="too short"):
            speech.read_wav(wav(0.1))
        with pytest.raises(speech.SpeechError, match="not a WAV"):
            speech.read_wav(b"RIFF....not really")
        with pytest.raises(speech.SpeechError, match="16-bit"):
            speech.read_wav(wav(1.0, width=1))


class TestRefusals:
    """Refused before the model is touched, so these never load it."""

    def test_silence_is_not_sent_to_the_model(self, monkeypatch):
        monkeypatch.setattr(speech, "_ensure_model", lambda: pytest.fail("model loaded for silence"))
        with pytest.raises(speech.SpeechError, match="No speech was heard"):
            speech.transcribe(wav(1.0, amplitude=0.0))

    def test_odia_is_refused_with_a_reason(self, monkeypatch):
        monkeypatch.setattr(speech, "_ensure_model", lambda: pytest.fail("model loaded for Odia"))
        with pytest.raises(speech.SpeechError, match="Odia"):
            speech.transcribe(wav(1.0), language="or")


class TestEndpoint:
    @pytest.fixture()
    def client(self, monkeypatch):
        from fastapi.testclient import TestClient
        import main
        return TestClient(main.app)

    def test_returns_the_text_without_searching(self, client, monkeypatch):
        seen = {}

        def fake(data, language=None):
            seen["language"] = language
            return {"text": "ceiling fan", "seconds": 1.0, "model": "fake", "language_hint": language}

        monkeypatch.setattr(speech, "transcribe", fake)
        resp = client.post("/transcribe", files={"audio": ("q.wav", wav(1.0), "audio/wav")}, data={"language": "hi"})
        assert resp.status_code == 200
        assert resp.json()["text"] == "ceiling fan"
        assert "results" not in resp.json()
        assert seen["language"] == "hi"

    def test_an_unusable_recording_is_422_with_the_reason(self, client):
        resp = client.post("/transcribe", files={"audio": ("q.wav", b"not audio", "audio/wav")})
        assert resp.status_code == 422
        assert "WAV" in resp.json()["detail"]

    def test_health_says_whether_to_offer_the_microphone(self, client):
        body = client.get("/health").json()
        assert set(body["speech"]) >= {"enabled", "ready", "model"}


def _model_cached():
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(speech.MODEL_NAME, "config.json"), str)
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _model_cached(), reason="speech model not downloaded; the test will not fetch 1 GB")
def test_a_real_recording_is_transcribed():
    """Windows' English voice saying a tender line, at 16 kHz."""
    text = speech.transcribe(_FIXTURE.read_bytes())["text"].lower()
    assert "ceiling fan" in text and "regulator" in text


class TestTidy:
    """Whisper captions; officials type. Measured on 104 spoken queries."""

    def test_title_case_goes_but_acronyms_and_grades_stay(self):
        assert speech.tidy("GI Pipes Medium Class for Water Supply") == "GI pipes medium class for water supply"
        assert speech.tidy("TMT bars FE500D for reinforcement.") == "TMT bars FE500D for reinforcement"

    def test_a_spoken_number_and_british_spelling(self):
        assert speech.tidy("2. Burner LPG gas stove") == "2 burner LPG gas stove"
        assert speech.tidy("Aluminium pressure cooker 5 Liter") == "aluminium pressure cooker 5 litre"
        assert speech.tidy("22 carat gold jewelry, armored cable, 15 millimeters") == \
            "22 carat gold jewellery, armoured cable, 15 mm"

    def test_an_indian_script_is_left_as_heard(self):
        assert speech.tidy("छत का पंखा.") == "छत का पंखा."
