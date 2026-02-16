"""
Language Detection Step

This step detects the language of the user's message for better language matching.
Enhanced with:
- Per-backend confidence normalization
- Expanded script coverage (20+ scripts)
- Expanded Latin language patterns
- Pre-compiled regex patterns
- Async parallel backend execution
- Mixed-language detection
- Configurable heuristic nudges
- Session persistence for stickiness
- Chat history language prior
"""

import asyncio
import logging
import re
import math
from typing import Dict, Any, Optional, List, Tuple, Pattern
from dataclasses import dataclass, field

from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)

# Import detection libraries with availability flags
try:
    from langdetect import detect_langs, LangDetectException, DetectorFactory
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    detect_langs = None
    class LangDetectException(Exception):
        pass
    class DetectorFactory:
        seed = 0

# Seed the language detector for deterministic results when available
try:
    DetectorFactory.seed = 0
except Exception:
    pass

try:
    import langid
    LANGID_AVAILABLE = True
except ImportError:
    LANGID_AVAILABLE = False

try:
    import pycld2 as cld2
    PYCLD2_AVAILABLE = True
except ImportError:
    PYCLD2_AVAILABLE = False

# Optional pycountry for language code normalization
try:
    import pycountry  # noqa: F401 - used for availability check
    PYCOUNTRY_AVAILABLE = True
except ImportError:
    PYCOUNTRY_AVAILABLE = False


# ============================================================================
# Pre-compiled Regex Patterns (Module-level for performance)
# ============================================================================

# Script detection patterns - covers 20+ scripts
# NOTE: Order matters for overlapping scripts - check Japanese before Chinese
SCRIPT_PATTERNS: List[Tuple[str, Pattern, float]] = [
    # East Asian - Japanese MUST come before Chinese (Kanji overlaps with CJK)
    ('ja', re.compile(r'[\u3040-\u309f\u30a0-\u30ff]'), 0.95),       # Japanese (Hiragana + Katakana)
    ('zh', re.compile(r'[\u4e00-\u9fff]'), 0.95),                    # Chinese (CJK Unified)
    ('ko', re.compile(r'[\uac00-\ud7af]'), 0.95),                    # Korean (Hangul)

    # Middle Eastern
    ('ar', re.compile(r'[\u0600-\u06ff]'), 0.95),                    # Arabic
    ('he', re.compile(r'[\u0590-\u05ff]'), 0.95),                    # Hebrew
    ('fa', re.compile(r'[\u0600-\u06ff][\u067e\u0686\u0698\u06af]'), 0.90),  # Persian (Arabic + specific chars)

    # South Asian
    ('hi', re.compile(r'[\u0900-\u097f]'), 0.95),                    # Devanagari (Hindi, Marathi, Sanskrit)
    ('bn', re.compile(r'[\u0980-\u09ff]'), 0.95),                    # Bengali
    ('ta', re.compile(r'[\u0b80-\u0bff]'), 0.95),                    # Tamil
    ('te', re.compile(r'[\u0c00-\u0c7f]'), 0.95),                    # Telugu
    ('kn', re.compile(r'[\u0c80-\u0cff]'), 0.95),                    # Kannada
    ('ml', re.compile(r'[\u0d00-\u0d7f]'), 0.95),                    # Malayalam
    ('gu', re.compile(r'[\u0a80-\u0aff]'), 0.95),                    # Gujarati
    ('pa', re.compile(r'[\u0a00-\u0a7f]'), 0.95),                    # Punjabi (Gurmukhi)
    ('or', re.compile(r'[\u0b00-\u0b7f]'), 0.95),                    # Odia
    ('si', re.compile(r'[\u0d80-\u0dff]'), 0.95),                    # Sinhala

    # Southeast Asian
    ('th', re.compile(r'[\u0e00-\u0e7f]'), 0.95),                    # Thai
    ('lo', re.compile(r'[\u0e80-\u0eff]'), 0.95),                    # Lao
    ('my', re.compile(r'[\u1000-\u109f]'), 0.95),                    # Myanmar (Burmese)
    ('km', re.compile(r'[\u1780-\u17ff]'), 0.95),                    # Khmer

    # Other
    ('ka', re.compile(r'[\u10a0-\u10ff]'), 0.95),                    # Georgian
    ('hy', re.compile(r'[\u0530-\u058f]'), 0.95),                    # Armenian
    ('am', re.compile(r'[\u1200-\u137f]'), 0.95),                    # Amharic (Ethiopic)
    ('el', re.compile(r'[\u0370-\u03ff]'), 0.95),                    # Greek
    ('ru', re.compile(r'[\u0400-\u04ff]'), 0.80),                    # Cyrillic (lower confidence - multi-language)
]

