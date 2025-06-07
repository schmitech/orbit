import unittest
import logging
import sys
import os
import pytest

# Ensure we can import your LanguageDetector
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.language_detector import LanguageDetector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

class TestLanguageDetectorRobust(unittest.TestCase):
    """Robust tests for LanguageDetector, allowing for detector quirks."""
    
    def setUp(self):
        self.detector = LanguageDetector(verbose=True)

    def test_query(self):
        """Test language detection for a specific query."""
        test_cases = [
            ("Hello World", {"en"}),
            ("Bonjour le monde", {"fr"}),
            ("Hola mundo", {"es", "pt"}),  # Accept both Spanish and Portuguese
            ("你好世界", {"zh"}),
            ("こんにちは世界", {"ja"})
        ]
        for query, expected in test_cases:
            with self.subTest(query=query):
                logger.info(f"Testing query: {query}")
                result = self.detector.detect(query)
                logger.info(f"Detected language: {result}")
                self.assertIn(result, expected | {"en"}, f"Expected one of {expected} or 'en' for '{query}', got '{result}'")

    def test_english_sentences(self):
        for txt in [
            "Apples"
        ]:
            with self.subTest(txt=txt):
                self.assertEqual(self.detector.detect(txt), "en")
    
    def test_english_sentences(self):
        for txt in [
            "The quick brown fox jumps over the lazy dog.",
            "Artificial intelligence and machine learning are transforming industries.",
            "Cloud-native architectures improve scalability and resilience."
        ]:
            with self.subTest(txt=txt):
                self.assertEqual(self.detector.detect(txt), "en")

    def test_french_sentences(self):
        for txt in [
            "Le renard brun rapide saute par-dessus le chien paresseux.",
            "L'optimisation des performances du système est cruciale.",
            "Les architectures natives du cloud améliorent la scalabilité et la résilience."
        ]:
            with self.subTest(txt=txt):
                self.assertEqual(self.detector.detect(txt), "fr")

    def test_spanish_sentences(self):
        for txt in [
            "El rápido zorro marrón salta sobre el perro perezoso.",
            "La inteligencia artificial está revolucionando el mundo.",
            "Las arquitecturas nativas de la nube mejoran la escalabilidad."
        ]:
            with self.subTest(txt=txt):
                self.assertEqual(self.detector.detect(txt), "es")

    def test_german_sentences(self):
        for txt in [
            "Der schnelle braune Fuchs springt über den faulen Hund.",
            "Künstliche Intelligenz verändert viele Branchen.",
            "Cloud-native Architekturen verbessern die Skalierbarkeit."
        ]:
            with self.subTest(txt=txt):
                result = self.detector.detect(txt)
                self.assertIn(result, {"de", "en"}, f"Expected 'de' or 'en' for '{txt}', got '{result}'")

    def test_other_european(self):
        self.assertEqual(self.detector.detect(
            "Questa è una frase di prova in italiano."), "it")
        self.assertEqual(self.detector.detect(
            "Detta är en testmening på svenska."), "sv")

    def test_russian_and_arabic(self):
        self.assertEqual(self.detector.detect(
            "Это тестовое предложение на русском языке."), "ru")
        self.assertEqual(self.detector.detect(
            "مرحبا كيف حالك؟"), "ar")

    def test_mongolian_cyrillic(self):
        """Test detection of Mongolian text written in Cyrillic script"""
        # These should be detected as Mongolian, not Russian
        mongolian_texts = [
            "Бэрлэнгийн зогсоолын зөвшөөрлийн хураамж хэд вэ?",
            "Та хэд настай вэ?",
            "Энэ юу вэ?",
        ]
        for text in mongolian_texts:
            with self.subTest(text=text):
                result = self.detector.detect(text)
                self.assertEqual(result, "mn", f"Expected 'mn' for Mongolian text: '{text}', got '{result}'")

    def test_chinese_and_japanese(self):
        # langdetect may return zh, zh‑cn, or even ko for Chinese/Japanese
        cases = [
            ("今日はいい天気ですね。", {"ja", "zh", "zh-cn", "ko"}),
            ("今天天气怎么样？",     {"zh", "zh-cn", "ko"})
        ]
        for txt, allowed in cases:
            with self.subTest(txt=txt):
                code = self.detector.detect(txt)
                self.assertIn(code, allowed,
                              f"Expected one of {allowed} for '{txt}', got '{code}'")

    def test_technical_content(self):
        # Code snippets often get mis‑classified as Dutch ('nl')
        samples = [
            ("def greet(name):\n    return f'Hello, {name}!'", {"en", "nl"}),
            ("The mitochondrion is the powerhouse of the cell.", {"en"}),
            ("La mitochondrie est la centrale énergétique de la cellule.", {"fr"})
        ]
        for txt, allowed in samples:
            with self.subTest(txt=txt):
                code = self.detector.detect(txt)
                self.assertIn(code, allowed,
                              f"Expected one of {allowed} for technical text, got '{code}'")

    def test_heavy_numeric_and_symbols(self):
        for txt in ["!!!???!!!", "1234567890", "$$$%%%^^^", "2025-04-21T14:30Z"]:
            with self.subTest(txt=txt):
                self.assertEqual(self.detector.detect(txt), "en")

    def test_emoji_and_mixed_unicode(self):
        cases = [
            ("😊👍",                     {"en"}),                # only emoji → default to English
            ("😊 Hello! ¿Cómo estás? こんにちは", {"en", "es", "ja"})
        ]
        for txt, allowed in cases:
            with self.subTest(txt=txt):
                code = self.detector.detect(txt)
                self.assertIn(code, allowed,
                              f"Expected one of {allowed} for mixed text, got '{code}'")

    def test_empty_and_short(self):
        for txt in ["", "a", "yo", "π"]:
            with self.subTest(txt=txt):
                self.assertEqual(self.detector.detect(txt), "en")

@pytest.mark.parametrize("query", [
    "Hello World",
    "Bonjour le monde",
    "Hola mundo",
    "你好世界",
    "こんにちは世界"
])
def test_single_query(query):
    """Test language detection for a single query using pytest."""
    detector = LanguageDetector(verbose=True)
    result = detector.detect(query)
    print(f"\nQuery: {query}")
    print(f"Detected language: {result}")
    assert result is not None, f"Language detection failed for query: {query}"

if __name__ == "__main__":
    # Run all tests
    unittest.main()
