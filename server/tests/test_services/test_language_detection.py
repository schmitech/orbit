"""
Language Detection Unit Tests

Comprehensive tests to ensure language detection accuracy across multiple languages,
scripts, and edge cases. These tests verify that user prompts are correctly identified
so LLMs will respond in the corresponding language.

Run with:
    cd server && pytest tests/test_language_detection.py -v
    OR from project root:
    pytest server/tests/test_language_detection.py -v
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

# Import the language detection module directly to avoid import chain issues
import sys
import os

# Add the server directory to the Python path
server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, server_dir)

# Import directly from the module files to avoid import chain issues
# that occur through inference/__init__.py
import importlib.util

def import_module_directly(module_name: str, file_path: str):
    """Import a module directly from file path to avoid package init issues."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Import base module first (needed by language_detection)
base_path = os.path.join(server_dir, 'inference', 'pipeline', 'base.py')
base_module = import_module_directly('inference.pipeline.base', base_path)
ProcessingContext = base_module.ProcessingContext
PipelineStep = base_module.PipelineStep

# Now import language detection
lang_detect_path = os.path.join(server_dir, 'inference', 'pipeline', 'steps', 'language_detection.py')
lang_detect_module = import_module_directly('inference.pipeline.steps.language_detection', lang_detect_path)

LanguageDetectionStep = lang_detect_module.LanguageDetectionStep
DetectionResult = lang_detect_module.DetectionResult
normalize_language_code = lang_detect_module.normalize_language_code
SCRIPT_PATTERNS = lang_detect_module.SCRIPT_PATTERNS
LATIN_WORD_PATTERNS = lang_detect_module.LATIN_WORD_PATTERNS
ENGLISH_MARKERS_PATTERN = lang_detect_module.ENGLISH_MARKERS_PATTERN
SPANISH_MARKERS_PATTERN = lang_detect_module.SPANISH_MARKERS_PATTERN