# French phrase patterns for disambiguation
FRENCH_PHRASE_PATTERNS: List[Pattern] = [
    re.compile(r"\bqui\s+es[- ]?tu\b", re.IGNORECASE),
    re.compile(r"\bqui\s+[êe]tes[- ]?vous\b", re.IGNORECASE),
    re.compile(r"\best[- ]?ce\s+que\b", re.IGNORECASE),
    re.compile(r"\bje\s+suis\b", re.IGNORECASE),
    re.compile(r"\bqu['']est[- ]?ce\b", re.IGNORECASE),
]

# Word patterns for Latin script languages (lang_code, patterns, base_confidence)
LATIN_WORD_PATTERNS: List[Tuple[str, List[Pattern], float]] = [
    # Spanish
    ('es', [
        re.compile(r'¿'),
        re.compile(r'¡'),
        re.compile(r'\baño\b', re.IGNORECASE),
        re.compile(r'\bestá\b', re.IGNORECASE),
        re.compile(r'\bqué\b', re.IGNORECASE),
        re.compile(r'\bgracias\b', re.IGNORECASE),
        re.compile(r'\bmucho\b', re.IGNORECASE),
    ], 0.9),

    # Portuguese
    ('pt', [
        re.compile(r'\bção\b', re.IGNORECASE),
        re.compile(r'\bvocê\b', re.IGNORECASE),
        re.compile(r'\bporque\b', re.IGNORECASE),
        re.compile(r'\bestão\b', re.IGNORECASE),
        re.compile(r'\bobrigad[oa]\b', re.IGNORECASE),
        re.compile(r'[ãõ]'),
    ], 0.9),

    # French
    ('fr', [
        re.compile(r"\bc['']?est\b", re.IGNORECASE),
        re.compile(r"\bqu['']est[- ]?ce\b", re.IGNORECASE),
        re.compile(r'\bvoil[àa]\b', re.IGNORECASE),
        re.compile(r'\bparce\b', re.IGNORECASE),
        re.compile(r'\best[- ]?ce\b', re.IGNORECASE),
        re.compile(r'\bje\s+suis\b', re.IGNORECASE),
        re.compile(r'\bmerci\b', re.IGNORECASE),
        re.compile(r'[œæ]'),
    ], 0.9),

    # German
    ('de', [
        re.compile(r'[äöüß]'),
        re.compile(r'\bund\b', re.IGNORECASE),
        re.compile(r'\bdas\b', re.IGNORECASE),
        re.compile(r'\bist\b', re.IGNORECASE),
        re.compile(r'\bich\b', re.IGNORECASE),
        re.compile(r'\bdanke\b', re.IGNORECASE),
        re.compile(r'\bbitte\b', re.IGNORECASE),
    ], 0.85),

    # Italian
    ('it', [
        re.compile(r'\bperché\b', re.IGNORECASE),
        re.compile(r'\banche\b', re.IGNORECASE),
        re.compile(r'\bquesto\b', re.IGNORECASE),
        re.compile(r'\bdopo\b', re.IGNORECASE),
        re.compile(r'\bgrazie\b', re.IGNORECASE),
        re.compile(r'\bprego\b', re.IGNORECASE),
    ], 0.85),

    # Dutch
    ('nl', [
        re.compile(r'\bhij\b', re.IGNORECASE),
        re.compile(r'\bzij\b', re.IGNORECASE),
        re.compile(r'\bdank\s*je\b', re.IGNORECASE),
        re.compile(r'\balstublieft\b', re.IGNORECASE),
        re.compile(r'\bwaarom\b', re.IGNORECASE),
        re.compile(r'ij'),
    ], 0.85),

    # Swedish
    ('sv', [
        re.compile(r'[åäö]'),
        re.compile(r'\boch\b', re.IGNORECASE),
        re.compile(r'\bär\b', re.IGNORECASE),
        re.compile(r'\bjag\b', re.IGNORECASE),
        re.compile(r'\btack\b', re.IGNORECASE),
    ], 0.85),

    # Norwegian
    ('no', [
        re.compile(r'[æøå]'),
        re.compile(r'\bog\b', re.IGNORECASE),
        re.compile(r'\bhar\b', re.IGNORECASE),
        re.compile(r'\bhva\b', re.IGNORECASE),
        re.compile(r'\btakk\b', re.IGNORECASE),
    ], 0.85),

    # Danish
    ('da', [
        re.compile(r'[æøå]'),
        re.compile(r'\bog\b', re.IGNORECASE),
        re.compile(r'\bhar\b', re.IGNORECASE),
        re.compile(r'\bhvad\b', re.IGNORECASE),
        re.compile(r'\btak\b', re.IGNORECASE),
    ], 0.85),

    # Polish
    ('pl', [
        re.compile(r'[ąćęłńóśźż]'),
        re.compile(r'\bjest\b', re.IGNORECASE),
        re.compile(r'\bdziękuję\b', re.IGNORECASE),
        re.compile(r'\bproszę\b', re.IGNORECASE),
    ], 0.90),

    # Czech
    ('cs', [
        re.compile(r'[ěščřžýáíéúůťďň]'),
        re.compile(r'\bje\b', re.IGNORECASE),
        re.compile(r'\bděkuji\b', re.IGNORECASE),
        re.compile(r'\bprosím\b', re.IGNORECASE),
    ], 0.90),

    # Turkish
    ('tr', [
        re.compile(r'[şğıüçö]'),
        re.compile(r'\bve\b', re.IGNORECASE),
        re.compile(r'\bbir\b', re.IGNORECASE),
        re.compile(r'\bteşekkür\b', re.IGNORECASE),
        re.compile(r'\blütfen\b', re.IGNORECASE),
    ], 0.90),

    # Indonesian/Malay
    ('id', [
        re.compile(r'\bdan\b', re.IGNORECASE),
        re.compile(r'\byang\b', re.IGNORECASE),
        re.compile(r'\bini\b', re.IGNORECASE),
        re.compile(r'\bitu\b', re.IGNORECASE),
        re.compile(r'\bterima\s*kasih\b', re.IGNORECASE),
    ], 0.85),

    # Finnish
    ('fi', [
        re.compile(r'[äö]'),
        re.compile(r'\bja\b', re.IGNORECASE),
        re.compile(r'\bon\b', re.IGNORECASE),
        re.compile(r'\bkiitos\b', re.IGNORECASE),
        re.compile(r'kk|tt|pp|ss'),  # Double consonants common in Finnish
    ], 0.85),

    # Vietnamese (Latin script with diacritics)
    ('vi', [
        re.compile(r'[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]'),
        re.compile(r'\bvà\b', re.IGNORECASE),
        re.compile(r'\blà\b', re.IGNORECASE),
        re.compile(r'\bcảm\s*ơn\b', re.IGNORECASE),
    ], 0.95),

    # Romanian
    ('ro', [
        re.compile(r'[ăâîșț]'),
        re.compile(r'\bși\b', re.IGNORECASE),
        re.compile(r'\beste\b', re.IGNORECASE),
        re.compile(r'\bmulțumesc\b', re.IGNORECASE),
    ], 0.90),

    # Hungarian
    ('hu', [
        re.compile(r'[őű]'),
        re.compile(r'\bés\b', re.IGNORECASE),
        re.compile(r'\bvan\b', re.IGNORECASE),
        re.compile(r'\bköszönöm\b', re.IGNORECASE),
    ], 0.90),
]

