"""
Language Detection Step

This step detects the language of the user's message for better language matching.
Enhanced with:
- Calibrated log-linear pooling of backend candidate distributions
- Expanded script coverage (20+ scripts)
- Expanded Latin language patterns
- Pre-compiled regex patterns
- Async parallel backend execution
- Mixed-language detection
- Session persistence for stickiness
- Chat history language prior
"""

import asyncio
import importlib.metadata
import json
import logging
import os
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

# Results that must not become evidence for later turns: a prior would feed
# back into itself, and a threshold fallback is below acceptance by definition.
UNTRUSTED_EVIDENCE_METHODS = PRIOR_METHODS | {'abstained', 'threshold_fallback'}

# Conversation prior policy: each older user turn counts half as much as the
# next newer one; the prior decides only when its top language holds at least
# half the weight, at a confidence below retrieval_min_confidence.
PRIOR_RECENCY_DECAY = 0.5
PRIOR_MIN_SHARE = 0.5
PRIOR_MAX_CONFIDENCE = 0.6

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
    """The pipeline-facing language decision.

    ``accepted`` means the current message decided the language (abstentions
    and conversation-prior results are not accepted). ``calibrated`` means
    ``confidence`` is a probability fitted on the benchmark tune split; rule
    paths (unique script, phrase patterns) and the prior report a fixed rule
    score instead. ``agreement`` is the share of answering backends whose
    top candidate is ``language``; ``margin`` is the gap to the next pooled
    candidate.
    """
    language: str
    confidence: float
    method: str
    raw_results: Optional[dict[str, Any]] = None
    accepted: bool = False
    calibrated: bool = False
    agreement: Optional[float] = None
    margin: Optional[float] = None

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


@lru_cache(maxsize=32)
def _package_version(package: str) -> Optional[str]:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def candidate_scores(pairs: Any) -> dict[str, float]:
    """Normalize backend codes and merge scores of codes that map to one language."""
    scores: dict[str, float] = {}
    for code, score in pairs:
        language = normalize_language_code(code)
        if language != UNKNOWN_LANGUAGE and score > 0:
            scores[language] = scores.get(language, 0.0) + float(score)
    return scores


