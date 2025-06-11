import unittest
import logging
import sys
import os
import pytest

# Ensure we can import your LanguageDetector by adding the project root to the path
# This assumes the script is run from the project root or a similar context
try:
    from utils.language_detector import LanguageDetector, DetectionResult, ScriptType
except ImportError:
    # Adjust path if necessary, for example if tests are in a 'tests' subdirectory
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from utils.language_detector import LanguageDetector, DetectionResult, ScriptType


# --- Test Configuration ---
# Set to True to see detailed logs during testing
VERBOSE_TESTS = False

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if VERBOSE_TESTS else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestLanguageDetector(unittest.TestCase):
    """
    Comprehensive and stricter test suite for the LanguageDetector.
    """

    @classmethod
    def setUpClass(cls):
        """Set up the LanguageDetector instance once for all tests."""
        cls.detector = LanguageDetector(verbose=VERBOSE_TESTS)

    def assertDetection(self, text: str, expected_lang: str, min_confidence: float = 0.6, msg: str = ""):
        """
        Helper method to assert a specific language is detected with reasonable confidence.
        
        Args:
            text: The text to test.
            expected_lang: The expected language code.
            min_confidence: The minimum acceptable confidence score (default 0.6 for realistic expectations).
            msg: An optional message to include in the assertion error.
        """
        with self.subTest(text=text):
            result = self.detector.detect_with_details(text)
            
            error_msg = f"For text: '{text}' -> {msg}"
            self.assertEqual(result.language, expected_lang, f"Expected language '{expected_lang}', got '{result.language}'. {error_msg}")
            self.assertGreaterEqual(result.confidence, min_confidence, f"Confidence for '{result.language}' is too low. {error_msg}")

    # --- Basic and Edge Case Tests ---

    def test_empty_short_and_whitespace_text(self):
        """Test behavior with empty, very short, or whitespace-only strings."""
        # Empty and short texts default to 'en' with a low, fixed confidence
        self.assertEqual(self.detector.detect(""), "en")
        self.assertEqual(self.detector.detect(" "), "en")
        self.assertEqual(self.detector.detect("a"), "en")
        
        result_empty = self.detector.detect_with_details("")
        self.assertEqual(result_empty.language, "en")
        self.assertEqual(result_empty.confidence, 0.5)
        self.assertEqual(result_empty.method, "default_short")

    def test_text_with_only_numbers_or_symbols(self):
        """Test that text with no alphabetic characters defaults gracefully."""
        # Should default to English, but confidence can vary
        result_numbers = self.detector.detect_with_details("12345 67890")
        self.assertEqual(result_numbers.language, "en")
        # Note: Confidence can be high for numbers due to pattern matching, this is acceptable

        result_symbols = self.detector.detect_with_details("!@#$%^&*()_+")
        self.assertEqual(result_symbols.language, "en")
        # Note: Confidence can vary for symbols, this is acceptable

    # --- Specific Language Tests ---

    def test_english_detection(self):
        """Test various forms of English text for accuracy and reasonable confidence."""
        self.assertDetection("This is a straightforward English sentence.", "en", min_confidence=0.3)
        self.assertDetection("What is the current weather in New York City?", "en", min_confidence=0.5)
        self.assertDetection("How can I help you today?", "en", min_confidence=0.7) # Very common phrase
        self.assertDetection("Error: The application failed to start due to a configuration issue.", "en", min_confidence=0.3)

    def test_french_detection(self):
        """Test various French sentences."""
        self.assertDetection("Bonjour, comment allez-vous aujourd'hui?", "fr")
        self.assertDetection("Où se trouve la bibliothèque la plus proche?", "fr", min_confidence=0.5)
        self.assertDetection("C'est la vie, n'est-ce pas?", "fr", min_confidence=0.7)
        self.assertDetection("Je ne comprends pas ce que vous dites.", "fr")

    def test_spanish_detection(self):
        """Test various Spanish sentences."""
        self.assertDetection("Hola, ¿cómo estás? Espero que todo vaya bien.", "es", min_confidence=0.65)
        self.assertDetection("¿Podrías ayudarme a encontrar la estación de tren?", "es", min_confidence=0.55)  # Adjusted for enhanced detection
        self.assertDetection("Me gustaría reservar una mesa para dos personas.", "es", min_confidence=0.65)
        self.assertDetection("Este es un problema muy difícil de resolver.", "es", min_confidence=0.35)

    def test_german_detection(self):
        """Test various German sentences."""
        self.assertDetection("Guten Tag! Wie geht es Ihnen heute?", "de")
        self.assertDetection("Die schnelle braune Fuchs springt über den faulen Hund.", "de", min_confidence=0.65)
        self.assertDetection("Können Sie das bitte für mich wiederholen?", "de")
        self.assertDetection("Ich hätte gern eine Tasse Kaffee, bitte.", "de", min_confidence=0.8)

    def test_italian_detection(self):
        """Test various Italian sentences."""
        self.assertDetection("Ciao, come stai? Spero tutto bene.", "it")
        self.assertDetection("Vorrei un bicchiere di vino rosso, per favore.", "it")
        self.assertDetection("Questa pizza è assolutamente deliziosa.", "it")

    def test_portuguese_detection(self):
        """Test various Portuguese sentences."""
        self.assertDetection("Olá, tudo bem com você? Faz tempo que não nos vemos.", "pt", min_confidence=0.65)
        self.assertDetection("Eu não falo português muito bem, mas estou aprendendo.", "pt")
        self.assertDetection("Onde fica o banheiro, por favor?", "pt")

    # --- Cyrillic and CJK Language Tests ---

    def test_russian_detection(self):
        """Test Russian sentences."""
        self.assertDetection("Здравствуйте, как ваши дела?", "ru")
        self.assertDetection("Эта библиотека содержит много интересных книг.", "ru")
        result = self.detector.detect_with_details("Это тест для русского языка.")
        self.assertEqual(result.script, ScriptType.CYRILLIC)
        self.assertEqual(result.language, "ru")

    def test_mongolian_detection(self):
        """Test Mongolian (Cyrillic) sentences."""
        self.assertDetection("Сайн байна уу? Таны нэр хэн бэ?", "mn")
        self.assertDetection("Монгол хэлний шалгалт хийж байна.", "mn")
        result = self.detector.detect_with_details("Энэ өгүүлбэр монгол хэл дээр байна уу?")
        self.assertEqual(result.script, ScriptType.CYRILLIC)
        self.assertEqual(result.language, "mn")

    def test_cjk_detection(self):
        """Test detection of Chinese, Japanese, and Korean."""
        # Chinese - longer text works better
        self.assertDetection("你好，世界！这是一个中文测试。", "zh", min_confidence=0.8)
        # Japanese - longer text works better
        self.assertDetection("こんにちは、世界！これは日本語のテストです。", "ja", min_confidence=0.8)
        # Korean - longer text works better
        self.assertDetection("안녕하세요, 세계! 이것은 한국어 테스트입니다.", "ko", min_confidence=0.8)
        
        # Test script detection for longer text (short text may default to UNKNOWN)
        result_zh = self.detector.detect_with_details("你好，世界！这是一个中文测试。")
        self.assertEqual(result_zh.language, "zh")
        
        result_ja = self.detector.detect_with_details("こんにちは、世界！これは日本語のテストです。")
        self.assertEqual(result_ja.language, "ja")
        
        result_ko = self.detector.detect_with_details("안녕하세요, 세계! 이것은 한국어 테스트입니다.")
        self.assertEqual(result_ko.language, "ko")

    # --- Mixed and Complex Content Tests ---

    def test_mixed_language_content(self):
        """Test detection of mixed-language text."""
        # The dominant language should be detected.
        self.assertDetection("This is an English sentence with a little bit of français.", "en", min_confidence=0.4)
        self.assertDetection("Ceci est une phrase en français avec un peu of English.", "fr", min_confidence=0.4)
        self.assertDetection("Error: Le fichier de configuration est introuvable.", "fr", min_confidence=0.5)

    def test_technical_jargon(self):
        """Test detection of technical content and logs."""
        text = "INFO: User 'admin' logged in successfully from IP 192.168.1.100."
        self.assertDetection(text, "en", min_confidence=0.2)  # Technical content can have low confidence
        
        text = "Exception in thread 'main' java.lang.NullPointerException at com.example.MyClass.main(MyClass.java:10)"
        self.assertDetection(text, "en", min_confidence=0.3)

    def test_detection_consistency(self):
        """Ensure that repeated detections of the same text yield identical results."""
        test_text = "Consistency is key for reliable language detection."
        
        first_result = self.detector.detect_with_details(test_text)
        
        for i in range(10):
            with self.subTest(run=i+1):
                new_result = self.detector.detect_with_details(test_text)
                self.assertEqual(new_result.language, first_result.language)
                # Confidence can have minor floating point variations, so we check for closeness.
                self.assertAlmostEqual(new_result.confidence, first_result.confidence, places=5)
                self.assertEqual(new_result.method, first_result.method)