# Combined English markers pattern (single regex for efficiency)
ENGLISH_MARKERS_PATTERN = re.compile(
    r'\b(the|and|this|that|is|are|what|how|why|where|when|who|can|could|should|would|please|thanks?|hello|hi)\b',
    re.IGNORECASE
)

# Combined Spanish markers pattern
SPANISH_MARKERS_PATTERN = re.compile(
    r'(¿|¡|[áéíóúñ]|\bqué\b|\bcomo\b|\bcómo\b|\bestás?\b|\bgracias\b)',
    re.IGNORECASE
)

# English question starters
ENGLISH_QUESTION_START_PATTERN = re.compile(
    r'^(how|what|why|where|when|who|can|could|should|would|is|are|does|do)\b',
    re.IGNORECASE
)

# Non-English diacritics for ASCII bias detection
NON_ENGLISH_DIACRITICS_PATTERN = re.compile(r'[áéíóúñçãõàâêô]')

# Text cleaning patterns
URL_PATTERN = re.compile(r'https?://\S{1,200}|www\.\S{1,200}')
EMAIL_PATTERN = re.compile(r'\b\S{1,100}@\S{1,100}\.[A-Za-z]{2,10}\b')
CODE_FENCE_PATTERN = re.compile(r'```[\s\S]*?```')
INLINE_CODE_PATTERN = re.compile(r'`[^`]{0,500}`')
EXCESSIVE_PUNCT_PATTERN = re.compile(r'[0-9_\-]{3,}')
WHITESPACE_PATTERN = re.compile(r'\s+')


# ============================================================================
# Language Code Normalization
# ============================================================================

# Common language code mappings (for backends that return non-standard codes)
LANGUAGE_CODE_MAP = {
    # ISO 639-1 to ISO 639-1 (normalize variants)
    'zh-cn': 'zh', 'zh-tw': 'zh', 'zh-hant': 'zh', 'zh-hans': 'zh',
    'zho': 'zh', 'chi': 'zh',
    'jpn': 'ja', 'kor': 'ko',
    'ara': 'ar', 'heb': 'he',
    'hin': 'hi', 'tha': 'th',
    'rus': 'ru', 'ukr': 'uk',
    'por': 'pt', 'spa': 'es', 'fra': 'fr', 'deu': 'de', 'ita': 'it',
    'nld': 'nl', 'swe': 'sv', 'nor': 'no', 'dan': 'da',
    'pol': 'pl', 'ces': 'cs', 'tur': 'tr',
    'ind': 'id', 'msa': 'ms', 'fin': 'fi', 'vie': 'vi',
    'ron': 'ro', 'hun': 'hu',
    'eng': 'en', 'english': 'en',
    # CLD2 specific
    'un': 'unknown', 'xxx': 'unknown',
}


