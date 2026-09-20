"""Translate non-English procurement queries into English before searching.

A procurement official in a state department may describe what they need in
Hindi, Tamil or Bengali. The retrieval stack is English-only, so those queries
must be translated first.

Why translate rather than use a multilingual embedding model: measured on this
corpus, an untranslated Hindi query scores -8 to -9 on the cross-encoder,
which the confidence gate correctly reads as "no match". Translating first
brings the same queries to +2.8 to +8.5 and returns exactly the standards the
English phrasing returns. Swapping in a multilingual embedder would mean
retraining the ranker and rebuilding every index; translating is one step in
front of a pipeline that already works well.

Model: facebook/nllb-200-distilled-600M — open weights, runs locally on CPU,
no API key. Loaded lazily, because the English-only path must not pay for it.
"""

import logging
import re
import threading
from typing import Dict, Optional

logger = logging.getLogger("standards-retrieval.translation")

_MODEL_NAME = "facebook/nllb-200-distilled-600M"

# Languages offered in the UI. NLLB uses its own language codes.
SUPPORTED_LANGUAGES: Dict[str, Dict[str, str]] = {
    "en": {"name": "English", "native": "English", "nllb": None},
    "hi": {"name": "Hindi", "native": "हिन्दी", "nllb": "hin_Deva"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "nllb": "tam_Taml"},
    "bn": {"name": "Bengali", "native": "বাংলা", "nllb": "ben_Beng"},
    "mr": {"name": "Marathi", "native": "मराठी", "nllb": "mar_Deva"},
    "te": {"name": "Telugu", "native": "తెలుగు", "nllb": "tel_Telu"},
}

# Unicode blocks, used to detect the script when no language is declared.
_SCRIPT_RANGES = [
    ("hi", r"[ऀ-ॿ]"),  # Devanagari — also Marathi; see _detect note
    ("bn", r"[ঀ-৿]"),
    ("ta", r"[஀-௿]"),
    ("te", r"[ఀ-౿]"),
]

_model = None
_tokenizers: Dict[str, object] = {}
_load_lock = threading.Lock()
_load_failed = False


class TranslationUnavailable(Exception):
    """Translation could not run. Callers should fall back, not fail."""


def detect_language(text: str) -> str:
    """Best-effort language guess from the script used.

    Script identifies the writing system, not the language: Hindi and Marathi
    both use Devanagari and cannot be told apart this way, so Devanagari is
    reported as Hindi. When the user has picked a language explicitly, prefer
    that over this.
    """
    for code, pattern in _SCRIPT_RANGES:
        if re.search(pattern, text):
            return code
    return "en"


def _ensure_model():
    """Load the translator on first use. Never blocks the English path."""
    global _model, _load_failed

    if _model is not None:
        return _model
    if _load_failed:
        raise TranslationUnavailable("Translation model previously failed to load.")

    with _load_lock:
        if _model is not None:
            return _model
        try:
            from transformers import AutoModelForSeq2SeqLM

            logger.info("[Translation] Loading %s (first use only)...", _MODEL_NAME)
            _model = AutoModelForSeq2SeqLM.from_pretrained(_MODEL_NAME)
            logger.info("[Translation] Model ready.")
            return _model
        except Exception as exc:
            _load_failed = True
            logger.error("[Translation] Could not load %s: %s", _MODEL_NAME, exc)
            raise TranslationUnavailable(str(exc)) from exc


def _ensure_tokenizer(source_code: str):
    """One tokenizer per source language: NLLB sets src_lang at construction."""
    if source_code in _tokenizers:
        return _tokenizers[source_code]

    with _load_lock:
        if source_code in _tokenizers:
            return _tokenizers[source_code]
        try:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME, src_lang=source_code)
            _tokenizers[source_code] = tokenizer
            return tokenizer
        except Exception as exc:
            raise TranslationUnavailable(str(exc)) from exc


def translate_to_english(text: str, language: Optional[str] = None) -> dict:
    """Translate a query into English.

    Returns a dict with:
      text            the English text to search with
      original        what the user typed
      detected        language code used
      translated      whether translation actually ran
      error           why it did not, when applicable

    Never raises for an unavailable model: a failed translation degrades to
    searching the original text, which is worse than a translation but much
    better than an error page.
    """
    stripped = text.strip()
    if not stripped:
        return {"text": text, "original": text, "detected": "en", "translated": False, "error": None}

    code = language if language and language != "auto" else detect_language(stripped)
    entry = SUPPORTED_LANGUAGES.get(code)

    if entry is None or entry["nllb"] is None:
        # English, or a language we do not support: search as typed.
        return {"text": stripped, "original": text, "detected": "en", "translated": False, "error": None}

    try:
        model = _ensure_model()
        tokenizer = _ensure_tokenizer(entry["nllb"])

        encoded = tokenizer(stripped, return_tensors="pt", truncation=True, max_length=512)
        generated = model.generate(
            **encoded,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids("eng_Latn"),
            max_new_tokens=128,
        )
        english = tokenizer.decode(generated[0], skip_special_tokens=True).strip()

        if not english:
            raise TranslationUnavailable("Translator returned empty output.")

        return {
            "text": english,
            "original": text,
            "detected": code,
            "translated": True,
            "error": None,
        }

    except TranslationUnavailable as exc:
        logger.warning("[Translation] Falling back to untranslated query: %s", exc)
        return {
            "text": stripped,
            "original": text,
            "detected": code,
            "translated": False,
            "error": (
                "Translation is unavailable, so the query was searched as typed. "
                "Results are likely to be poor for non-English text."
            ),
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("[Translation] Unexpected failure: %s", exc, exc_info=True)
        return {
            "text": stripped,
            "original": text,
            "detected": code,
            "translated": False,
            "error": "Translation failed, so the query was searched as typed.",
        }