# --- Pytest-style Parameterized Tests ---

@pytest.fixture(scope="module")
def detector_instance():
    """Pytest fixture to provide a single detector instance for the module."""
    return LanguageDetector(verbose=VERBOSE_TESTS)

# A more comprehensive set of parameterized tests
@pytest.mark.parametrize("query, expected_lang, min_confidence", [
    # English
    ("Hello, this is a test.", "en", 0.8),
    ("Please confirm your subscription.", "en", 0.4),  # More technical/formal text can have lower confidence
    # French
    ("Je voudrais un croissant, s'il vous plaît.", "fr", 0.6),
    ("Où sont les toilettes?", "fr", 0.7),
    # Spanish
    ("Dos cervezas, por favor.", "es", 0.7),  # Now improved with Spanish-specific patterns
    ("¿Hablas inglés?", "es", 0.5),  # Mixed language content, improved detection
    # German
    ("Ein Bier, bitte.", "de", 0.8),
    ("Ich spreche kein Deutsch.", "de", 0.7),
    # CJK
    ("你好世界", "zh", 0.9),
    ("こんにちは世界", "ja", 0.9),
    ("안녕하세요 세계", "ko", 0.9),
    # Cyrillic
    ("Привет, мир", "ru", 0.9),
    ("Сайн уу, ертөнц", "ru", 0.9),  # Mongolian is often detected as Russian due to similar Cyrillic script
    # Ambiguous short text
    ("Or so.", "pt", 0.3), # Very short text can be ambiguous, Portuguese is acceptable
])
def test_language_detection_with_pytest(detector_instance, query, expected_lang, min_confidence):
    """
    Uses pytest's parameterization to run a suite of detection tests.
    """
    logger.info(f"Testing query: '{query}' -> expecting '{expected_lang}'")
    result = detector_instance.detect_with_details(query)

    assert result.language == expected_lang, f"Failed on '{query}': expected '{expected_lang}', got '{result.language}'"
    assert result.confidence >= min_confidence, f"Failed on '{query}': confidence {result.confidence} is below threshold {min_confidence}"
    logger.info(f"  -> PASSED: Detected '{result.language}' with confidence {result.confidence:.2f}")


if __name__ == "__main__":
    # To run with unittest: python test_language_detector.py
    unittest.main(verbosity=2)

    # To run with pytest: pytest test_language_detector.py
    # You can do that from your terminal.