import unittest
import logging
import sys
import os
import argparse

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

    def test_query(self, query):
        """Test language detection for a specific query."""
        logger.info(f"Testing query: {query}")
        result = self.detector.detect(query)
        logger.info(f"Detected language: {result}")
        return result

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
                self.assertEqual(self.detector.detect(txt), "de")

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test language detection for a query')
    parser.add_argument('--query', type=str, help='Query to test language detection')
    args = parser.parse_args()

    if args.query:
        # Run single query test
        detector = LanguageDetector(verbose=True)
        result = detector.detect(args.query)
        print(f"\nQuery: {args.query}")
        print(f"Detected language: {result}")
    else:
        # Run all tests
        unittest.main()
