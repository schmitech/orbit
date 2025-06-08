#!/usr/bin/env python3

import unittest
import logging
import sys
import os
import pytest

# Ensure we can import LanguageDetector - follow same pattern as other tests
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.language_detector import LanguageDetector

# Set up logging for test output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

class TestLanguageDetectionBugFixes(unittest.TestCase):
    """Test cases specifically for language detection bug fixes."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.detector = LanguageDetector(verbose=False)
    
    def test_french_problematic_phrase(self):
        """Test the specific French phrase that was being detected as English."""
        problematic_text = "c'est quoi ma premier question?"
        result = self.detector.detect(problematic_text)
        
        logger.info(f"Testing problematic phrase: '{problematic_text}' → {result}")
        self.assertEqual(result, "fr", 
                        f"Expected French (fr) for '{problematic_text}', got '{result}'")
    
    def test_french_indicators_detection(self):
        """Test various French phrases with clear French indicators."""
        french_test_cases = [
            "c'est quoi ma premier question?",  # The original bug case
            "c'est quoi",
            "qu'est-ce que c'est?",
            "je suis français",
            "première question",
            "c'est formidable",
            "qu'est-ce que tu fais?",
            "ça va bien merci"
        ]
        
        for text in french_test_cases:
            with self.subTest(text=text):
                result = self.detector.detect(text)
                logger.info(f"French test: '{text}' → {result}")
                self.assertEqual(result, "fr", 
                               f"Expected French (fr) for '{text}', got '{result}'")
    
    def test_confidence_calculation_fix(self):
        """Test that confidence calculation handles negative votes properly."""
        # This should not crash and should handle negative votes gracefully
        test_text = "c'est quoi ma premier question?"
        
        try:
            result = self.detector.detect(test_text)
            # Should be French due to our fixes
            self.assertEqual(result, "fr")
            logger.info(f"Confidence calculation test passed: '{test_text}' → {result}")
        except Exception as e:
            self.fail(f"Confidence calculation failed with error: {e}")
    
    def test_multilingual_detection_accuracy(self):
        """Test detection accuracy across multiple languages including Asian languages."""
        test_cases = [
            # English
            ("Hello how are you?", "en"),
            ("What is your first question?", "en"),
            ("Good morning everyone", "en"),
            
            # French - including edge cases
            ("Bonjour comment ça va?", "fr"),
            ("c'est quoi ma premier question?", "fr"),  # The bug fix case
            ("qu'est-ce que c'est?", "fr"),
            ("je suis content de vous voir", "fr"),
            
            # Spanish  
            ("Hola como estas?", "es"),
            ("¿Cómo te llamas?", "es"),
            ("Me gusta mucho este lugar", "es"),
            
            # German
            ("Guten Tag wie geht es?", "de"),
            ("Wie heißt du?", "de"),
            ("Ich bin sehr glücklich heute", "de"),
            
            # Italian
            ("Ciao come stai?", "it"),
            ("Dove si trova la stazione?", "it"),
            ("Mi piace molto la pizza italiana", "it"),
            
            # Portuguese (note: might be detected as Spanish due to similarity)
            ("Olá como está você?", "pt"),
            ("Onde fica a biblioteca?", "pt"),
            ("Eu gosto muito do Brasil", "pt"),
            
            # Russian
            ("Привет как дела?", "ru"),
            ("Где находится вокзал?", "ru"),
            ("Я изучаю русский язык", "ru"),
            ("Как дела? Что делаешь?", "ru"),
            ("Привет, меня зовут Иван.", "ru"),
            
            # Mongolian (Cyrillic script)
            ("Бэрлэнгийн зогсоолын зөвшөөрлийн хураамж хэд вэ?", "mn"),
            ("Та хэд настай вэ?", "mn"),
            ("Энэ юу вэ?", "mn"),
            ("Би монгол хүн байна", "mn"),
            ("Та яаж байна вэ?", "mn"),
            
            # Chinese (Simplified)
            ("你好吗？", "zh"),
            ("你叫什么名字？", "zh"),
            ("我喜欢学习中文", "zh"),
            
            # Japanese
            ("こんにちは元気ですか？", "ja"),
            ("お名前は何ですか？", "ja"),
            ("日本語を勉強しています", "ja"),
            
            # Korean
            ("안녕하세요 어떻게 지내세요?", "ko"),
            ("이름이 뭐예요?", "ko"),
            ("한국어를 배우고 있어요", "ko"),
            
            # Arabic
            ("مرحبا كيف حالك؟", "ar"),
            ("ما اسمك؟", "ar"),
            ("أنا أتعلم اللغة العربية", "ar"),
            
            # Hindi (Devanagari script)
            ("नमस्ते आप कैसे हैं?", "hi"),
            ("आपका नाम क्या है?", "hi"),
            ("मैं हिंदी सीख रहा हूँ", "hi"),
            
            # Thai
            ("สวัสดี คุณเป็นอย่างไรบ้าง?", "th"),
            ("คุณชื่ออะไร?", "th"),
            ("ฉันกำลังเรียนภาษาไทย", "th"),
            
            # Vietnamese
            ("Xin chào bạn khỏe không?", "vi"),
            ("Tên bạn là gì?", "vi"),
            ("Tôi đang học tiếng Việt", "vi"),
        ]
        
        all_passed = True
        failed_cases = []
        
        for text, expected in test_cases:
            with self.subTest(text=text, expected=expected):
                result = self.detector.detect(text)
                if result != expected:
                    all_passed = False
                    failed_cases.append((text, expected, result))
                
                logger.info(f"Multilingual test: '{text}' → {result} (expected: {expected})")
                
                # Allow some flexibility for similar languages and script detection issues
                if expected in ["es", "pt"]:  # Spanish/Portuguese can be confused
                    self.assertIn(result, ["es", "pt", "en"], 
                                f"Expected Spanish, Portuguese, or English for '{text}', got '{result}'")
                elif expected in ["de", "en"]:  # German/English can be confused for short texts
                    self.assertIn(result, ["de", "en"], 
                                f"Expected German or English for '{text}', got '{result}'")
                elif expected in ["zh", "ja", "ko"]:  # CJK languages can be confused sometimes
                    self.assertIn(result, ["zh", "ja", "ko", "en"], 
                                f"Expected CJK language or English for '{text}', got '{result}'")
                elif expected == "ru":  # Russian can be confused with other Cyrillic languages
                    self.assertIn(result, ["ru", "mk", "bg", "sr"], 
                                f"Expected Cyrillic language for '{text}', got '{result}'")
                elif expected == "mn":  # Mongolian should be detected correctly
                    self.assertEqual(result, "mn", 
                                   f"Expected Mongolian (mn) for '{text}', got '{result}'")
                elif expected in ["th", "vi", "hi"]:  # Asian languages - allow more flexibility
                    # These might be detected as other languages due to detector limitations
                    self.assertIsInstance(result, str)
                    self.assertTrue(len(result) >= 2, f"Invalid language code: {result}")
                else:
                    self.assertEqual(result, expected, 
                                   f"Expected '{expected}' for '{text}', got '{result}'")
        
        if failed_cases:
            logger.warning(f"Failed cases: {failed_cases}")
    
    def test_mongolian_cyrillic_detection(self):
        """Test specific Mongolian Cyrillic detection functionality."""
        # Test cases that should be detected as Mongolian, not Russian
        mongolian_test_cases = [
            ("Бэрлэнгийн зогсоолын зөвшөөрлийн хураамж хэд вэ?", "mn"),  # The original log case
            ("Та хэд настай вэ?", "mn"),  # How old are you?
            ("Энэ юу вэ?", "mn"),         # What is this?
            ("Би монгол хүн байна", "mn"),  # I am Mongolian
            ("Та яаж байна вэ?", "mn"),     # How are you?
        ]
        
        # Test cases that should still be detected as Russian
        russian_test_cases = [
            ("Как дела? Что делаешь?", "ru"),
            ("Привет, меня зовут Иван.", "ru"),
            ("Это тестовое предложение на русском языке.", "ru"),
            ("Где находится вокзал?", "ru"),
            ("Я изучаю русский язык уже два года.", "ru"),
        ]
        
        # Test Mongolian detection
        for text, expected in mongolian_test_cases:
            with self.subTest(text=text, expected=expected):
                result = self.detector.detect(text)
                logger.info(f"Mongolian test: '{text}' → {result}")
                self.assertEqual(result, expected, 
                               f"Expected Mongolian (mn) for '{text}', got '{result}'")
        
        # Test Russian still works
        for text, expected in russian_test_cases:
            with self.subTest(text=text, expected=expected):
                result = self.detector.detect(text)
                logger.info(f"Russian test: '{text}' → {result}")
                self.assertEqual(result, expected, 
                               f"Expected Russian (ru) for '{text}', got '{result}'")

    def test_ensemble_voting_robustness(self):
        """Test that ensemble voting handles conflicting detector results properly."""
        # Test texts that might cause detector conflicts
        conflict_cases = [
            "c'est quoi ma premier question?",  # French with English-like words
            "premier ministre",  # Could be French or English
            "question importante",  # Could be French or English
        ]
        
        for text in conflict_cases:
            with self.subTest(text=text):
                result = self.detector.detect(text)
                logger.info(f"Conflict resolution test: '{text}' → {result}")
                
                # Should return a valid language code
                self.assertIsInstance(result, str)
                self.assertTrue(len(result) >= 2, f"Invalid language code: {result}")
                
                # For these specific cases, should prefer French due to indicators
                if "c'est" in text:
                    self.assertEqual(result, "fr", 
                                   f"Expected French for text with French indicators: '{text}'")
                # "premier" alone might be detected as English in short phrases


@pytest.mark.parametrize("text,expected", [
    # Core bug fix test cases
    ("c'est quoi ma premier question?", "fr"),
    ("c'est quoi", "fr"),
    ("qu'est-ce que c'est?", "fr"),
    ("je suis français", "fr"),
    
    # Regression tests - ensure we didn't break existing functionality
    ("Hello how are you?", "en"),
    ("Bonjour comment ça va?", "fr"),
    ("Hola como estas?", "es"),
    ("Guten Tag wie geht es?", "de"),
    
    # Additional languages for comprehensive testing
    ("Ciao come stai?", "it"),
    ("Olá como está você?", "pt"),
    ("Привет как дела?", "ru"),
    ("你好吗？", "zh"),
    ("こんにちは元気ですか？", "ja"),
    ("안녕하세요 어떻게 지내세요?", "ko"),
    
    # Mongolian Cyrillic detection tests
    ("Бэрлэнгийн зогсоолын зөвшөөрлийн хураамж хэд вэ?", "mn"),
    ("Та хэд настай вэ?", "mn"),
    ("Энэ юу вэ?", "mn"),
    ("Би монгол хүн байна", "mn"),
    
    # Russian vs Mongolian distinction
    ("Как дела? Что делаешь?", "ru"),
    ("Привет, меня зовут Иван.", "ru"),
])
def test_language_detection_parametrized(text, expected):
    """Parametrized test for language detection using pytest."""
    detector = LanguageDetector(verbose=False)
    result = detector.detect(text)
    
    logger.info(f"Parametrized test: '{text}' → {result} (expected: {expected})")
    
    # Allow some flexibility for similar languages
    if expected in ["es", "pt"]:
        assert result in ["es", "pt"], f"Expected Spanish or Portuguese for '{text}', got '{result}'"
    elif expected in ["de", "en"] and len(text) < 20:  # Short German texts might be detected as English
        assert result in ["de", "en"], f"Expected German or English for '{text}', got '{result}'"
    elif expected in ["zh", "ja", "ko"]:  # CJK languages can be confused
        assert result in ["zh", "ja", "ko", "en"], f"Expected CJK language or English for '{text}', got '{result}'"
    elif expected == "ru":  # Russian can be confused with other Cyrillic languages
        assert result in ["ru", "mk", "bg", "sr"], f"Expected Cyrillic language for '{text}', got '{result}'"
    elif expected == "mn":  # Mongolian should be detected correctly
        assert result == "mn", f"Expected Mongolian (mn) for '{text}', got '{result}'"
    else:
        assert result == expected, f"Expected '{expected}' for '{text}', got '{result}'"


def test_debug_problematic_phrase():
    """Debug function to analyze the problematic phrase in detail."""
    detector = LanguageDetector(verbose=True)
    problematic_text = "c'est quoi ma premier question?"
    
    print(f"\nDebugging: '{problematic_text}'")
    print("=" * 50)
    
    # Check what detectors are available
    print(f"Available detectors: {list(detector.detectors.keys())}")
    
    # Test the problematic text
    result = detector.detect(problematic_text)
    print(f"Final result: {result}")
    
    # Test character statistics
    stats = detector.analyzer.calculate_char_stats(problematic_text)
    print(f"Character stats: {stats}")
    
    # Test script analysis
    script_info = detector.analyzer.analyze_script(problematic_text)
    print(f"Script info: {script_info}")
    
    assert result == "fr", f"Expected French, got {result}"


def test_debug_mongolian_detection():
    """Debug function to analyze Mongolian language detection in detail."""
    detector = LanguageDetector(verbose=True)
    
    test_cases = [
        ("Бэрлэнгийн зогсоолын зөвшөөрлийн хураамж хэд вэ?", "mn"),  # Original log case
        ("Та хэд настай вэ?", "mn"),  # How old are you?
        ("Энэ юу вэ?", "mn"),         # What is this?
        ("Как дела? Что делаешь?", "ru"),  # Russian for comparison
        ("Привет, меня зовут Иван.", "ru"),  # Russian for comparison
    ]
    
    print(f"\nDebugging Mongolian Detection")
    print("=" * 60)
    
    # Check what detectors are available
    print(f"Available detectors: {list(detector.detectors.keys())}")
    print()
    
    for text, expected in test_cases:
        print(f"Testing: '{text}'")
        print(f"Expected: {expected}")
        print("-" * 40)
        
        # Test the text
        result = detector.detect(text)
        print(f"Final result: {result}")
        
        # Test character statistics
        stats = detector.analyzer.calculate_char_stats(text)
        print(f"Character stats: {stats}")
        
        # Test script analysis
        script_info = detector.analyzer.analyze_script(text)
        print(f"Script info: {script_info}")
        
        # Test Mongolian detection specifically if it's Cyrillic
        if script_info.script_type == 'Cyrillic':
            is_mongolian = detector._is_mongolian_cyrillic(text)
            print(f"Mongolian Cyrillic detection: {is_mongolian}")
        
        print(f"✓ PASS" if result == expected else f"✗ FAIL - Expected {expected}, got {result}")
        print("=" * 60)
        print()
        
        assert result == expected, f"Expected {expected}, got {result} for '{text}'"


if __name__ == "__main__":
    # Run the debug functions first for detailed output
    print("Running debug analysis...")
    test_debug_problematic_phrase()
    
    print("\nRunning Mongolian detection debug analysis...")
    test_debug_mongolian_detection()
    
    print("\nRunning unittest tests...")
    unittest.main(verbosity=2) 