def normalize_language_code(code: str) -> str:
    """Normalize language code to ISO 639-1 format."""
    if not code:
        return 'unknown'
    code_lower = code.lower().strip()
    return LANGUAGE_CODE_MAP.get(code_lower, code_lower[:2] if len(code_lower) > 2 else code_lower)


# ============================================================================
# Detection Result Data Classes
# ============================================================================

@dataclass
class DetectionResult:
    """Result of language detection with confidence and metadata."""
    language: str
    confidence: float
    method: str
    raw_results: Dict[str, Any] = None

    def __post_init__(self):
        # Normalize language code on creation
        self.language = normalize_language_code(self.language)


@dataclass
class MixedLanguageResult:
    """Result for mixed-language detection."""
    primary_language: str
    primary_confidence: float
    secondary_languages: List[Tuple[str, float]] = field(default_factory=list)
    is_mixed: bool = False
    method: str = "ensemble"
    raw_results: Dict[str, Any] = None


# ============================================================================
# Main Language Detection Step
# ============================================================================

class LanguageDetectionStep(PipelineStep):
    """
    Detect the language of the user's message using multiple backends.

    This step uses an ensemble of detection libraries with weighted voting
    for improved accuracy and robustness.

    Enhancements:
    - Pre-compiled regex patterns for performance
    - Async parallel backend execution
    - Per-backend confidence normalization
    - Expanded script and language coverage
    - Mixed-language detection
    - Configurable heuristic nudges
    - Session persistence for language stickiness
    - Chat history language prior
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config = self.container.get_or_none('config') or {}
        lang_config = config.get('language_detection', {})

        if lang_config.get('enabled', False):
            self._setup_backends()
        else:
            self.backends = []
            self.min_confidence = 0.7
            self.min_margin = 0.2
            self.fallback_language = 'en'
            self.prefer_english_for_ascii = True
            self.enable_stickiness = True
            self.heuristic_nudges = {}
            self.backend_timeout = 2.0

    def _setup_backends(self):
        """Initialize available backends with their weights."""
        config = self.container.get_or_none('config') or {}
        lang_config = config.get('language_detection', {})

        enabled_backends = lang_config.get('backends', ['langdetect', 'langid', 'pycld2'])

        self.backends = []
        backend_weights = lang_config.get('backend_weights', {
            'langdetect': 1.0,
            'langid': 1.2,
            'pycld2': 1.5
        })

        if 'langdetect' in enabled_backends and LANGDETECT_AVAILABLE:
            self.backends.append(('langdetect', backend_weights.get('langdetect', 1.0), self._detect_langdetect))

        if 'langid' in enabled_backends and LANGID_AVAILABLE:
            self.backends.append(('langid', backend_weights.get('langid', 1.2), self._detect_langid))

        if 'pycld2' in enabled_backends and PYCLD2_AVAILABLE:
            self.backends.append(('pycld2', backend_weights.get('pycld2', 1.5), self._detect_pycld2))

        # Store configuration
        self.min_confidence = lang_config.get('min_confidence', 0.7)
        self.min_margin = lang_config.get('min_margin', 0.2)
        self.prefer_english_for_ascii = lang_config.get('prefer_english_for_ascii', True)
        self.enable_stickiness = lang_config.get('enable_stickiness', True)
        self.fallback_language = lang_config.get('fallback_language', 'en')

        # Configurable heuristic nudges (new)
        self.heuristic_nudges = lang_config.get('heuristic_nudges', {
            'en_boost': 0.2,      # Boost for English in ASCII-heavy text
            'es_penalty': 0.1,    # Penalty for Spanish in pure ASCII
            'script_boost': 0.2,  # Boost when script matches ensemble winner
        })

        # Mixed language detection threshold
        self.mixed_language_threshold = lang_config.get('mixed_language_threshold', 0.3)

        # Chat history prior settings
        self.use_chat_history_prior = lang_config.get('use_chat_history_prior', True)
        self.chat_history_prior_weight = lang_config.get('chat_history_prior_weight', 0.3)
        self.chat_history_messages_count = lang_config.get('chat_history_messages_count', 5)

        # Backend timeout (default 2.0s to handle cold starts when models need to load)
        self.backend_timeout = lang_config.get('backend_timeout', 2.0)

        logger.info(f"Initialized {len(self.backends)} language detection backends: {[b[0] for b in self.backends]}")

    def should_execute(self, context: ProcessingContext) -> bool:
        """Determine if this step should execute."""
        config = self.container.get_or_none('config') or {}
        language_detection_config = config.get('language_detection', {})
        enabled = language_detection_config.get('enabled', False)
        return enabled and bool(context.message) and not context.is_blocked

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Process the context and detect the language."""
        if context.is_blocked:
            return context

        logger.debug("Detecting language of user message")

        try:
            # Get previous language from session storage if available
            previous_language = await self._get_session_language(context)

            # Get chat history language prior if enabled
            chat_history_prior = None
            if self.use_chat_history_prior:
                chat_history_prior = await self._get_chat_history_language_prior(context)

            # Detect language using ensemble method
            result = await self._detect_language_ensemble_async(
                context.message,
                previous_language=previous_language,
                chat_history_prior=chat_history_prior
            )

            context.detected_language = result.language

            # Store additional metadata for debugging
            if not hasattr(context, 'language_detection_meta'):
                context.language_detection_meta = {}

            # Build metadata with mixed-language fields exposed at top level
            meta_update = {
                'confidence': result.confidence,
                'method': result.method,
                'raw_results': result.raw_results
            }

            # Expose mixed-language detection at top level (not buried in raw_results)
            # Always set all three fields to avoid stale data from previous turns
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

            # Persist to session storage for stickiness across API calls
            await self._save_session_language(context, result)

            # Also store in context metadata for backward compatibility
            context.metadata['last_detected_language'] = result.language
            context.metadata['last_detected_language_confidence'] = result.confidence

            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                logger.info(
                    f"DEBUG: Detected language: {result.language} "
                    f"(confidence: {result.confidence:.2f}, method: {result.method}) "
                    f"for message: {context.message[:50]}..."
                )

        except Exception as e:
            logger.error(f"Error during language detection: {str(e)}")
            context.detected_language = self.fallback_language
            if not hasattr(context, 'language_detection_meta'):
                context.language_detection_meta = {}
            context.language_detection_meta.update({
                'confidence': 0.0,
                'method': 'fallback',
                'error': str(e)
            })

        return context

    async def _get_session_language(self, context: ProcessingContext) -> Optional[str]:
        """Get previously detected language from session storage."""
        # Skip Redis lookup if stickiness is disabled
        if not self.enable_stickiness:
            return None

        if not context.session_id:
            return getattr(context, 'detected_language', None) or None

        try:
            # Try to get from Redis service if available
            if self.container.has('redis_service'):
                redis_service = self.container.get('redis_service')
                if redis_service and redis_service.enabled:
                    key = f"lang_detect:{context.session_id}"
                    data = await redis_service.get_json(key)
                    if data and data.get('language'):
                        return data.get('language')
        except Exception as e:
            logger.debug(f"Could not retrieve session language from Redis: {e}")

        # Fallback to context metadata
        return context.metadata.get('last_detected_language') or getattr(context, 'detected_language', None) or None

    async def _save_session_language(self, context: ProcessingContext, result: DetectionResult) -> None:
        """Save detected language to session storage for persistence."""
        # Skip Redis storage if stickiness is disabled
        if not self.enable_stickiness:
            return

        if not context.session_id:
            return

        try:
            if self.container.has('redis_service'):
                redis_service = self.container.get('redis_service')
                if redis_service and redis_service.enabled:
                    key = f"lang_detect:{context.session_id}"
                    data = {
                        'language': result.language,
                        'confidence': result.confidence,
                        'method': result.method
                    }
                    # Set with TTL of 1 hour to match session duration
                    await redis_service.store_json(key, data, ttl=3600)
        except Exception as e:
            logger.debug(f"Could not save session language to Redis: {e}")

    async def _get_chat_history_language_prior(self, context: ProcessingContext) -> Optional[Dict[str, float]]:
        """
        Get language distribution from recent chat history.

        Returns a dictionary mapping language codes to their frequency weights.
        """
        if not context.session_id:
            return None

        try:
            # Try to get chat history service
            if not self.container.has('chat_history_service'):
                return None

            chat_service = self.container.get('chat_history_service')
            if not chat_service:
                return None

            # Get recent messages using the correct method name
            messages = await chat_service.get_conversation_history(
                session_id=context.session_id,
                limit=self.chat_history_messages_count,
                include_metadata=True
            )

            if not messages:
                return None

            # Count language occurrences
            lang_counts: Dict[str, int] = {}
            for msg in messages:
                lang = msg.get('detected_language') or msg.get('metadata', {}).get('detected_language')
                if lang:
                    lang = normalize_language_code(lang)
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1

            if not lang_counts:
                return None

            # Convert to weights (normalize by total)
            total = sum(lang_counts.values())
            return {lang: count / total for lang, count in lang_counts.items()}

        except Exception as e:
            logger.debug(f"Could not get chat history language prior: {e}")
            return None

    async def _detect_language_ensemble_async(
        self,
        text: str,
        previous_language: Optional[str] = None,
        chat_history_prior: Optional[Dict[str, float]] = None
    ) -> DetectionResult:
        """
        Detect language using ensemble of multiple backends with async execution.
        """
        # Handle very short text - but try script detection first for CJK
        text_stripped = text.strip()
        if not text_stripped:
            return DetectionResult(
                language=self.fallback_language,
                confidence=0.1,
                method='length_fallback',
                raw_results={'reason': 'empty_text'}
            )

        # For very short text (1-2 chars), try script detection for CJK
        if len(text_stripped) < 3:
            script_result = self._detect_by_script(text_stripped)
            if script_result.confidence > 0.9:
                return script_result
            return DetectionResult(
                language=self.fallback_language,
                confidence=0.1,
                method='length_fallback',
                raw_results={'reason': 'text_too_short'}
            )

        # Pre-clean text to avoid URL/code bias
        clean_text = self._clean_text_for_detection(text)

        # First try high-confidence script-based detection
        script_result = self._detect_by_script(clean_text)
        if script_result.confidence > 0.9:
            return script_result

        # Run all available backends in parallel
        backend_results = []
        raw_results = {}

        if self.backends:
            # Create tasks for parallel execution
            tasks = []
            backend_info = []

            for backend_name, weight, detector_func in self.backends:
                tasks.append(self._run_backend_with_timeout(backend_name, detector_func, clean_text, self.backend_timeout))
                backend_info.append((backend_name, weight))

            # Execute all backends concurrently with timeout
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                backend_name, weight = backend_info[i]
                if isinstance(result, Exception):
                    logger.warning(f"Backend {backend_name} failed: {str(result)}")
                    raw_results[backend_name] = {'error': str(result)}
                elif result:
                    backend_results.append((result, weight, backend_name))
                    raw_results[backend_name] = {
                        'language': result.language,
                        'confidence': result.confidence
                    }

        if not backend_results:
            return DetectionResult(
                language=self.fallback_language,
                confidence=0.0,
                method='all_backends_failed',
                raw_results=raw_results
            )

        # Compute heuristic signals
        ascii_ratio = self._ascii_ratio(clean_text)
        english_marker_count = len(ENGLISH_MARKERS_PATTERN.findall(clean_text))
        spanish_marker_count = len(SPANISH_MARKERS_PATTERN.findall(clean_text))

        # Strong ASCII English heuristic
        if self.prefer_english_for_ascii:
            lower = clean_text.lower()
            if ascii_ratio > 0.98 and len(clean_text) <= 120:
                if ENGLISH_QUESTION_START_PATTERN.search(lower) or re.search(r'\b(please|thanks)\b', lower, re.IGNORECASE):
                    if spanish_marker_count == 0 and not NON_ENGLISH_DIACRITICS_PATTERN.search(lower):
                        return DetectionResult(
                            language='en',
                            confidence=0.9,
                            method='heuristic_ascii_bias',
                            raw_results={'reason': 'english_question_heuristic'}
                        )

        # Weighted voting with per-backend normalization
        language_votes: Dict[str, float] = {}

        for result, weight, backend_name in backend_results:
            lang = normalize_language_code(result.language)
            conf = result.confidence

            # Confidence is already normalized by per-backend methods
            conf = max(0.0, min(1.0, conf))

            weighted_score = conf * weight
            language_votes[lang] = language_votes.get(lang, 0) + weighted_score

        # Apply chat history prior if available
        if chat_history_prior and self.chat_history_prior_weight > 0:
            prior_boost = self.chat_history_prior_weight
            for lang, freq in chat_history_prior.items():
                if lang in language_votes:
                    language_votes[lang] += prior_boost * freq
                else:
                    language_votes[lang] = prior_boost * freq * 0.5  # Lower boost for new languages

        # Apply configurable heuristic nudges
        en_boost = self.heuristic_nudges.get('en_boost', 0.2)
        es_penalty = self.heuristic_nudges.get('es_penalty', 0.1)

        if self.prefer_english_for_ascii and ascii_ratio > 0.95 and english_marker_count > 0 and spanish_marker_count == 0:
            language_votes['en'] = language_votes.get('en', 0) + en_boost
            if 'es' in language_votes:
                language_votes['es'] = max(0, language_votes['es'] - es_penalty)

        # Sort to get top candidates
        sorted_votes = sorted(language_votes.items(), key=lambda kv: kv[1], reverse=True)
        best_language, best_score = sorted_votes[0]
        second_score = sorted_votes[1][1] if len(sorted_votes) > 1 else 0.0

        # Compute confidence as proportion of total votes (true posterior probability)
        # This gives realistic confidence values that can exceed the retrieval threshold
        total_votes = sum(language_votes.values())
        if total_votes > 0:
            best_confidence = best_score / total_votes
        else:
            best_confidence = 0.0
        best_confidence = max(0.0, min(1.0, best_confidence))

        # Script detection confidence boost
        script_boost = self.heuristic_nudges.get('script_boost', 0.2)
        if script_result.confidence > 0.5 and script_result.language == best_language:
            # Scale boost by script coverage
            script_coverage = self._compute_script_coverage(clean_text, script_result.language)
            actual_boost = script_boost * script_coverage
            best_confidence = min(0.95, best_confidence + actual_boost)

        # Check for mixed language
        if len(sorted_votes) > 1:
            second_language, second_vote_score = sorted_votes[1]
            # Use same normalization (proportion of total votes) for consistency
            second_confidence = (second_vote_score / total_votes) if total_votes > 0 else 0.0
            if second_confidence >= self.mixed_language_threshold and best_confidence < 0.8:
                # This is potentially mixed-language text
                raw_results['mixed_language_detected'] = True
                raw_results['secondary_language'] = second_language
                raw_results['secondary_confidence'] = second_confidence

        # Enforce minimum margin and confidence
        # Margin is now the difference in confidence (proportion), not raw scores
        margin = best_confidence - (second_score / total_votes if total_votes > 0 else 0.0)

        if best_confidence < self.min_confidence or margin < self.min_margin:
            # Prefer sticky previous language when enabled and plausible
            if self.enable_stickiness and previous_language and previous_language in language_votes:
                # Decay stickiness based on how different the current detection is
                sticky_confidence = min(0.9, max(best_confidence, 0.7))
                return DetectionResult(
                    language=previous_language,
                    confidence=sticky_confidence,
                    method='sticky_previous',
                    raw_results={'reason': 'below_threshold_or_margin', 'votes': language_votes, 'raw': raw_results}
                )

            # Prefer English for high ASCII ratio
            lower = clean_text.lower()
            if self.prefer_english_for_ascii and ascii_ratio > 0.95 and spanish_marker_count == 0:
                if english_marker_count > 0 or ENGLISH_QUESTION_START_PATTERN.search(lower):
                    return DetectionResult(
                        language='en',
                        confidence=0.75,
                        method='heuristic_ascii_bias',
                        raw_results={'reason': 'below_threshold_or_margin', 'votes': language_votes, 'raw': raw_results}
                    )

            # Fallback
            return DetectionResult(
                language=self.fallback_language,
                confidence=best_confidence,
                method='threshold_fallback',
                raw_results={'votes': language_votes, 'raw': raw_results}
            )

        return DetectionResult(
            language=best_language,
            confidence=best_confidence,
            method='ensemble_voting',
            raw_results=raw_results
        )

    async def _run_backend_with_timeout(
        self,
        backend_name: str,
        detector_func,
        text: str,
        timeout: float = 0.5
    ) -> Optional[DetectionResult]:
        """Run a backend detector with timeout."""
        try:
            # Run in executor since detection libraries are synchronous
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, detector_func, text),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Backend {backend_name} timed out after {timeout}s")
            return None
        except Exception as e:
            logger.warning(f"Backend {backend_name} failed: {e}")
            return None

    def _detect_by_script(self, text: str) -> DetectionResult:
        """High-confidence script-based detection with comprehensive patterns."""
        # Check script patterns
        for lang_code, pattern, confidence in SCRIPT_PATTERNS:
            if pattern.search(text):
                return DetectionResult(
                    language=lang_code,
                    confidence=confidence,
                    method='script_detection',
                    raw_results={'matched_script': lang_code}
                )

        # Check French phrase patterns
        text_lower = text.lower()
        for pattern in FRENCH_PHRASE_PATTERNS:
            if pattern.search(text_lower):
                return DetectionResult(
                    language='fr',
                    confidence=0.95,
                    method='phrase_pattern_detection',
                    raw_results={'pattern': 'french_phrase'}
                )

        # Check Latin word patterns - collect ALL matches first
        pattern_matches: List[Tuple[str, int, float]] = []

        for lang_code, patterns, base_confidence in LATIN_WORD_PATTERNS:
            matches = sum(1 for pattern in patterns if pattern.search(text_lower))
            if matches >= 1:
                # Calculate confidence based on match ratio
                match_ratio = matches / len(patterns)
                actual_confidence = min(base_confidence, base_confidence * match_ratio + 0.3)
                pattern_matches.append((lang_code, matches, actual_confidence))

        # Return the best match (most patterns matched, then highest confidence)
        if pattern_matches:
            pattern_matches.sort(key=lambda x: (x[1], x[2]), reverse=True)
            best_lang, best_matches, best_conf = pattern_matches[0]
            return DetectionResult(
                language=best_lang,
                confidence=best_conf,
                method='word_pattern_detection',
                raw_results={'patterns_matched': best_matches}
            )

        return DetectionResult(
            language='unknown',
            confidence=0.0,
            method='script_detection',
            raw_results={'reason': 'no_patterns_matched'}
        )

    def _compute_script_coverage(self, text: str, lang_code: str) -> float:
        """Compute what fraction of text matches the detected script."""
        # Find the pattern for this language
        for code, pattern, _ in SCRIPT_PATTERNS:
            if code == lang_code:
                matches = pattern.findall(text)
                if not matches:
                    return 0.0
                # Count characters matched
                matched_chars = sum(len(m) for m in matches)
                return min(1.0, matched_chars / max(1, len(text)))
        return 0.0

    def _clean_text_for_detection(self, text: str) -> str:
        """Lightweight cleaning to remove tokens that confuse detectors."""
        text = URL_PATTERN.sub(' ', text)
        text = EMAIL_PATTERN.sub(' ', text)
        text = CODE_FENCE_PATTERN.sub(' ', text)
        text = INLINE_CODE_PATTERN.sub(' ', text)
        text = EXCESSIVE_PUNCT_PATTERN.sub(' ', text)
        text = WHITESPACE_PATTERN.sub(' ', text).strip()
        return text

    def _ascii_ratio(self, text: str) -> float:
        """Compute ratio of ASCII characters to total characters."""
        if not text:
            return 1.0
        total = len(text)
        ascii_count = sum(1 for c in text if ord(c) < 128)
        return ascii_count / total if total else 1.0

    # ========================================================================
    # Backend Detection Methods with Per-Backend Normalization
    # ========================================================================

    def _detect_langdetect(self, text: str) -> Optional[DetectionResult]:
        """Detect language using langdetect library."""
        if not LANGDETECT_AVAILABLE:
            return None
        try:
            lang_probs = detect_langs(text)
            if lang_probs:
                best = lang_probs[0]
                # langdetect already returns 0-1 probabilities
                return DetectionResult(
                    language=best.lang,
                    confidence=best.prob,
                    method='langdetect'
                )
        except LangDetectException:
            pass
        return None

    def _detect_langid(self, text: str) -> Optional[DetectionResult]:
        """Detect language using langid library with proper normalization."""
        if not LANGID_AVAILABLE:
            return None
        try:
            # Use rank() to get comparable scores and apply softmax
            if hasattr(langid, 'rank'):
                ranked = langid.rank(text)
                if ranked:
                    # ranked is list of (lang, score), scores are log-probs
                    top_k = ranked[:5]
                    max_score = max(s for _, s in top_k)
                    # Apply softmax over top-K for proper probability
                    exps = [math.exp(s - max_score) for _, s in top_k]
                    total = sum(exps) or 1.0
                    probs = [e / total for e in exps]
                    lang = top_k[0][0]
                    confidence = probs[0]
                    return DetectionResult(
                        language=lang,
                        confidence=confidence,
                        method='langid'
                    )

            # Fallback to classify()
            lang, score = langid.classify(text)
            # Apply softmax to single score (compare against 0)
            try:
                confidence = 1.0 / (1.0 + math.exp(-float(score)))
            except Exception:
                confidence = 0.7
            confidence = max(0.0, min(1.0, confidence))
            return DetectionResult(
                language=lang,
                confidence=confidence,
                method='langid'
            )
        except Exception:
            pass
        return None

    def _detect_pycld2(self, text: str) -> Optional[DetectionResult]:
        """Detect language using pycld2 library with proper normalization."""
        if not PYCLD2_AVAILABLE:
            return None
        try:
            is_reliable, text_bytes_found, details = cld2.detect(text)
            if details:
                lang_code = details[0][1]
                # pycld2 returns percentage (0-100), normalize to 0-1
                raw_confidence = details[0][2]
                confidence = raw_confidence / 100.0

                # Apply reliability factor
                if not is_reliable:
                    confidence *= 0.7  # Reduce confidence for unreliable detections

                return DetectionResult(
                    language=lang_code,
                    confidence=confidence,
                    method='pycld2'
                )
        except Exception:
            pass
        return None

    # Backward compatibility: sync version for external callers
    def _detect_language_ensemble(self, text: str, previous_language: Optional[str] = None) -> DetectionResult:
        """Sync wrapper for backward compatibility."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, run directly
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._detect_language_ensemble_async(text, previous_language)
                    )
                    return future.result(timeout=2.0)
            else:
                return asyncio.run(self._detect_language_ensemble_async(text, previous_language))
        except Exception as e:
            logger.error(f"Error in sync ensemble detection: {e}")
            return DetectionResult(
                language=self.fallback_language,
                confidence=0.0,
                method='sync_fallback',
                raw_results={'error': str(e)}
            )
