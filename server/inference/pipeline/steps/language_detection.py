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
import unicodedata
import urllib.parse
from collections import Counter
from functools import lru_cache
from typing import Any, Optional
from re import Pattern
from dataclasses import dataclass, field

import regex

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
except AttributeError:
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

# Optional pycountry for validating ISO 639 codes during normalization
try:
    import pycountry
    PYCOUNTRY_AVAILABLE = True
except ImportError:
    pycountry = None
    PYCOUNTRY_AVAILABLE = False


# ============================================================================
# Pre-compiled Regex Patterns (Module-level for performance)
# ============================================================================

AMBIGUOUS_LATIN_LANGS = frozenset({'de', 'nl', 'no', 'da', 'fi', 'id'})

# Result language when detection abstains. Never a response-language default.
UNKNOWN_LANGUAGE = 'unknown'

# Methods whose language comes from conversation state, not the current message.
PRIOR_METHODS = frozenset({'sticky_previous', 'chat_history_prior'})

# Candidate languages per Unicode script. A script with one candidate may
# select that language (script fast path); a shared script only narrows the
# candidates the statistical backends may choose from. Latin, and scripts not
# listed here, impose no restriction.
SCRIPT_CANDIDATES: dict[str, tuple[str, ...]] = {
    'Hangul': ('ko',),
    'Japanese': ('ja',),        # Kana present; Han letters in the same text count as Japanese
    'Han': ('zh', 'ja'),        # Han without kana: Chinese, or kanji-only Japanese
    'Cyrillic': ('ru', 'uk', 'bg', 'sr', 'mk', 'be', 'kk', 'ky', 'mn', 'tg'),
    'Arabic': ('ar', 'fa', 'ur', 'ps', 'ku', 'sd', 'ug'),
    'Hebrew': ('he', 'yi'),
    'Devanagari': ('hi', 'mr', 'ne', 'sa'),
    'Bengali': ('bn', 'as'),
    'Ethiopic': ('am', 'ti'),
    'Greek': ('el',),
    'Armenian': ('hy',),
    'Georgian': ('ka',),
    'Gurmukhi': ('pa',),
    'Gujarati': ('gu',),
    'Oriya': ('or',),
    'Tamil': ('ta',),
    'Telugu': ('te',),
    'Kannada': ('kn',),
    'Malayalam': ('ml',),
    'Sinhala': ('si',),
    'Thai': ('th',),
    'Lao': ('lo',),
    'Myanmar': ('my',),
    'Khmer': ('km',),
}

# Script-letter evidence (letters and combining marks; Common/Inherited
# characters such as digits, punctuation, emoji and the kana prolonged-sound
# mark are not evidence). One pass; the matching group names the script.
_SCRIPT_NAMES = [s for s in SCRIPT_CANDIDATES if s != 'Japanese'] + ['Latin']
SCRIPT_LETTER_PATTERN = regex.compile(
    '(?V1)' + '|'.join(
        [f'(?P<{s}>[\\p{{Script={s}}}&&[\\p{{L}}\\p{{M}}]])' for s in _SCRIPT_NAMES if s != 'Han']
        + [r'(?P<Kana>[[\p{Script=Hiragana}\p{Script=Katakana}]&&[\p{L}\p{M}]])',
           r'(?P<Han>[\p{Script=Han}&&[\p{L}\p{M}]])',
           r'(?P<Other>[[\p{L}\p{M}]--[\p{Script=Common}\p{Script=Inherited}]])']
    )
)