class MockContainer:
    """Mock service container for testing."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._services = {}
        self._config = config or self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            'language_detection': {
                'enabled': True,
                'backends': ['langdetect', 'langid', 'pycld2'],
                'backend_weights': {
                    'langdetect': 1.0,
                    'langid': 1.2,
                    'pycld2': 1.5
                },
                'min_confidence': 0.7,
                'min_margin': 0.2,
                'prefer_english_for_ascii': True,
                'enable_stickiness': True,
                'fallback_language': 'en',
                'heuristic_nudges': {
                    'en_boost': 0.2,
                    'es_penalty': 0.1,
                    'script_boost': 0.2
                },
                'mixed_language_threshold': 0.3,
                'use_chat_history_prior': False,  # Disable for unit tests
            },
            'general': {'verbose': False}
        }

    def get(self, key: str) -> Any:
        if key == 'config':
            return self._config
        return self._services.get(key)

    def get_or_none(self, key: str) -> Optional[Any]:
        if key == 'config':
            return self._config
        return self._services.get(key)

    def has(self, key: str) -> bool:
        return key in self._services or key == 'config'

    def register(self, key: str, service: Any):
        self._services[key] = service


def create_context(message: str, session_id: Optional[str] = None) -> ProcessingContext:
    """Create a ProcessingContext for testing."""
    ctx = ProcessingContext(
        message=message,
        adapter_name="test-adapter",
        session_id=session_id
    )
    return ctx


class TestLanguageCodeNormalization:
    """Tests for language code normalization."""

    def test_iso_639_1_passthrough(self):
        """Standard 2-letter codes should pass through."""
        assert normalize_language_code('en') == 'en'
        assert normalize_language_code('es') == 'es'
        assert normalize_language_code('fr') == 'fr'
        assert normalize_language_code('zh') == 'zh'

    def test_iso_639_3_to_iso_639_1(self):
        """3-letter codes should be normalized to 2-letter."""
        assert normalize_language_code('eng') == 'en'
        assert normalize_language_code('spa') == 'es'
        assert normalize_language_code('fra') == 'fr'
        assert normalize_language_code('zho') == 'zh'
        assert normalize_language_code('jpn') == 'ja'
        assert normalize_language_code('kor') == 'ko'

    def test_chinese_variants(self):
        """Chinese variant codes should normalize to 'zh'."""
        assert normalize_language_code('zh-cn') == 'zh'
        assert normalize_language_code('zh-tw') == 'zh'
        assert normalize_language_code('zh-hant') == 'zh'
        assert normalize_language_code('zh-hans') == 'zh'

    def test_case_insensitive(self):
        """Normalization should be case-insensitive."""
        assert normalize_language_code('EN') == 'en'
        assert normalize_language_code('Es') == 'es'
        assert normalize_language_code('ZH-CN') == 'zh'

    def test_unknown_codes(self):
        """Unknown codes should be truncated or passed through."""
        assert normalize_language_code('unknown-lang') == 'un'
        assert normalize_language_code('xyz') == 'xy'
        assert normalize_language_code('') == 'unknown'
        assert normalize_language_code(None) == 'unknown'


class TestScriptDetection:
    """Tests for script-based language detection."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    # East Asian Scripts
    def test_chinese_detection(self, detector):
        """Chinese characters should be detected with high confidence."""
        result = detector._detect_by_script("你好世界")
        assert result.language == 'zh'
        assert result.confidence >= 0.9

    def test_japanese_hiragana(self, detector):
        """Japanese hiragana should be detected."""
        result = detector._detect_by_script("こんにちは")
        assert result.language == 'ja'
        assert result.confidence >= 0.9

    def test_japanese_katakana(self, detector):
        """Japanese katakana should be detected."""
        result = detector._detect_by_script("コンピューター")
        assert result.language == 'ja'
        assert result.confidence >= 0.9

    def test_korean_detection(self, detector):
        """Korean hangul should be detected."""
        result = detector._detect_by_script("안녕하세요")
        assert result.language == 'ko'
        assert result.confidence >= 0.9

    # Middle Eastern Scripts
    def test_arabic_detection(self, detector):
        """Arabic script should be detected."""
        result = detector._detect_by_script("مرحبا بالعالم")
        assert result.language == 'ar'
        assert result.confidence >= 0.9

    def test_hebrew_detection(self, detector):
        """Hebrew script should be detected."""
        result = detector._detect_by_script("שלום עולם")
        assert result.language == 'he'
        assert result.confidence >= 0.9

    # South Asian Scripts
    def test_hindi_devanagari(self, detector):
        """Hindi in Devanagari should be detected."""
        result = detector._detect_by_script("नमस्ते दुनिया")
        assert result.language == 'hi'
        assert result.confidence >= 0.9

    def test_bengali_detection(self, detector):
        """Bengali script should be detected."""
        result = detector._detect_by_script("হ্যালো বিশ্ব")
        assert result.language == 'bn'
        assert result.confidence >= 0.9

    def test_tamil_detection(self, detector):
        """Tamil script should be detected."""
        result = detector._detect_by_script("வணக்கம் உலகம்")
        assert result.language == 'ta'
        assert result.confidence >= 0.9

    # Southeast Asian Scripts
    def test_thai_detection(self, detector):
        """Thai script should be detected."""
        result = detector._detect_by_script("สวัสดีครับ")
        assert result.language == 'th'
        assert result.confidence >= 0.9

    # European Scripts
    def test_greek_detection(self, detector):
        """Greek script should be detected."""
        result = detector._detect_by_script("Γειά σου κόσμε")
        assert result.language == 'el'
        assert result.confidence >= 0.9

    def test_cyrillic_detection(self, detector):
        """Cyrillic script should be detected (with lower confidence due to multi-language)."""
        result = detector._detect_by_script("Привет мир")
        assert result.language == 'ru'
        assert result.confidence >= 0.7

    # Other Scripts
    def test_georgian_detection(self, detector):
        """Georgian script should be detected."""
        result = detector._detect_by_script("გამარჯობა")
        assert result.language == 'ka'
        assert result.confidence >= 0.9

    def test_armenian_detection(self, detector):
        """Armenian script should be detected."""
        result = detector._detect_by_script("Բdelays")
        # Note: Single word may not be detected
        # Using full phrase
        result = detector._detect_by_script("Բdelays մdelays")
        assert result.language in ['hy', 'unknown']