@dataclass(frozen=True)
class BackendResult:
    """One backend's full candidate list, before any pooling.

    ``candidates`` maps normalized languages to scores on the backend's own
    ``scale``, which is not always a probability:

    - ``probability``: langdetect's sampled probabilities;
    - ``softmax_top_k``: langid log-probabilities softmaxed over its top k only;
    - ``text_percent``: the share of the text pycld2 assigns to each language.
    """
    backend: str
    candidates: dict[str, float]
    scale: str
    version: Optional[str] = None
    reliable: Optional[bool] = None
    raw: dict[str, Any] = field(default_factory=dict)
    spans: Optional[list[dict[str, Any]]] = None

    @property
    def language(self) -> str:
        if not self.candidates:
            return UNKNOWN_LANGUAGE
        return min(self.candidates.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    @property
    def score(self) -> float:
        return self.candidates.get(self.language, 0.0)

    @property
    def abstained(self) -> bool:
        return not self.candidates


CALIBRATION_PATH = os.path.join(os.path.dirname(__file__), 'language_detection_calibration.json')


@dataclass(frozen=True)
class PoolCalibration:
    """Pooling parameters fitted for one set of answering backends."""
    weights: dict[str, float]
    floor: float
    accept_confidence: float


@dataclass(frozen=True)
class Calibration:
    """Frozen pooling parameters, fitted on the benchmark tune split.

    There is one ``PoolCalibration`` per non-empty set of backends, because
    weights and the acceptance threshold fitted for all three backends do not
    transfer to a deployment (or a request) where only some of them answer.
    Regenerate with ``server/tests/language_eval/calibrate.py``; the file
    records the benchmark and backend versions that produced it.
    """
    version: str
    universe_size: int
    langid_top_k: int
    pools: dict[frozenset[str], PoolCalibration]

    @property
    def backends(self) -> frozenset[str]:
        return frozenset().union(*self.pools)

    def for_backends(self, backends: Any) -> Optional[PoolCalibration]:
        return self.pools.get(frozenset(backends))


@lru_cache(maxsize=4)
def load_calibration(path: str = CALIBRATION_PATH) -> Calibration:
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return Calibration(
        version=data['version'],
        universe_size=int(data['universe_size']),
        langid_top_k=int(data['langid_top_k']),
        pools={
            frozenset(pool['backends']): PoolCalibration(
                weights=dict(pool['weights']),
                floor=float(pool['floor']),
                accept_confidence=float(pool['accept_confidence']),
            )
            for pool in data['pools']
        },
    )


def pool_backend_distributions(
    results: list[BackendResult],
    pool: PoolCalibration,
    universe_size: int,
) -> tuple[dict[str, float], float]:
    """Weighted log-linear pool of backend candidate distributions.

    Each backend's scores are renormalized over its own candidates and mixed
    with a floor (``pool.floor`` spread over ``universe_size`` languages), so
    a language the backend did not list is unlikely rather than impossible.
    Then ``log P(l) = sum_b w_b log q_b(l)``, normalized over the whole
    universe. Languages no backend listed share the residual mass equally,
    so agreement on a weak answer cannot renormalize to 1.0.

    Returns the probabilities of the listed languages and the residual mass.
    """
    support = sorted({language for result in results for language in result.candidates})
    if not support:
        return {}, 1.0
    n, floor = universe_size, pool.floor
    log_scores = dict.fromkeys(support, 0.0)
    log_unlisted = 0.0
    for result in results:
        weight = pool.weights.get(result.backend, 0.0)
        total = sum(result.candidates.values())
        if weight <= 0 or total <= 0:
            continue
        for language in support:
            share = result.candidates.get(language, 0.0) / total
            log_scores[language] += weight * math.log((1 - floor) * share + floor / n)
        log_unlisted += weight * math.log(floor / n)

    peak = max(max(log_scores.values()), log_unlisted)
    scores = {language: math.exp(v - peak) for language, v in log_scores.items()}
    residual = max(n - len(support), 0) * math.exp(log_unlisted - peak)
    total = sum(scores.values()) + residual
    return {language: v / total for language, v in scores.items()}, residual / total


@dataclass(frozen=True)
class ConversationPrior:
    """Language distribution from earlier turns of the same conversation.

    ``source`` is ``chat_history`` (persisted user-message evidence) or
    ``session_cache`` (last trusted detection, when stickiness is enabled).
    """
    distribution: dict[str, float]
    source: str

    @property
    def method(self) -> str:
        return 'chat_history_prior' if self.source == 'chat_history' else 'sticky_previous'

    def top(self) -> tuple[str, float]:
        return max(self.distribution.items(), key=lambda kv: kv[1])


def language_evidence(context: Any) -> Optional[dict[str, Any]]:
    """This turn's detection, in the shape stored on the user message.

    Stored even when abstained, so the record is complete; the prior reader
    decides what is trustworthy.
    """
    language = getattr(context, 'detected_language', None)
    meta = getattr(context, 'language_detection_meta', None)
    if not language or not meta:
        return None
    return {
        'language': language,
        'confidence': meta.get('confidence'),
        'method': meta.get('method'),
        'abstained': bool(meta.get('abstained')),
    }


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


# ============================================================================
# Main Language Detection Step
# ============================================================================

class LanguageDetectionStep(PipelineStep):
    """
    Detect the language of the user's message using multiple backends.

    This step pools the full candidate distributions of several detection
    libraries with calibrated weights, and abstains when the pooled
    probability is too low.

    Enhancements:
    - Pre-compiled regex patterns for performance
    - Async parallel backend execution
    - Calibrated pooling of full backend candidate distributions
    - Expanded script and language coverage
    - Mixed-language detection
    - Session persistence for language stickiness
    - Chat history language prior
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backends = []
        self.calibration = load_calibration()
        self.min_letters = 5
        self.script_fast_path_min_letters = 1
        self.script_fast_path_min_coverage = 0.8
        self.enable_stickiness = False
        self.backend_timeout = 10.0
        self.use_chat_history_prior = True
        self.chat_history_messages_count = 5
        self.prior_min_confidence = 0.7
        self.stickiness_ttl_seconds = 3600
        self.mixed_language_threshold = 0.3

        config = self.container.get_or_none('config') or {}
        lang_config = config.get('language_detection', {})

        if lang_config.get('enabled', False):
            self._setup_backends()

    def _setup_backends(self):
        """Initialize the available backends; pooling weights come from the calibration file."""
        config = self.container.get_or_none('config') or {}
        lang_config = config.get('language_detection', {})

        enabled_backends = lang_config.get('backends', ['langdetect', 'langid', 'pycld2'])

        self.backends = []
        if 'langdetect' in enabled_backends and LANGDETECT_AVAILABLE:
            self.backends.append(('langdetect', self._detect_langdetect))

        if 'langid' in enabled_backends and LANGID_AVAILABLE:
            self.backends.append(('langid', self._detect_langid))

        if 'pycld2' in enabled_backends and PYCLD2_AVAILABLE:
            self.backends.append(('pycld2', self._detect_pycld2))

        self.enable_stickiness = lang_config.get('enable_stickiness', False)

        # Evidence thresholds: below min_letters the text is too short for the
        # statistical backends; the script fast path needs its own minimums.
        self.min_letters = lang_config.get('min_letters', 5)
        script_fast_path = lang_config.get('script_fast_path', {}) or {}
        self.script_fast_path_min_letters = script_fast_path.get('min_letters', 1)
        self.script_fast_path_min_coverage = script_fast_path.get('min_coverage', 0.8)

        # Mixed language detection threshold
        self.mixed_language_threshold = lang_config.get('mixed_language_threshold', 0.3)

        # Conversation prior settings
        self.use_chat_history_prior = lang_config.get('use_chat_history_prior', True)
        self.chat_history_messages_count = lang_config.get('chat_history_messages_count', 5)
        self.prior_min_confidence = lang_config.get('prior_min_confidence', 0.7)
        self.stickiness_ttl_seconds = lang_config.get('stickiness_ttl_seconds', 3600)

        # Backend timeout (default 2.0s to handle cold starts when models need to load)
        self.backend_timeout = lang_config.get('backend_timeout', 10.0)

        logger.info(
            f"Initialized {len(self.backends)} language detection backends: {[b[0] for b in self.backends]} "
            f"(calibration {self.calibration.version})"
        )

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
            prior = await self._get_conversation_prior(context)

            # Detect language using ensemble method
            result = await self._detect_language_ensemble_async(context.message, prior=prior)

            context.detected_language = result.language

            # Store additional metadata for debugging
            if not hasattr(context, 'language_detection_meta'):
                context.language_detection_meta = {}

            # Build metadata with mixed-language fields exposed at top level
            meta_update = {
                'confidence': result.confidence,
                'method': result.method,
                'abstained': result.abstained,
                'accepted': result.accepted,
                'calibrated': result.calibrated,
                'agreement': result.agreement,
                'margin': result.margin,
                'detector_version': self.calibration.version,
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
                'accepted': False,
                'calibrated': False,
                'raw_results': {'reason': 'error'},
                'error': str(e)
            })

        return context

    def _is_trusted_evidence(self, evidence: Optional[dict[str, Any]]) -> bool:
        """Whether a stored detection may inform later turns."""
        if not isinstance(evidence, dict) or evidence.get('abstained'):
            return False
        if evidence.get('method') in UNTRUSTED_EVIDENCE_METHODS:
            return False
        if normalize_language_code(evidence.get('language')) == UNKNOWN_LANGUAGE:
            return False
        confidence = evidence.get('confidence')
        return isinstance(confidence, (int, float)) and confidence >= self.prior_min_confidence

    async def _get_conversation_prior(self, context: ProcessingContext) -> Optional[ConversationPrior]:
        """One prior per request: persisted chat history first, else the session cache.

        The two sources describe the same earlier turns, so they are never
        combined. Either source failing or being unavailable yields no prior.
        """
        if not context.session_id:
            return None
        if self.use_chat_history_prior:
            prior = await self._get_chat_history_prior(context)
            if prior:
                return prior
        if self.enable_stickiness:
            return await self._get_session_cache_prior(context)
        return None

    async def _get_chat_history_prior(self, context: ProcessingContext) -> Optional[ConversationPrior]:
        """Confidence- and recency-weighted languages of recent user messages."""
        try:
            chat_service = self.container.get('chat_history_service') if self.container.has('chat_history_service') else None
            if not chat_service:
                return None

            messages = await chat_service.get_conversation_history(
                session_id=context.session_id,
                limit=self.chat_history_messages_count,
                include_metadata=True
            )
            # The user's detected language is stored on user messages only;
            # assistant and system messages are not evidence of it.
            user_messages = [m for m in messages or [] if m.get('role') == 'user']

            weights: dict[str, float] = {}
            for age, msg in enumerate(reversed(user_messages)):
                evidence = (msg.get('metadata') or {}).get('language_detection')
                if self._is_trusted_evidence(evidence):
                    lang = normalize_language_code(evidence['language'])
                    weights[lang] = weights.get(lang, 0.0) + evidence['confidence'] * PRIOR_RECENCY_DECAY ** age

            total = sum(weights.values())
            if total <= 0:
                return None
            return ConversationPrior({lang: w / total for lang, w in weights.items()}, source='chat_history')

        except Exception as e:  # noqa: BLE001 - best-effort read over arbitrary chat-history backends
            logger.debug(f"Could not get chat history language prior: {e}")
            return None

    async def _get_session_cache_prior(self, context: ProcessingContext) -> Optional[ConversationPrior]:
        """The session's last trusted detection, from the shared cache."""
        try:
            cache_service = self.container.get('cache_service') if self.container.has('cache_service') else None
            if not cache_service or not cache_service.enabled:
                return None
            data = await cache_service.get_json(self._session_language_key(context.session_id))
            if not self._is_trusted_evidence(data):
                return None
            return ConversationPrior({normalize_language_code(data['language']): 1.0}, source='session_cache')
        except Exception as e:  # noqa: BLE001 - best-effort cache read; no prior when the cache is unavailable
            logger.debug(f"Could not retrieve session language from cache: {e}")
            return None

    async def _save_session_language(self, context: ProcessingContext, result: DetectionResult) -> None:
        """Save a trusted detection to the session cache for stickiness."""
        if not self.enable_stickiness or not context.session_id:
            return

        data = {
            'language': result.language,
            'confidence': result.confidence,
            'method': result.method
        }
        if not self._is_trusted_evidence(data):
            return

        try:
            if self.container.has('cache_service'):
                cache_service = self.container.get('cache_service')
                if cache_service and cache_service.enabled:
                    key = self._session_language_key(context.session_id)
                    # Idle window: the entry expires this long after the last trusted
                    # detection. Unrelated to auth.session_duration_hours.
                    await cache_service.store_json(key, data, ttl=self.stickiness_ttl_seconds)
        except Exception as e:  # noqa: BLE001 - best-effort cache write must not fail the detection step
            logger.debug(f"Could not save session language to cache: {e}")

    def _session_language_key(self, session_id: str) -> str:
        """Build a cache-safe key for persisted language detection state."""
        safe_id = urllib.parse.quote(str(session_id), safe='')
        return f"lang_detect:{safe_id}"

    async def _detect_language_ensemble_async(
        self,
        text: str,
        prior: Optional[ConversationPrior] = None,
    ) -> DetectionResult:
        """
        Detect language by pooling the backends' candidate distributions.

        The current message decides first. The conversation prior is consulted
        only when the message alone yields no accepted result (too short, or
        below threshold), so a clear language switch is followed immediately.
        """
        # Pre-clean text to avoid URL/code bias
        clean_text = self._clean_text_for_detection(text or "")
        evidence = self._script_evidence(clean_text)
        if evidence.letters == 0:
            return self._prior_result(prior, reason='no_letters') or abstain('no_letters')

        # Unique-script fast path, or high-confidence Latin phrase patterns
        script_result = self._detect_by_script(clean_text, evidence)
        if script_result.confidence > 0.9:
            script_result.accepted = True
            return script_result

        # Too little text for the statistical backends: use a trustworthy
        # conversation prior if there is one, otherwise abstain.
        if evidence.letters < self.min_letters:
            return self._prior_result(prior, reason='low_evidence') or abstain(
                'low_evidence', letters=evidence.letters
            )

        candidates = self._narrow_candidates(clean_text, evidence)

        # Run all available backends in parallel
        backend_results: list[BackendResult] = []
        raw_results: dict[str, Any] = {}
        if self.backends:
            names = [name for name, _ in self.backends]
            results = await asyncio.gather(
                *(self._run_backend_with_timeout(name, func, clean_text, self.backend_timeout)
                  for name, func in self.backends),
                return_exceptions=True,
            )
            for name, result in zip(names, results):
                if isinstance(result, Exception):
                    logger.warning(f"Backend {name} failed: {result!s}")
                    raw_results[name] = {'error': str(result)}
                elif result:
                    raw_results[name] = {
                        'candidates': {lang: round(score, 4) for lang, score in result.candidates.items()},
                        'scale': result.scale,
                        'reliable': result.reliable,
                        'version': result.version,
                    }
                    # A backend answering only "unknown" (e.g. CLD2 'un') has nothing to pool.
                    if not result.abstained:
                        backend_results.append(result)

        # Pool with the parameters fitted for exactly the backends that
        # answered, so a missing or timed-out backend does not leave the
        # others weighted and thresholded as if it were present.
        backend_results = [r for r in backend_results if r.backend in self.calibration.backends]
        if not backend_results:
            return abstain('all_backends_failed', raw=raw_results)
        pool = self.calibration.for_backends(r.backend for r in backend_results)
        raw_results['pool_backends'] = sorted(r.backend for r in backend_results)

        probabilities, residual = pool_backend_distributions(
            backend_results, pool, self.calibration.universe_size
        )
        raw_results['pooled'] = {lang: round(p, 4) for lang, p in probabilities.items()}
        raw_results['residual'] = round(residual, 4)

        # A shared script restricts which languages may win. Mass outside the
        # candidates stays in the normalization, so dropping it cannot inflate
        # confidence.
        eligible = probabilities
        if candidates:
            raw_results['script_candidates'] = sorted(candidates)
            eligible = {lang: p for lang, p in probabilities.items() if lang in candidates}
            if not eligible:
                return abstain('no_candidate_votes', raw=raw_results)

        ranked = sorted(eligible.items(), key=lambda kv: (-kv[1], kv[0]))
        best_language, best_confidence = ranked[0]
        second_confidence = max((p for lang, p in probabilities.items() if lang != best_language), default=0.0)
        margin = round(best_confidence - second_confidence, 4)
        agreement = round(
            sum(result.language == best_language for result in backend_results) / len(backend_results), 4
        )

        # Check for mixed language (backend disagreement; spans arrive in Phase 4)
        if len(ranked) > 1:
            second_language, second_eligible = ranked[1]
            if second_eligible >= self.mixed_language_threshold and best_confidence < 0.8:
                raw_results['mixed_language_detected'] = True
                raw_results['secondary_language'] = second_language
                raw_results['secondary_confidence'] = second_eligible

        if best_confidence < pool.accept_confidence:
            # The conversation prior, if the current message's candidates include it
            return self._prior_result(
                prior, reason='below_threshold', supported_by=eligible, raw=raw_results,
            ) or abstain('below_threshold', raw=raw_results)

        return DetectionResult(
            language=best_language,
            confidence=best_confidence,
            method='calibrated_ensemble',
            raw_results=raw_results,
            accepted=True,
            calibrated=True,
            agreement=agreement,
            margin=margin,
        )

    async def _run_backend_with_timeout(
        self,
        backend_name: str,
        detector_func,
        text: str,
        timeout: float = 0.5
    ) -> Optional[BackendResult]:
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

    def _prior_result(
        self,
        prior: Optional[ConversationPrior],
        reason: str,
        supported_by: Optional[dict[str, float]] = None,
        **raw: Any,
    ) -> Optional[DetectionResult]:
        """The conversation prior's language, for a message that cannot decide alone.

        The prior's top language must hold at least PRIOR_MIN_SHARE of its
        weight and, when ``supported_by`` candidates are given, be among them.
        Confidence stays below retrieval_min_confidence: a prior may pick the
        reply language but should not re-rank retrieved documents.
        """
        if not prior:
            return None
        language, share = prior.top()
        if share < PRIOR_MIN_SHARE or language == UNKNOWN_LANGUAGE:
            return None
        if supported_by is not None and language not in supported_by:
            return None
        return DetectionResult(
            language=language,
            confidence=round(PRIOR_MAX_CONFIDENCE * share, 4),
            method=prior.method,
            raw_results={'reason': reason, 'prior': prior.distribution, 'prior_source': prior.source, **raw},
        )

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

    # ========================================================================
    # Backend adapters: each returns its full candidate list (BackendResult)
    # ========================================================================

    def _detect_langdetect(self, text: str) -> Optional[BackendResult]:
        """Every language langdetect's sampling assigned a probability to."""
        if not LANGDETECT_AVAILABLE:
            return None
        try:
            lang_probs = detect_langs(text)
        except LangDetectException:
            return None
        return BackendResult(
            backend='langdetect',
            candidates=candidate_scores((c.lang, c.prob) for c in lang_probs),
            scale='probability',
            version=_package_version('langdetect'),
        )

    def _detect_langid(self, text: str) -> Optional[BackendResult]:
        """langid's top-k languages, softmaxed over those k only.

        The softmax is not a probability over all languages; the raw
        log-probabilities are kept for calibration.
        """
        if not LANGID_AVAILABLE:
            return None
        try:
            top_k = langid.rank(text)[:self.calibration.langid_top_k]
        except Exception:
            logger.debug("langid detection failed", exc_info=True)
            return None
        if not top_k:
            return None
        best = max(score for _, score in top_k)
        exps = [(lang, math.exp(score - best)) for lang, score in top_k]
        total = sum(e for _, e in exps)
        return BackendResult(
            backend='langid',
            candidates=candidate_scores((lang, e / total) for lang, e in exps),
            scale='softmax_top_k',
            version=_package_version('langid'),
            raw={'log_probs': [(lang, round(float(score), 3)) for lang, score in top_k]},
        )

    def _detect_pycld2(self, text: str) -> Optional[BackendResult]:
        """pycld2's languages with their share of the text and its reliability flag."""
        if not PYCLD2_AVAILABLE:
            return None
        try:
            is_reliable, text_bytes_found, details = cld2.detect(text)
        except Exception:
            logger.debug("pycld2 detection failed", exc_info=True)
            return None
        return BackendResult(
            backend='pycld2',
            candidates=candidate_scores((code, percent / 100.0) for _, code, percent, _ in details),
            scale='text_percent',
            version=_package_version('pycld2'),
            reliable=bool(is_reliable),
            raw={
                'text_bytes': text_bytes_found,
                'details': [(code, percent, score) for _, code, percent, score in details if code != 'un'],
            },
        )