# Letters that narrow Arabic-script candidates. The Persian letters are shared
# with Urdu and Pashto, so they rule out Arabic rather than select Persian.
ARABIC_SCRIPT_MARKERS: list[tuple[Pattern, frozenset[str]]] = [
    (re.compile(r'[\u067e\u0686\u0698\u06af]'),                        # \u067e \u0686 \u0698 \u06af
     frozenset(SCRIPT_CANDIDATES['Arabic']) - {'ar'}),
    (re.compile(r'[\u0679\u0688\u0691\u06ba\u06d2]'), frozenset({'ur'})),  # \u0679 \u0688 \u0691 \u06ba \u06d2
    (re.compile(r'[\u067c\u0689\u0693\u069a\u0696\u0681\u0685\u06bc\u06ab]'),
     frozenset({'ps'})),                                               # \u067c \u0689 \u0693 \u069a \u0696 \u0681 \u0685 \u06bc \u06ab
]

# French phrase patterns for disambiguation
FRENCH_PHRASE_PATTERNS: list[Pattern] = [
    re.compile(r"\bqui\s+es[- ]?tu\b", re.IGNORECASE),
    re.compile(r"\bqui\s+[êe]tes[- ]?vous\b", re.IGNORECASE),
    re.compile(r"\best[- ]?ce\s+que\b", re.IGNORECASE),
    re.compile(r"\bje\s+suis\b", re.IGNORECASE),
    re.compile(r"\bqu['']est[- ]?ce\b", re.IGNORECASE),
    re.compile(r"\bcomment\s+(?:puis|allez|fait)\b", re.IGNORECASE),
    re.compile(r"\bje\s+(?:veux|peux|voudrais)\b", re.IGNORECASE),
    re.compile(r"\bdonne[- ]?moi\b", re.IGNORECASE),
    re.compile(r"\bs['']il\s+vous\s+pla[iî]t\b", re.IGNORECASE),
    re.compile(r"\bquels?\b", re.IGNORECASE),
    re.compile(r"\bpourquoi\b", re.IGNORECASE),
    re.compile(r"\bpouvez[- ]?vous\b", re.IGNORECASE),
]