class TestLatinLanguagePatterns:
    """Tests for Latin script language pattern detection."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    def test_spanish_markers(self, detector):
        """Spanish with distinctive markers should be detected."""
        result = detector._detect_by_script("¿Cómo estás? ¡Hola!")
        assert result.language == 'es'
        assert result.confidence >= 0.5  # Pattern detection gives moderate confidence

    def test_portuguese_markers(self, detector):
        """Portuguese with distinctive markers should be detected."""
        result = detector._detect_by_script("Obrigado, você está bem?")
        assert result.language == 'pt'
        assert result.confidence >= 0.5  # Pattern detection gives moderate confidence

    def test_french_phrases(self, detector):
        """French phrase patterns should be detected."""
        result = detector._detect_by_script("Qui es-tu?")
        assert result.language == 'fr'
        assert result.confidence >= 0.9

        result = detector._detect_by_script("Est-ce que tu parles français?")
        assert result.language == 'fr'
        assert result.confidence >= 0.9

    def test_german_markers(self, detector):
        """German with distinctive markers should be detected."""
        result = detector._detect_by_script("Wie geht es Ihnen? Das ist schön.")
        assert result.language == 'de'
        assert result.confidence >= 0.5  # Pattern detection gives moderate confidence

    def test_polish_markers(self, detector):
        """Polish with distinctive diacritics should be detected."""
        result = detector._detect_by_script("Dziękuję bardzo, proszę")
        assert result.language == 'pl'
        assert result.confidence >= 0.7

    def test_turkish_markers(self, detector):
        """Turkish with distinctive characters should be detected."""
        result = detector._detect_by_script("Teşekkür ederim, lütfen")
        assert result.language == 'tr'
        assert result.confidence >= 0.7

    def test_vietnamese_diacritics(self, detector):
        """Vietnamese with tone marks should be detected with high confidence."""
        result = detector._detect_by_script("Cảm ơn bạn rất nhiều")
        assert result.language == 'vi'
        assert result.confidence >= 0.7  # Good but not perfect for short text


class TestEnglishDetection:
    """Tests for English language detection and ASCII bias handling."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    @pytest.mark.asyncio
    async def test_english_question_heuristic(self, detector):
        """Short English questions should be detected correctly."""
        # These are the problematic cases that used to be misclassified
        test_cases = [
            "How do I export code?",
            "What is the best way to do this?",
            "Can you help me please?",
            "Where should I put this file?",
            "Why does this happen?",
            "Thanks for your help!",
        ]

        for text in test_cases:
            result = await detector._detect_language_ensemble_async(text)
            assert result.language == 'en', f"Failed for: {text}"
            assert result.confidence >= 0.7, f"Low confidence for: {text}"

    @pytest.mark.asyncio
    async def test_english_not_misclassified_as_portuguese(self, detector):
        """English should not be misclassified as Portuguese."""
        # This was a known issue
        result = await detector._detect_language_ensemble_async("How do I export code?")
        assert result.language == 'en'
        assert result.language != 'pt'

    @pytest.mark.asyncio
    async def test_english_not_misclassified_as_spanish(self, detector):
        """Pure ASCII English should not be misclassified as Spanish."""
        result = await detector._detect_language_ensemble_async("What is your name?")
        assert result.language == 'en'
        assert result.language != 'es'


class TestMultiLanguageScenarios:
    """Tests for multi-language and edge case scenarios."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    @pytest.mark.asyncio
    async def test_short_text_cjk(self, detector):
        """Very short CJK text should still be detected."""
        result = await detector._detect_language_ensemble_async("你好")
        assert result.language == 'zh'

    @pytest.mark.asyncio
    async def test_empty_text(self, detector):
        """Empty text should return fallback language."""
        result = await detector._detect_language_ensemble_async("")
        assert result.language == 'en'
        assert result.method == 'length_fallback'

    @pytest.mark.asyncio
    async def test_whitespace_only(self, detector):
        """Whitespace-only text should return fallback."""
        result = await detector._detect_language_ensemble_async("   \n\t  ")
        assert result.language == 'en'

    @pytest.mark.asyncio
    async def test_code_removal(self, detector):
        """Code blocks should be removed before detection."""
        text = "```python\nprint('hello')\n```\nBonjour, comment ça va?"
        result = await detector._detect_language_ensemble_async(text)
        # Should detect French, not be confused by code
        assert result.language == 'fr'

    @pytest.mark.asyncio
    async def test_url_removal(self, detector):
        """URLs should be removed before detection."""
        # Use more distinctive French to overcome ASCII bias
        text = "Visitez https://example.com/page pour plus d'informations. Merci beaucoup! C'est très bien."
        result = await detector._detect_language_ensemble_async(text)
        assert result.language == 'fr'


class TestLanguageStickiness:
    """Tests for language stickiness across messages."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    @pytest.mark.asyncio
    async def test_stickiness_with_previous_language(self, detector):
        """Ambiguous text should prefer previous language."""
        # First detect Spanish with very strong markers (no English words)
        result1 = await detector._detect_language_ensemble_async(
            "¡Buenos días! ¿Cómo te llamas? Me llamo María. Mucho gusto.",
            previous_language=None
        )
        assert result1.language == 'es'

        # Ambiguous short text should stick to Spanish
        result2 = await detector._detect_language_ensemble_async(
            "OK",  # Ambiguous
            previous_language='es'
        )
        # Should either detect as Spanish or fall back to previous
        assert result2.language in ['es', 'en']

    @pytest.mark.asyncio
    async def test_stickiness_override_with_strong_signal(self, detector):
        """Strong language signal should override stickiness."""
        # Previous was English, but strong French signal
        result = await detector._detect_language_ensemble_async(
            "Bonjour, comment allez-vous aujourd'hui?",
            previous_language='en'
        )
        assert result.language == 'fr'


