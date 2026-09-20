"""Tests for non-English query handling.

The model itself is not under test here. What matters is that the wiring is
right: that a non-English query is detected, that English is left alone, and
above all that a translation failure degrades to searching the original text
rather than returning an error page.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import translation  # noqa: E402


class TestLanguageDetection(unittest.TestCase):
    def test_detects_indian_scripts(self):
        cases = [
            ("घर की वायरिंग के लिए तांबे का तार", "hi"),
            ("குடிநீர் விநியோகத்திற்கான எஃகு குழாய்", "ta"),
            ("শ্রমিকদের জন্য নিরাপত্তা হেলমেট", "bn"),
            ("తెలుగు లో ప్రశ్న", "te"),
        ]
        for text, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(translation.detect_language(text), expected)

    def test_english_is_detected_as_english(self):
        self.assertEqual(
            translation.detect_language("copper wire for house wiring"), "en"
        )

    def test_mixed_script_follows_the_indian_script(self):
        """Procurement text mixes scripts: 'IS 694 के लिए तांबे का तार'."""
        self.assertEqual(translation.detect_language("IS 694 के लिए तांबे का तार"), "hi")


class TestTranslationRouting(unittest.TestCase):
    def test_english_is_not_sent_to_the_translator(self):
        """English must not pay the cost of loading a translation model."""
        with patch.object(translation, "_ensure_model") as ensure:
            result = translation.translate_to_english("copper wire for wiring")
            ensure.assert_not_called()
        self.assertFalse(result["translated"])
        self.assertEqual(result["detected"], "en")
        self.assertEqual(result["text"], "copper wire for wiring")

    def test_empty_query_is_passed_through(self):
        result = translation.translate_to_english("   ")
        self.assertFalse(result["translated"])

    def test_explicit_language_overrides_script_detection(self):
        """Devanagari serves both Hindi and Marathi; the user's choice wins."""
        with patch.object(translation, "_ensure_model", side_effect=translation.TranslationUnavailable("stub")):
            result = translation.translate_to_english("पोर्टलँड सिमेंट", language="mr")
        self.assertEqual(result["detected"], "mr")

    def test_translation_failure_degrades_instead_of_raising(self):
        """A dead translator must not take the search down with it.

        Falling back to the untranslated query gives poor results; returning
        an error gives none. Poor and explained beats broken.
        """
        with patch.object(
            translation, "_ensure_model",
            side_effect=translation.TranslationUnavailable("model unavailable"),
        ):
            result = translation.translate_to_english("तांबे का तार", language="hi")

        self.assertFalse(result["translated"])
        self.assertEqual(result["text"], "तांबे का तार")
        self.assertIsNotNone(result["error"])
        self.assertIn("unavailable", result["error"].lower())

    def test_unsupported_language_is_searched_as_typed(self):
        result = translation.translate_to_english("bonjour le monde", language="fr")
        self.assertFalse(result["translated"])
        self.assertEqual(result["text"], "bonjour le monde")

    def test_supported_languages_are_well_formed(self):
        """Every entry needs a display name and, unless English, an NLLB code."""
        self.assertIn("en", translation.SUPPORTED_LANGUAGES)
        for code, entry in translation.SUPPORTED_LANGUAGES.items():
            with self.subTest(code=code):
                self.assertTrue(entry["name"])
                self.assertTrue(entry["native"])
                if code != "en":
                    self.assertTrue(entry["nllb"], f"{code} needs an NLLB code")


if __name__ == "__main__":
    unittest.main()