# Word patterns for Latin script languages (lang_code, patterns, base_confidence)
LATIN_WORD_PATTERNS: list[tuple[str, list[Pattern], float]] = [
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
        re.compile(r'\bpourquoi\b', re.IGNORECASE),
        re.compile(r'\bcomment\b', re.IGNORECASE),
        re.compile(r'\bbonjour\b', re.IGNORECASE),
        re.compile(r'\bvous\b', re.IGNORECASE),
        re.compile(r'[éèêë]'),
    ], 0.9),

    # German
    ('de', [
        re.compile(r'[äöüß]'),
        re.compile(r'\bund\b', re.IGNORECASE),
        re.compile(r'\bnicht\b', re.IGNORECASE),
        re.compile(r'\bauch\b', re.IGNORECASE),
        re.compile(r'\beine?\b', re.IGNORECASE),
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

# English search-query/content markers for short ASCII noun phrases
ENGLISH_QUERY_MARKERS_PATTERN = re.compile(
    r"\b("
    r"crime|statistics?|stats?|weather|forecast|population|salary|salaries|"
    r"tax|taxes|price|prices|cost|costs|rate|rates|report|reports|news|"
    r"map|maps|housing|rent|rents|income|jobs|traffic|data"
    r")\b",
    re.IGNORECASE
)

# Non-English diacritics for ASCII bias detection
NON_ENGLISH_DIACRITICS_PATTERN = re.compile(r'[áéíóúñçãõàâêôèëïüäößæøåšžčřůě]')

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
    # Legacy ISO 639-1 codes (CLD2 still emits 'iw')
    'iw': 'he', 'ji': 'yi', 'in': 'id', 'jw': 'jv', 'mo': 'ro',
    # Backends emit 'tl' for Filipino/Tagalog; keep one code for both
    'fil': 'tl',
    # Norwegian written standards share the macrolanguage code
    'nb': 'no', 'nn': 'no',
    # Undetermined / not linguistic content
    'un': UNKNOWN_LANGUAGE, 'und': UNKNOWN_LANGUAGE, 'xxx': UNKNOWN_LANGUAGE,
    'zxx': UNKNOWN_LANGUAGE, 'mul': UNKNOWN_LANGUAGE, UNKNOWN_LANGUAGE: UNKNOWN_LANGUAGE,
}

# Well-formed RFC 5646 langtag with a 2-3 letter primary language (lowercased).
_BCP47_TAG_PATTERN = re.compile(r"""
    (?P<primary>[a-z]{2,3})
    (?:-[a-z]{3}){0,3}                    # extlang
    (?:-[a-z]{4})?                        # script
    (?:-(?:[a-z]{2}|\d{3}))?              # region
    (?:-(?:[a-z\d]{5,8}|\d[a-z\d]{3}))*   # variants
    (?:-[a-wyz\d](?:-[a-z\d]{2,8})+)*     # extensions
    (?:-x(?:-[a-z\d]{1,8})+)?             # private use
""", re.VERBOSE)


def _validate_iso639(code: str) -> str:
    """Return the ISO 639-1 code (or 639-3 when none exists), or unknown."""
    if not PYCOUNTRY_AVAILABLE:
        return code
    try:
        if len(code) == 2:
            language = pycountry.languages.get(alpha_2=code)
        else:
            language = pycountry.languages.get(alpha_3=code) or pycountry.languages.get(bibliographic=code)
    except (KeyError, LookupError):  # older pycountry raises instead of returning None
        language = None
    if language is None:
        return UNKNOWN_LANGUAGE
    return getattr(language, 'alpha_2', None) or language.alpha_3


@lru_cache(maxsize=1024)
def normalize_language_code(code: Optional[str]) -> str:
    """Normalize a backend language code or BCP-47 tag to a base language code.

    Only the base language is kept (``zh-Hant`` -> ``zh``, ``pt-BR`` -> ``pt``):
    prompt building and retrieval both key on it. The whole tag must be
    well-formed before subtags are dropped, so ``en--US`` is not English.
    Unsupported or malformed codes return ``unknown`` rather than a guess.
    """
    if not code:
        return UNKNOWN_LANGUAGE
    tag = str(code).strip().lower().replace('_', '-')
    if tag in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[tag]
    match = _BCP47_TAG_PATTERN.fullmatch(tag)
    if not match:
        return UNKNOWN_LANGUAGE
    primary = match.group('primary')
    if primary in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[primary]
    return _validate_iso639(primary)


# ============================================================================
# Detection Result Data Classes
# ============================================================================

@dataclass
class DetectionResult:
    """Result of language detection with confidence and metadata."""
    language: str
    confidence: float
    method: str
    raw_results: Optional[dict[str, Any]] = None

    def __post_init__(self):
        # Normalize language code on creation
        self.language = normalize_language_code(self.language)

    @property
    def abstained(self) -> bool:
        return self.language == UNKNOWN_LANGUAGE


def abstain(reason: str, **raw: Any) -> DetectionResult:
    """An explicit "language unknown" outcome; never replaced by a default language."""
    return DetectionResult(
        language=UNKNOWN_LANGUAGE,
        confidence=0.0,
        method='abstained',
        raw_results={'reason': reason, **raw},
    )


@dataclass(frozen=True)
class ScriptEvidence:
    """Script-letter counts for a text, computed once before any decision."""
    letters: int
    counts: dict[str, int] = field(default_factory=dict)
    dominant: Optional[str] = None
    coverage: float = 0.0

    @property
    def candidates(self) -> tuple[str, ...]:
        """Languages the dominant script allows; empty means unrestricted."""
        return SCRIPT_CANDIDATES.get(self.dominant or '', ())


@dataclass(frozen=True)
class HeuristicSignals:
    """Precomputed lexical signals used by ensemble voting heuristics."""
    ascii_ratio: float
    english_marker_count: int
    spanish_marker_count: int
    lower_text: str
    non_en_latin_matched: bool
    english_query_like: bool


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
        self.backends = []
        self.min_confidence = 0.7
        self.min_margin = 0.2
        self.min_letters = 5
        self.script_fast_path_min_letters = 1
        self.script_fast_path_min_coverage = 0.8
        self.prefer_english_for_ascii = True
        self.enable_stickiness = False
        self.heuristic_nudges = {}
        self.backend_timeout = 10.0
        self.use_chat_history_prior = True
        self.chat_history_prior_weight = 0.3
        self.chat_history_messages_count = 5
        self.mixed_language_threshold = 0.3

        config = self.container.get_or_none('config') or {}
        lang_config = config.get('language_detection', {})

        if lang_config.get('enabled', False):
            self._setup_backends()

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
        self.enable_stickiness = lang_config.get('enable_stickiness', False)

        # Evidence thresholds: below min_letters the text is too short for the
        # statistical backends; the script fast path needs its own minimums.
        self.min_letters = lang_config.get('min_letters', 5)
        script_fast_path = lang_config.get('script_fast_path', {}) or {}
        self.script_fast_path_min_letters = script_fast_path.get('min_letters', 1)
        self.script_fast_path_min_coverage = script_fast_path.get('min_coverage', 0.8)

        # Configurable heuristic nudges (new)
        self.heuristic_nudges = lang_config.get('heuristic_nudges', {
            'en_boost': 0.2,      # Boost for English in ASCII-heavy text
            'es_penalty': 0.1,    # Penalty for Spanish in pure ASCII
        })

        # Mixed language detection threshold
        self.mixed_language_threshold = lang_config.get('mixed_language_threshold', 0.3)

        # Chat history prior settings
        self.use_chat_history_prior = lang_config.get('use_chat_history_prior', True)
        self.chat_history_prior_weight = lang_config.get('chat_history_prior_weight', 0.3)
        self.chat_history_messages_count = lang_config.get('chat_history_messages_count', 5)

        # Backend timeout (default 2.0s to handle cold starts when models need to load)
        self.backend_timeout = lang_config.get('backend_timeout', 10.0)

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
                'abstained': result.abstained,
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

            # Store in context metadata (used by context_retrieval for language boosting).
            # An abstention is not language evidence, so it clears rather than records.
            if result.abstained:
                context.metadata.pop('last_detected_language', None)
                context.metadata.pop('last_detected_language_confidence', None)
            else:
                context.metadata['last_detected_language'] = result.language
                context.metadata['last_detected_language_confidence'] = result.confidence

            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                logger.info(
                    f"DEBUG: Detected language: {result.language} "
                    f"(confidence: {result.confidence:.2f}, method: {result.method}) "
                    f"for message: {(context.message or '')[:50]}..."
                )

        except Exception as e:  # noqa: BLE001 - pipeline step must not crash the request; abstains instead
            logger.error(f"Error during language detection: {e!s}")
            context.detected_language = UNKNOWN_LANGUAGE
            if not hasattr(context, 'language_detection_meta'):
                context.language_detection_meta = {}
            context.language_detection_meta.update({
                'confidence': 0.0,
                'method': 'abstained',
                'abstained': True,
                'raw_results': {'reason': 'error'},
                'error': str(e)
            })

        return context

    async def _get_session_language(self, context: ProcessingContext) -> Optional[str]:
        """Get previously detected language from session storage."""
        # Skip cache lookup if stickiness is disabled
        if not self.enable_stickiness:
            return None

        if not context.session_id:
            return getattr(context, 'detected_language', None) or None

        try:
            # Try to get from the cache service if available
            if self.container.has('cache_service'):
                cache_service = self.container.get('cache_service')
                if cache_service and cache_service.enabled:
                    key = self._session_language_key(context.session_id)
                    data = await cache_service.get_json(key)
                    if data and data.get('language'):
                        return data.get('language')
        except Exception as e:  # noqa: BLE001 - best-effort cache read; falls through to context metadata
            logger.debug(f"Could not retrieve session language from cache: {e}")

        # Fallback to context metadata
        return context.metadata.get('last_detected_language') or getattr(context, 'detected_language', None) or None

    async def _save_session_language(self, context: ProcessingContext, result: DetectionResult) -> None:
        """Save detected language to session storage for persistence."""
        # Skip cache storage if stickiness is disabled
        if not self.enable_stickiness:
            return

        if not context.session_id:
            return

        # Only independently detected languages are evidence for later turns;
        # abstentions and prior-derived results would feed the prior back into itself.
        if result.abstained or result.method in PRIOR_METHODS:
            return

        try:
            if self.container.has('cache_service'):
                cache_service = self.container.get('cache_service')
                if cache_service and cache_service.enabled:
                    key = self._session_language_key(context.session_id)
                    data = {
                        'language': result.language,
                        'confidence': result.confidence,
                        'method': result.method
                    }
                    # Set with TTL of 1 hour to match session duration
                    await cache_service.store_json(key, data, ttl=3600)
        except Exception as e:  # noqa: BLE001 - best-effort cache write must not fail the detection step
            logger.debug(f"Could not save session language to cache: {e}")

    def _session_language_key(self, session_id: str) -> str:
        """Build a cache-safe key for persisted language detection state."""
        safe_id = urllib.parse.quote(str(session_id), safe='')
        return f"lang_detect:{safe_id}"

    async def _get_chat_history_language_prior(self, context: ProcessingContext) -> Optional[dict[str, float]]:
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
            lang_counts: dict[str, int] = {}
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

        except Exception as e:  # noqa: BLE001 - best-effort heuristic over arbitrary chat-history message shapes
            logger.debug(f"Could not get chat history language prior: {e}")
            return None

    async def _detect_language_ensemble_async(
        self,
        text: str,
        previous_language: Optional[str] = None,
        chat_history_prior: Optional[dict[str, float]] = None
    ) -> DetectionResult:
        """
        Detect language using ensemble of multiple backends with async execution.
        """
        # Pre-clean text to avoid URL/code bias
        clean_text = self._clean_text_for_detection(text or "")
        evidence = self._script_evidence(clean_text)
        if evidence.letters == 0:
            return abstain('no_letters')

        # Unique-script fast path, or high-confidence Latin phrase patterns
        script_result = self._detect_by_script(clean_text, evidence)
        if script_result.confidence > 0.9:
            return script_result

        # Too little text for the statistical backends: use a trustworthy
        # conversation prior if there is one, otherwise abstain.
        if evidence.letters < self.min_letters:
            return self._short_text_prior(previous_language, chat_history_prior) or abstain(
                'low_evidence', letters=evidence.letters
            )

        candidates = self._narrow_candidates(clean_text, evidence)

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
                    logger.warning(f"Backend {backend_name} failed: {result!s}")
                    raw_results[backend_name] = {'error': str(result)}
                elif result:
                    backend_results.append((result, weight, backend_name))
                    raw_results[backend_name] = {
                        'language': result.language,
                        'confidence': result.confidence
                    }

        # A backend answering "unknown" (e.g. CLD2 'un') has no vote to cast.
        backend_results = [entry for entry in backend_results if not entry[0].abstained]
        if not backend_results:
            return abstain('all_backends_failed', raw=raw_results)

        signals = self._compute_heuristic_signals(clean_text)

        # Strong ASCII English heuristic
        if self.prefer_english_for_ascii:
            if signals.ascii_ratio > 0.98 and len(clean_text) <= 120:
                if (
                    ENGLISH_QUESTION_START_PATTERN.search(signals.lower_text)
                    or signals.english_marker_count > 0
                    or signals.english_query_like
                ):
                    if (
                        signals.spanish_marker_count == 0
                        and not NON_ENGLISH_DIACRITICS_PATTERN.search(signals.lower_text)
                        and not signals.non_en_latin_matched
                    ):
                        return DetectionResult(
                            language='en',
                            confidence=0.9,
                            method='heuristic_ascii_bias',
                            raw_results={
                                'reason': 'english_query_heuristic' if signals.english_query_like else 'english_question_heuristic'
                            }
                        )

        language_votes = self._aggregate_backend_votes(backend_results, chat_history_prior)
        self._apply_nudges(language_votes, signals)

        # A shared script restricts which languages may win; votes outside the
        # candidates still count toward the total so dropping them cannot
        # inflate confidence.
        eligible_votes = language_votes
        if candidates:
            raw_results['script_candidates'] = sorted(candidates)
            eligible_votes = {lang: v for lang, v in language_votes.items() if lang in candidates and v > 0}
            if not eligible_votes:
                if len(candidates) == 1:
                    return DetectionResult(
                        language=next(iter(candidates)),
                        confidence=0.75,
                        method='script_letters',
                        raw_results={'reason': 'distinctive_letters', 'votes': language_votes, 'raw': raw_results},
                    )
                return abstain('no_candidate_votes', votes=language_votes, raw=raw_results)

        # Sort to get top candidates
        sorted_votes = sorted(eligible_votes.items(), key=lambda kv: kv[1], reverse=True)
        best_language, best_score = sorted_votes[0]
        second_score = sorted_votes[1][1] if len(sorted_votes) > 1 else 0.0

        # Confidence is the winner's share of all weighted top-1 votes. It is a
        # vote share, not a posterior probability (see roadmap Phase 3).
        total_votes = sum(language_votes.values())
        if total_votes > 0:
            raw_best_confidence = best_score / total_votes
        else:
            raw_best_confidence = 0.0
        raw_best_confidence = max(0.0, min(1.0, raw_best_confidence))
        second_confidence = (second_score / total_votes) if total_votes > 0 else 0.0
        margin = raw_best_confidence - second_confidence
        best_confidence = raw_best_confidence

        # Check for mixed language
        if len(sorted_votes) > 1:
            second_language = sorted_votes[1][0]
            if second_confidence >= self.mixed_language_threshold and best_confidence < 0.8:
                # This is potentially mixed-language text
                raw_results['mixed_language_detected'] = True
                raw_results['secondary_language'] = second_language
                raw_results['secondary_confidence'] = second_confidence

        # Enforce minimum margin and confidence
        # Margin is now the difference in confidence (proportion), not raw scores
        if raw_best_confidence < self.min_confidence or margin < self.min_margin:
            # Prefer sticky previous language when enabled and plausible
            if self.enable_stickiness and previous_language and previous_language in eligible_votes:
                # Decay stickiness based on how different the current detection is
                sticky_confidence = min(0.9, max(best_confidence, 0.7))
                return DetectionResult(
                    language=previous_language,
                    confidence=sticky_confidence,
                    method='sticky_previous',
                    raw_results={'reason': 'below_threshold_or_margin', 'votes': language_votes, 'raw': raw_results}
                )

            # Prefer English for high ASCII ratio, but not if non-English Latin patterns matched
            if (
                self.prefer_english_for_ascii
                and signals.ascii_ratio > 0.95
                and signals.spanish_marker_count == 0
                and not signals.non_en_latin_matched
            ):
                if (
                    signals.english_marker_count > 0
                    or ENGLISH_QUESTION_START_PATTERN.search(signals.lower_text)
                    or signals.english_query_like
                ):
                    return DetectionResult(
                        language='en',
                        confidence=0.75,
                        method='heuristic_ascii_bias',
                        raw_results={
                            'reason': 'below_threshold_or_margin',
                            'votes': language_votes,
                            'raw': raw_results,
                            'english_query_like': signals.english_query_like,
                        }
                    )

            # If non-English Latin patterns matched, trust the best voted language;
            # otherwise the evidence is insufficient and detection abstains.
            if not signals.non_en_latin_matched:
                return abstain('below_threshold', votes=language_votes, raw=raw_results)
            return DetectionResult(
                language=best_language,
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

    def _compute_heuristic_signals(self, clean_text: str) -> HeuristicSignals:
        """Compute reusable text signals for language heuristics."""
        ascii_ratio = self._ascii_ratio(clean_text)
        english_marker_count = len(ENGLISH_MARKERS_PATTERN.findall(clean_text))
        spanish_marker_count = len(SPANISH_MARKERS_PATTERN.findall(clean_text))
        ascii_word_tokens = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", clean_text)
        lower_text = clean_text.lower()

        non_en_latin_matched = False
        for lang_code, patterns, _base_confidence in LATIN_WORD_PATTERNS:
            min_matches = 2 if lang_code in AMBIGUOUS_LATIN_LANGS else 1
            matches = sum(1 for pattern in patterns if pattern.search(lower_text))
            if matches >= min_matches:
                non_en_latin_matched = True
                break

        english_query_like = (
            ascii_ratio > 0.98
            and len(clean_text) <= 120
            and len(ascii_word_tokens) >= 3
            and ENGLISH_QUERY_MARKERS_PATTERN.search(lower_text) is not None
            and spanish_marker_count == 0
            and not NON_ENGLISH_DIACRITICS_PATTERN.search(lower_text)
            and not non_en_latin_matched
        )

        return HeuristicSignals(
            ascii_ratio=ascii_ratio,
            english_marker_count=english_marker_count,
            spanish_marker_count=spanish_marker_count,
            lower_text=lower_text,
            non_en_latin_matched=non_en_latin_matched,
            english_query_like=english_query_like,
        )

    def _aggregate_backend_votes(
        self,
        backend_results: list[tuple[DetectionResult, float, str]],
        chat_history_prior: Optional[dict[str, float]],
    ) -> dict[str, float]:
        """Aggregate normalized backend scores and optional chat-history prior."""
        language_votes: dict[str, float] = {}

        for result, weight, _backend_name in backend_results:
            lang = normalize_language_code(result.language)
            conf = max(0.0, min(1.0, result.confidence))
            language_votes[lang] = language_votes.get(lang, 0) + conf * weight

        if chat_history_prior and self.chat_history_prior_weight > 0:
            prior_boost = self.chat_history_prior_weight
            for lang, freq in chat_history_prior.items():
                if lang in language_votes:
                    language_votes[lang] += prior_boost * freq
                else:
                    language_votes[lang] = prior_boost * freq * 0.5

        return language_votes

    def _apply_nudges(self, language_votes: dict[str, float], signals: HeuristicSignals) -> None:
        """Apply configured heuristic nudges to aggregated votes in place."""
        en_boost = self.heuristic_nudges.get('en_boost', 0.2)
        es_penalty = self.heuristic_nudges.get('es_penalty', 0.1)

        if (
            self.prefer_english_for_ascii
            and signals.ascii_ratio > 0.95
            and (signals.english_marker_count > 0 or signals.english_query_like)
            and signals.spanish_marker_count == 0
        ):
            language_votes['en'] = language_votes.get('en', 0) + en_boost
            if 'es' in language_votes:
                language_votes['es'] = max(0, language_votes['es'] - es_penalty)

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
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, detector_func, text),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Backend {backend_name} timed out after {timeout}s")
            return None
        except Exception as e:  # noqa: BLE001 - pluggable detection backend with no fixed exception surface
            logger.warning(f"Backend {backend_name} failed: {e}")
            return None

    def _script_evidence(self, text: str) -> ScriptEvidence:
        """Count script letters across the whole text before choosing anything."""
        counts = Counter(m.lastgroup for m in SCRIPT_LETTER_PATTERN.finditer(text))
        # Kana marks the text as Japanese; its kanji are Japanese evidence too.
        if counts.get('Kana'):
            counts['Japanese'] = counts.pop('Kana') + counts.pop('Han', 0)
        letters = sum(counts.values())
        if not letters:
            return ScriptEvidence(letters=0)
        dominant, dominant_count = counts.most_common(1)[0]
        return ScriptEvidence(
            letters=letters,
            counts=dict(counts),
            dominant=dominant,
            coverage=dominant_count / letters,
        )

    def _narrow_candidates(self, text: str, evidence: ScriptEvidence) -> frozenset[str]:
        """Candidate languages for the statistical stage; empty means unrestricted.

        Only a script covering enough of the text restricts candidates, so
        mixed-script input is not forced into its first script's languages.
        """
        if evidence.coverage < self.script_fast_path_min_coverage:
            return frozenset()
        candidates = frozenset(evidence.candidates)
        if evidence.dominant == 'Arabic':
            for pattern, languages in ARABIC_SCRIPT_MARKERS:
                if pattern.search(text) and candidates & languages:
                    candidates &= languages
        return candidates

    def _short_text_prior(
        self,
        previous_language: Optional[str],
        chat_history_prior: Optional[dict[str, float]],
    ) -> Optional[DetectionResult]:
        """Conversation-derived language for text too short to detect.

        Confidence stays below retrieval_min_confidence: a prior may pick the
        reply language but should not re-rank retrieved documents.
        """
        if self.enable_stickiness and previous_language and previous_language != UNKNOWN_LANGUAGE:
            return DetectionResult(
                language=previous_language,
                confidence=0.6,
                method='sticky_previous',
                raw_results={'reason': 'low_evidence'},
            )
        if chat_history_prior:
            language, share = max(chat_history_prior.items(), key=lambda kv: kv[1])
            if share >= 0.5 and language != UNKNOWN_LANGUAGE:
                return DetectionResult(
                    language=language,
                    confidence=round(0.6 * share, 4),
                    method='chat_history_prior',
                    raw_results={'reason': 'low_evidence', 'prior': chat_history_prior},
                )
        return None

    def _detect_by_script(self, text: str, evidence: Optional[ScriptEvidence] = None) -> DetectionResult:
        """Unique-script fast path, then Latin phrase/word patterns.

        A script selects a language only when it maps to a single candidate and
        has enough letters and coverage. Shared scripts return ``unknown`` with
        their candidates so the statistical stage can choose among them.
        """
        evidence = evidence or self._script_evidence(text)
        candidates = evidence.candidates
        if (
            len(candidates) == 1
            and evidence.counts.get(evidence.dominant, 0) >= self.script_fast_path_min_letters
            and evidence.coverage >= self.script_fast_path_min_coverage
        ):
            return DetectionResult(
                language=candidates[0],
                confidence=0.95,
                method='script_detection',
                raw_results={'script': evidence.dominant, 'coverage': round(evidence.coverage, 4)}
            )
        if evidence.dominant != 'Latin':
            return DetectionResult(
                language=UNKNOWN_LANGUAGE,
                confidence=0.0,
                method='script_detection',
                raw_results={'script': evidence.dominant, 'candidates': list(candidates)}
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
        pattern_matches: list[tuple[str, int, float]] = []

        # Languages with short common words that overlap English need min 2 matches
        for lang_code, patterns, base_confidence in LATIN_WORD_PATTERNS:
            matches = sum(1 for pattern in patterns if pattern.search(text_lower))
            min_matches = 2 if lang_code in AMBIGUOUS_LATIN_LANGS else 1
            if matches >= min_matches:
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

    def _clean_text_for_detection(self, text: str) -> str:
        """NFC-normalize, then remove tokens that confuse detectors.

        NFC (not NFKC) so composed and decomposed diacritics compare equal
        without folding compatibility characters such as full-width forms.
        """
        text = unicodedata.normalize('NFC', text)
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
                logger.debug("langid confidence normalization failed", exc_info=True)
                confidence = 0.7
            confidence = max(0.0, min(1.0, confidence))
            return DetectionResult(
                language=lang,
                confidence=confidence,
                method='langid'
            )
        except Exception:
            logger.debug("langid detection failed", exc_info=True)
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
            logger.debug("pycld2 detection failed", exc_info=True)
        return None