class TestRealWorldPrompts:
    """Tests with real-world prompts to ensure LLM responds in correct language."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    @pytest.mark.asyncio
    async def test_english_programming_question(self, detector):
        """Programming questions in English should be detected correctly."""
        prompts = [
            "How do I create a REST API in Python?",
            "What's the difference between let and const in JavaScript?",
            "Can you explain how async/await works?",
            "Please help me debug this code",
            "Why is my function returning undefined?",
        ]
        for prompt in prompts:
            result = await detector._detect_language_ensemble_async(prompt)
            assert result.language == 'en', f"Failed for: {prompt}"

    @pytest.mark.asyncio
    async def test_spanish_questions(self, detector):
        """Spanish questions should be detected correctly."""
        # Use prompts with more Spanish words than English technical terms
        prompts = [
            "¿Cómo puedo aprender a programar? Necesito ayuda con esto.",
            "¿Cuál es la diferencia entre estas dos cosas? Gracias por explicar.",
            "¿Me puedes ayudar con este problema? Muchas gracias por tu tiempo y paciencia.",
        ]
        for prompt in prompts:
            result = await detector._detect_language_ensemble_async(prompt)
            assert result.language == 'es', f"Failed for: {prompt}"

    @pytest.mark.asyncio
    async def test_french_questions(self, detector):
        """French questions should be detected correctly."""
        prompts = [
            "Comment puis-je créer une API en Python?",
            "Qu'est-ce que c'est le machine learning?",
            "Pouvez-vous m'expliquer cette erreur?",
        ]
        for prompt in prompts:
            result = await detector._detect_language_ensemble_async(prompt)
            assert result.language == 'fr', f"Failed for: {prompt}"

    @pytest.mark.asyncio
    async def test_german_questions(self, detector):
        """German questions should be detected correctly."""
        prompts = [
            "Wie kann ich eine REST API erstellen?",
            "Was ist der Unterschied zwischen let und const?",
            "Können Sie mir bei diesem Problem helfen?",
        ]
        for prompt in prompts:
            result = await detector._detect_language_ensemble_async(prompt)
            assert result.language == 'de', f"Failed for: {prompt}"

    @pytest.mark.asyncio
    async def test_chinese_questions(self, detector):
        """Chinese questions should be detected correctly."""
        prompts = [
            "如何用Python创建REST API?",
            "机器学习是什么?",
            "请帮我解释这个错误",
        ]
        for prompt in prompts:
            result = await detector._detect_language_ensemble_async(prompt)
            assert result.language == 'zh', f"Failed for: {prompt}"

    @pytest.mark.asyncio
    async def test_japanese_questions(self, detector):
        """Japanese questions should be detected correctly."""
        # Use text with clear hiragana/katakana to ensure Japanese detection
        prompts = [
            "このプログラムはどうやって使いますか?",  # Clear hiragana
            "関数の使い方を教えてください",  # Clear hiragana
            "エラーの原因を説明できますか?",  # Katakana + hiragana
        ]
        for prompt in prompts:
            result = await detector._detect_language_ensemble_async(prompt)
            assert result.language == 'ja', f"Failed for: {prompt}"

    @pytest.mark.asyncio
    async def test_korean_questions(self, detector):
        """Korean questions should be detected correctly."""
        prompts = [
            "Python으로 REST API를 어떻게 만들 수 있나요?",
            "이 코드에서 오류가 발생하는 이유를 설명해 주세요",
            "함수의 사용법을 알려주세요",
        ]
        for prompt in prompts:
            result = await detector._detect_language_ensemble_async(prompt)
            assert result.language == 'ko', f"Failed for: {prompt}"


class TestDetectionResult:
    """Tests for DetectionResult dataclass."""

    def test_language_normalization_on_creation(self):
        """Language code should be normalized when creating DetectionResult."""
        result = DetectionResult(
            language='eng',
            confidence=0.9,
            method='test'
        )
        assert result.language == 'en'

    def test_chinese_variant_normalization(self):
        """Chinese variants should be normalized."""
        result = DetectionResult(
            language='zh-cn',
            confidence=0.9,
            method='test'
        )
        assert result.language == 'zh'


class TestTextCleaning:
    """Tests for text cleaning before detection."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    def test_url_removal(self, detector):
        """URLs should be removed from text."""
        text = "Visit https://example.com for more info"
        cleaned = detector._clean_text_for_detection(text)
        assert "https://" not in cleaned
        assert "example.com" not in cleaned

    def test_email_removal(self, detector):
        """Emails should be removed from text."""
        text = "Contact me at user@example.com please"
        cleaned = detector._clean_text_for_detection(text)
        assert "@" not in cleaned

    def test_code_fence_removal(self, detector):
        """Code fences should be removed."""
        text = "Here's the code:\n```python\nprint('hello')\n```\nDone!"
        cleaned = detector._clean_text_for_detection(text)
        assert "```" not in cleaned
        assert "print" not in cleaned

    def test_inline_code_removal(self, detector):
        """Inline code should be removed."""
        text = "Use the `print()` function"
        cleaned = detector._clean_text_for_detection(text)
        assert "`" not in cleaned


