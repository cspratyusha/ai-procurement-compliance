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

    def test_detects_the_other_scheduled_languages(self):
        cases = [
            ("ઘર માટે તાંબાનો વાયર", "gu"),
            ("ಸೀಲಿಂಗ್ ಫ್ಯಾನ್", "kn"),
            ("കുടിവെള്ളത്തിന്റെ ഗുണനിലവാരം", "ml"),
            ("ਘਰ ਲਈ ਤਾਂਬੇ ਦੀ ਤਾਰ", "pa"),
            ("ଘର ପାଇଁ ତମ୍ବା ତାର", "or"),
            ("گھر کے لیے تانبے کی تار", "ur"),
        ]
        for text, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(translation.detect_language(text), expected)

    def test_marathi_is_told_from_hindi_by_its_own_words(self):
        """Both are written in Devanagari; 'saathi' (for) and 'aani' (and) are Marathi."""
        self.assertEqual(translation.detect_language("दुचाकीस्वारांसाठी हेल्मेट"), "mr")
        self.assertEqual(translation.detect_language("घरासाठी तांबे आणि पितळेच्या तारा"), "mr")
        self.assertEqual(translation.detect_language("दोपहिया वाहन चालकों के लिए हेलमेट"), "hi")

    def test_assamese_is_told_from_bengali_by_its_own_letters(self):
        self.assertEqual(translation.detect_language("ঘৰৰ বাবে তাঁৰ"), "as")
        self.assertEqual(translation.detect_language("বাড়ির জন্য তার"), "bn")

    def test_a_script_no_language_here_uses_is_unsupported_not_english(self):
        self.assertEqual(translation.detect_language("ගෙදර සඳහා වයර්"), translation.UNSUPPORTED)   # Sinhala
        self.assertEqual(translation.detect_language("家用铜线"), translation.UNSUPPORTED)
        self.assertEqual(translation.detect_language("café wiring"), "en")                    # Latin accents


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

    def test_an_unsupported_script_says_so_instead_of_a_silent_no_match(self):
        with patch.object(translation, "_ensure_model") as ensure:
            result = translation.translate_to_english("ගෙදර සඳහා වයර්")
            ensure.assert_not_called()
        self.assertEqual(result["detected"], translation.UNSUPPORTED)
        self.assertIn("not supported", result["error"])
        self.assertIn("Gujarati", result["error"])          # it names what is supported

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


class TestGlossary:
    """Procurement words replaced by their English trade name before translating."""

    def test_the_longest_phrase_wins_and_whole_words_only(self):
        text, used = translation.apply_glossary("छत का पंखा और तारीख", "hi")
        assert text.startswith("ceiling fan ")
        assert "तारीख" in text          # "तार" (wire) inside "तारीख" (date) is not replaced
        assert used == ["ceiling fan"]

    def test_a_word_is_replaced_only_for_its_own_language(self):
        assert translation.apply_glossary("सरिया", "mr")[0] == "सरिया"
        assert translation.apply_glossary("सरिया", "hi")[0] == "steel reinforcement bars"

    def test_it_can_be_switched_off(self, monkeypatch):
        monkeypatch.setenv("TRANSLATION_GLOSSARY", "0")
        assert translation.apply_glossary("छत का पंखा", "hi") == ("छत का पंखा", [])

    def test_a_query_made_only_of_glossary_words_needs_no_translator(self, monkeypatch):
        def no_model():
            raise AssertionError("the translator must not be loaded")
        monkeypatch.setattr(translation, "_ensure_model", no_model)
        result = translation.translate_to_english("छत का पंखा")
        assert result["text"] == "ceiling fan" and result["detected"] == "hi" and result["translated"]