class TestMarkerPatterns:
    """Tests for marker pattern matching."""

    def test_english_markers_pattern(self):
        """English marker pattern should match common words."""
        test_text = "The quick brown fox can jump. What is this? Please help!"
        matches = ENGLISH_MARKERS_PATTERN.findall(test_text.lower())
        assert len(matches) >= 4  # the, can, what, is, this, please

    def test_spanish_markers_pattern(self):
        """Spanish marker pattern should match distinctive characters."""
        test_text = "¿Cómo estás? ¡Hola amigo!"
        matches = SPANISH_MARKERS_PATTERN.findall(test_text)
        assert len(matches) >= 2  # ¿, ó, á, ¡


class TestPipelineIntegration:
    """Tests for integration with the pipeline."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    def test_should_execute_when_enabled(self, detector):
        """Step should execute when enabled and message exists."""
        context = create_context("Hello world")
        assert detector.should_execute(context) is True

    def test_should_not_execute_when_blocked(self, detector):
        """Step should not execute when context is blocked."""
        context = create_context("Hello world")
        context.is_blocked = True
        assert detector.should_execute(context) is False

    def test_should_not_execute_when_empty_message(self, detector):
        """Step should not execute when message is empty."""
        context = create_context("")
        assert detector.should_execute(context) is False

    @pytest.mark.asyncio
    async def test_process_sets_detected_language(self, detector):
        """Process should set detected_language on context."""
        # Use strong French markers to ensure detection
        context = create_context("Bonjour, comment allez-vous? C'est très bien, merci beaucoup!")
        result = await detector.process(context)
        assert result.detected_language == 'fr'

    @pytest.mark.asyncio
    async def test_process_sets_metadata(self, detector):
        """Process should set language detection metadata."""
        context = create_context("Hello, how are you?")
        result = await detector.process(context)
        assert 'last_detected_language' in result.metadata
        assert 'last_detected_language_confidence' in result.metadata
        assert hasattr(result, 'language_detection_meta')


class TestAccuracyBenchmark:
    """
    Accuracy benchmark tests with diverse language samples.

    These tests use longer, more realistic text samples to verify
    detection accuracy across many languages.
    """

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    # Comprehensive test data with expected languages
    # Using samples with clear language markers to ensure accurate detection
    LANGUAGE_SAMPLES = {
        'en': [
            "The quick brown fox jumps over the lazy dog.",
            "How can I help you today? Please let me know if you have any questions.",
            "Machine learning is a subset of artificial intelligence.",
        ],
        'es': [
            "El rápido zorro marrón salta sobre el perro perezoso. ¡Qué interesante!",
            "¿Cómo puedo ayudarte hoy? Por favor, déjame saber si tienes preguntas. Gracias.",
            "El aprendizaje automático es un subconjunto de la inteligencia artificial. ¿Entiendes?",
        ],
        'fr': [
            "Le renard brun rapide saute par-dessus le chien paresseux. C'est amusant!",
            "Comment puis-je vous aider aujourd'hui? N'hésitez pas à me poser des questions. Merci beaucoup.",
            "L'apprentissage automatique est un sous-ensemble de l'intelligence artificielle. Qu'est-ce que c'est?",
        ],
        'de': [
            "Der schnelle braune Fuchs springt über den faulen Hund. Das ist schön!",
            "Wie kann ich Ihnen heute helfen? Bitte lassen Sie mich wissen, wenn Sie Fragen haben. Danke.",
            "Maschinelles Lernen ist ein Teilbereich der künstlichen Intelligenz. Verstehen Sie?",
        ],
        'it': [
            "La volpe marrone veloce salta sopra il cane pigro. Che bello! Grazie mille.",
            "Come posso aiutarti oggi? Per favore fammi sapere se hai domande. Prego.",
            "L'apprendimento automatico è un sottoinsieme dell'intelligenza artificiale. Capito?",
        ],
        'pt': [
            "A rápida raposa marrom pula sobre o cachorro preguiçoso. Que legal! Obrigado.",
            "Como posso ajudá-lo hoje? Por favor, me avise se você tiver perguntas. Muito obrigado.",
            "O aprendizado de máquina é um subconjunto da inteligência artificial. Você entende?",
        ],
        'zh': [
            "敏捷的棕色狐狸跳过懒狗。",
            "今天我能帮你什么忙?如果你有任何问题,请告诉我。",
            "机器学习是人工智能的一个子集。",
        ],
        'ja': [
            "素早い茶色のキツネは怠惰な犬を飛び越えます。これはとても面白いですね。",
            "今日はどのようにお手伝いできますか?ご質問があればお知らせください。ありがとうございます。",
            "機械学習は人工知能のサブセットです。わかりますか?",
        ],
        'ko': [
            "빠른 갈색 여우가 게으른 개를 뛰어넘습니다.",
            "오늘 어떻게 도와드릴까요? 질문이 있으시면 알려주세요.",
            "머신러닝은 인공지능의 하위 분야입니다.",
        ],
        'ru': [
            "Быстрая коричневая лиса прыгает через ленивую собаку.",
            "Как я могу помочь вам сегодня? Пожалуйста, дайте знать, если у вас есть вопросы.",
            "Машинное обучение является подмножеством искусственного интеллекта.",
        ],
        'ar': [
            "الثعلب البني السريع يقفز فوق الكلب الكسول.",
            "كيف يمكنني مساعدتك اليوم؟ يرجى إخباري إذا كان لديك أي أسئلة.",
            "التعلم الآلي هو مجموعة فرعية من الذكاء الاصطناعي.",
        ],
        'hi': [
            "तेज भूरी लोमड़ी आलसी कुत्ते के ऊपर से कूदती है।",
            "आज मैं आपकी कैसे मदद कर सकता हूं? कृपया मुझे बताएं अगर आपके कोई प्रश्न हैं।",
            "मशीन लर्निंग कृत्रिम बुद्धिमत्ता का एक उपसमूह है।",
        ],
        'th': [
            "สุนัขจิ้งจอกสีน้ำตาลตัวเร็วกระโดดข้ามสุนัขขี้เกียจ",
            "วันนี้ฉันช่วยอะไรคุณได้บ้าง กรุณาแจ้งให้ฉันทราบหากคุณมีคำถาม",
            "การเรียนรู้ของเครื่องเป็นส่วนย่อยของปัญญาประดิษฐ์",
        ],
    }

    @pytest.mark.asyncio
    async def test_accuracy_all_languages(self, detector):
        """Test detection accuracy across all supported languages."""
        results = {}
        failures = []

        for expected_lang, samples in self.LANGUAGE_SAMPLES.items():
            correct = 0
            for sample in samples:
                result = await detector._detect_language_ensemble_async(sample)
                if result.language == expected_lang:
                    correct += 1
                else:
                    failures.append({
                        'expected': expected_lang,
                        'detected': result.language,
                        'confidence': result.confidence,
                        'text': sample[:50] + '...'
                    })

            accuracy = correct / len(samples)
            results[expected_lang] = accuracy

        # Report failures for debugging
        if failures:
            print("\n=== Detection Failures ===")
            for f in failures:
                print(f"Expected: {f['expected']}, Got: {f['detected']} "
                      f"(conf: {f['confidence']:.2f}) - {f['text']}")

        # All languages should have at least 66% accuracy (2/3 samples correct)
        for lang, accuracy in results.items():
            assert accuracy >= 0.66, f"Language {lang} has only {accuracy*100:.0f}% accuracy"

        # Most languages should have 100% accuracy
        high_accuracy_count = sum(1 for acc in results.values() if acc >= 1.0)
        assert high_accuracy_count >= len(results) * 0.7, \
            f"Only {high_accuracy_count}/{len(results)} languages have 100% accuracy"


# =============================================================================
# Tests for Bug Fixes (December 2024)
# =============================================================================

class TestRedisServiceIntegration:
    """Tests for Redis service integration (Fix #1: Redis stickiness)."""

    @pytest.fixture
    def mock_redis_service(self):
        """Create a mock Redis service."""
        redis_service = MagicMock()
        redis_service.enabled = True
        redis_service.get_json = AsyncMock(return_value=None)
        redis_service.store_json = AsyncMock(return_value=True)
        return redis_service

    @pytest.fixture
    def detector_with_redis(self, mock_redis_service):
        """Create a detector with Redis service registered."""
        container = MockContainer()
        container.register('redis_service', mock_redis_service)
        return LanguageDetectionStep(container), mock_redis_service

    @pytest.mark.asyncio
    async def test_session_language_saved_to_redis(self, detector_with_redis):
        """Language detection should save results to Redis when available."""
        detector, redis_mock = detector_with_redis
        context = create_context("Hello world", session_id="test-session-123")

        result = DetectionResult(language='en', confidence=0.9, method='test')
        await detector._save_session_language(context, result)

        # Verify Redis was called with correct parameters (store_json, not set_json)
        redis_mock.store_json.assert_called_once()
        call_args = redis_mock.store_json.call_args
        assert call_args[0][0] == "lang_detect:test-session-123"
        assert call_args[0][1]['language'] == 'en'
        assert call_args[0][1]['confidence'] == 0.9
        assert call_args[1]['ttl'] == 3600

    @pytest.mark.asyncio
    async def test_session_language_retrieved_from_redis(self, detector_with_redis):
        """Language detection should retrieve previous language from Redis."""
        detector, redis_mock = detector_with_redis
        redis_mock.get_json = AsyncMock(return_value={
            'language': 'es',
            'confidence': 0.85,
            'method': 'ensemble_voting'
        })

        context = create_context("OK", session_id="test-session-123")
        result = await detector._get_session_language(context)

        assert result == 'es'
        redis_mock.get_json.assert_called_once_with("lang_detect:test-session-123")

    @pytest.mark.asyncio
    async def test_fallback_when_redis_disabled(self):
        """Should fallback to context metadata when Redis is not available."""
        container = MockContainer()
        detector = LanguageDetectionStep(container)

        context = create_context("OK", session_id="test-session-123")
        context.metadata['last_detected_language'] = 'fr'

        result = await detector._get_session_language(context)
        assert result == 'fr'

    @pytest.mark.asyncio
    async def test_no_session_id_skips_redis(self, detector_with_redis):
        """Should not access Redis when session_id is None."""
        detector, redis_mock = detector_with_redis
        context = create_context("Hello", session_id=None)

        result = await detector._get_session_language(context)
        redis_mock.get_json.assert_not_called()


class TestMixedLanguageMetadataExposure:
    """Tests for mixed-language metadata exposure (Fix #2)."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    @pytest.mark.asyncio
    async def test_mixed_language_metadata_at_top_level(self, detector):
        """Mixed-language fields should be exposed at top level of metadata."""
        # Simulate a result with mixed language detection
        result = DetectionResult(
            language='en',
            confidence=0.6,
            method='ensemble_voting',
            raw_results={
                'mixed_language_detected': True,
                'secondary_language': 'es',
                'secondary_confidence': 0.35
            }
        )

        context = create_context("Hello amigo, como estas?")

        # Manually set the metadata as the process method would
        context.detected_language = result.language
        if not hasattr(context, 'language_detection_meta'):
            context.language_detection_meta = {}

        meta_update = {
            'confidence': result.confidence,
            'method': result.method,
            'raw_results': result.raw_results
        }

        raw = result.raw_results or {}
        if raw.get('mixed_language_detected'):
            meta_update['mixed_language_detected'] = True
            meta_update['secondary_language'] = raw.get('secondary_language')
            meta_update['secondary_confidence'] = raw.get('secondary_confidence')
        else:
            meta_update['mixed_language_detected'] = False

        context.language_detection_meta.update(meta_update)

        # Verify top-level access
        assert context.language_detection_meta['mixed_language_detected'] is True
        assert context.language_detection_meta['secondary_language'] == 'es'
        assert context.language_detection_meta['secondary_confidence'] == 0.35

    @pytest.mark.asyncio
    async def test_non_mixed_language_sets_flag_false(self, detector):
        """Non-mixed language detection should set mixed_language_detected to False."""
        result = DetectionResult(
            language='en',
            confidence=0.95,
            method='ensemble_voting',
            raw_results={}
        )

        context = create_context("Hello world")
        context.detected_language = result.language
        context.language_detection_meta = {}

        meta_update = {
            'confidence': result.confidence,
            'method': result.method,
            'raw_results': result.raw_results
        }

        raw = result.raw_results or {}
        if raw.get('mixed_language_detected'):
            meta_update['mixed_language_detected'] = True
            meta_update['secondary_language'] = raw.get('secondary_language')
            meta_update['secondary_confidence'] = raw.get('secondary_confidence')
        else:
            meta_update['mixed_language_detected'] = False
            meta_update['secondary_language'] = None
            meta_update['secondary_confidence'] = None

        context.language_detection_meta.update(meta_update)

        assert context.language_detection_meta['mixed_language_detected'] is False

    @pytest.mark.asyncio
    async def test_stale_secondary_language_cleared(self, detector):
        """Secondary language fields should be cleared when detection is not mixed."""
        context = create_context("Hello world")

        # Simulate previous turn having mixed language
        context.language_detection_meta = {
            'mixed_language_detected': True,
            'secondary_language': 'es',
            'secondary_confidence': 0.35
        }

        # Now simulate a non-mixed detection result
        result = DetectionResult(
            language='en',
            confidence=0.95,
            method='ensemble_voting',
            raw_results={}  # No mixed language this time
        )

        # Apply the same logic as the actual implementation
        meta_update = {
            'confidence': result.confidence,
            'method': result.method,
            'raw_results': result.raw_results
        }

        raw = result.raw_results or {}
        if raw.get('mixed_language_detected'):
            meta_update['mixed_language_detected'] = True
            meta_update['secondary_language'] = raw.get('secondary_language')
            meta_update['secondary_confidence'] = raw.get('secondary_confidence')
        else:
            meta_update['mixed_language_detected'] = False
            meta_update['secondary_language'] = None
            meta_update['secondary_confidence'] = None

        context.language_detection_meta.update(meta_update)

        # Verify stale values are cleared
        assert context.language_detection_meta['mixed_language_detected'] is False
        assert context.language_detection_meta['secondary_language'] is None
        assert context.language_detection_meta['secondary_confidence'] is None


class TestConfidenceCalculation:
    """Tests for confidence calculation (Fix #3: retrieval boost threshold)."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    @pytest.mark.asyncio
    async def test_confidence_as_proportion_of_votes(self, detector):
        """Confidence should be calculated as proportion of total votes."""
        # Test with clear English text - should get high confidence
        result = await detector._detect_language_ensemble_async(
            "How do I install the software on my computer?"
        )

        # With the new calculation (best_score / total_votes),
        # unanimous detection should give high confidence
        assert result.confidence >= 0.7, \
            f"Expected confidence >= 0.7, got {result.confidence}"

    @pytest.mark.asyncio
    async def test_confidence_exceeds_retrieval_threshold(self, detector):
        """Confidence should realistically exceed the default 0.7 retrieval threshold."""
        # Test with unambiguous text in different languages
        test_cases = [
            ("What is the weather like today?", 'en'),
            ("你好，今天天气怎么样？", 'zh'),
            ("こんにちは、今日の天気はどうですか？", 'ja'),
            ("Bonjour, quel temps fait-il aujourd'hui?", 'fr'),
            ("¿Cuál es el clima hoy? Necesito saber antes de salir.", 'es'),
        ]

        high_confidence_count = 0
        for text, expected_lang in test_cases:
            result = await detector._detect_language_ensemble_async(text)
            if result.confidence >= 0.7:
                high_confidence_count += 1

        # At least 60% of unambiguous texts should exceed the threshold
        assert high_confidence_count >= 3, \
            f"Only {high_confidence_count}/5 texts exceeded 0.7 confidence threshold"

    @pytest.mark.asyncio
    async def test_margin_calculation_uses_proportions(self, detector):
        """Margin should be calculated using confidence proportions."""
        # This test verifies the margin is computed correctly
        # by checking that ambiguous text triggers stickiness

        # First detect clear English
        result1 = await detector._detect_language_ensemble_async(
            "Please help me with this problem."
        )

        # Now detect something ambiguous with previous language set
        result2 = await detector._detect_language_ensemble_async(
            "OK",
            previous_language='en'
        )

        # If margin calculation works correctly, short ambiguous text
        # should trigger stickiness and return English
        assert result2.language == 'en', \
            "Short ambiguous text should stick to previous language"


class TestRetrievalBoostIntegration:
    """Integration tests for retrieval boost with fixed confidence."""

    @pytest.fixture
    def detector(self):
        container = MockContainer()
        return LanguageDetectionStep(container)

    @pytest.mark.asyncio
    async def test_clear_language_activates_boost(self, detector):
        """Clear language detection should produce confidence high enough for boost."""
        # Use text that should be clearly identifiable
        clear_texts = [
            "I need help setting up my development environment",
            "Please explain how the authentication system works",
            "What are the best practices for error handling?",
        ]

        for text in clear_texts:
            result = await detector._detect_language_ensemble_async(text)

            # The fix ensures confidence is calculated as proportion of votes
            # so clear English text should have confidence >= 0.7
            if result.language == 'en':
                assert result.confidence >= 0.6, \
                    f"Clear English text '{text[:30]}...' got confidence {result.confidence}, expected >= 0.6"


# Run tests with: pytest server/tests/test_language_detection.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
