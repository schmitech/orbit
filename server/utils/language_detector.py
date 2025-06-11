"""
Language detection service for multilingual applications - Refactored Version

This module provides a robust language detection service that can detect
languages from short text inputs with high accuracy. It handles edge cases
like short texts, product descriptions, and technical content.

Key improvements:
- Better separation of concerns with dedicated modules
- Improved error handling and logging
- More extensible pattern system
- Enhanced confidence scoring
- Better organization of language-specific logic
"""

import re
import logging
import string
import unicodedata
from typing import Dict, List, Optional, Tuple, Any, Set, Protocol
from dataclasses import dataclass, field
from collections import defaultdict
from abc import ABC, abstractmethod
from enum import Enum

# Initialize logger
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes and Enums
# =============================================================================

class ScriptType(Enum):
    """Enumeration of script types"""
    UNKNOWN = "Unknown"
    LATIN = "Latin"
    CYRILLIC = "Cyrillic"
    CHINESE = "Chinese"
    KOREAN = "Korean"
    JAPANESE = "Japanese"
    ARABIC = "Arabic"
    DEVANAGARI = "Devanagari"
    HEBREW = "Hebrew"
    GREEK = "Greek"


@dataclass
class ScriptInfo:
    """Information about the script used in text"""
    script_type: ScriptType
    script_ratios: Dict[str, float] = field(default_factory=dict)
    
    @property
    def primary_script(self) -> ScriptType:
        """Get the primary script type"""
        return self.script_type
    
    @property
    def is_cjk(self) -> bool:
        """Check if the script is CJK"""
        return self.script_type in {ScriptType.CHINESE, ScriptType.KOREAN, ScriptType.JAPANESE}
    
    def get_ratio(self, script: str) -> float:
        """Get ratio for a specific script"""
        return self.script_ratios.get(script, 0.0)


@dataclass
class CharStats:
    """Character statistics for text analysis"""
    alpha_ratio: float
    digit_ratio: float
    punct_ratio: float
    space_ratio: float
    special_ratio: float = 0.0
    
    @property
    def is_mostly_alphabetic(self) -> bool:
        """Check if text is mostly alphabetic"""
        return self.alpha_ratio > 0.5
    
    @property
    def is_technical(self) -> bool:
        """Check if text appears to be technical content"""
        return self.digit_ratio + self.punct_ratio > 0.4


@dataclass
class DetectionResult:
    """Result of language detection"""
    language: str
    confidence: float
    script: ScriptType
    method: str = "unknown"
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_confident(self) -> bool:
        """Check if detection is confident"""
        return self.confidence >= 0.7


# =============================================================================
# Language Pattern Repository
# =============================================================================

class LanguagePatternRepository:
    """Centralized repository for language-specific patterns and indicators"""
    
    def __init__(self):
        self._patterns = self._initialize_patterns()
    
    def _initialize_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Initialize all language patterns"""
        return {
            'en': {
                'starters': {
                    "who", "what", "when", "where", "why", "how", "which",
                    "can", "could", "will", "would", "should", "shall", "may", "might", "must",
                    "do", "does", "did", "don't", "doesn't", "didn't", "won't", "wouldn't",
                    "shouldn't", "can't", "couldn't", "isn't", "aren't", "wasn't", "weren't",
                    "have", "has", "had", "haven't", "hasn't", "hadn't"
                },
                'phrases': {
                    "can you", "could you", "will you", "would you", "do you", "did you",
                    "are you", "is it", "was it", "were you", "have you", "has it",
                    "what is", "where is", "how to", "why does", "when will"
                },
                'common_words': {
                    "the", "be", "to", "of", "and", "a", "in", "that", "it",
                    "for", "not", "on", "with", "he", "as", "you", "at", "this"
                },
                'character_freq': {'e': 12.7, 't': 9.1, 'a': 8.2, 'o': 7.5, 'i': 7.0}
            },
            'fr': {
                'indicators': [
                    "c'est", "qu'est", "qu'il", "qu'elle", "n'est", "n'a", 
                    "j'ai", "j'aime", "ça", "où", "d'un", "d'une", "l'est"
                ],
                'accents': ['é', 'è', 'ê', 'ë', 'à', 'â', 'ù', 'û', 'ç', 'ô', 'î', 'ï'],
                'common_words': {
                    "le", "de", "un", "être", "et", "à", "il", "avoir", "ne",
                    "je", "son", "que", "se", "qui", "ce", "dans", "en", "du"
                },
                'character_freq': {'e': 14.7, 'a': 7.6, 's': 7.9, 'i': 7.5, 't': 7.2}
            },
            'es': {
                'accents': ['á', 'é', 'í', 'ó', 'ú', 'ñ', 'ü'],
                'indicators': ["qué", "cómo", "dónde", "cuándo", "por qué"],
                'common_words': {
                    "el", "la", "de", "que", "y", "a", "en", "un", "ser",
                    "se", "no", "haber", "por", "con", "su", "para", "como"
                },
                'character_freq': {'e': 13.7, 'a': 12.5, 'o': 8.7, 's': 8.0, 'n': 6.7}
            },
            'de': {
                'accents': ['ä', 'ö', 'ü', 'ß'],
                'indicators': ["ich", "du", "er", "sie", "es", "wir", "ihr"],
                'common_words': {
                    "der", "die", "und", "in", "den", "von", "zu", "das",
                    "mit", "sich", "des", "auf", "für", "ist", "im", "dem"
                },
                'character_freq': {'e': 17.4, 'n': 9.8, 'i': 7.6, 's': 7.3, 'r': 7.0}
            },
            'it': {
                'accents': ['à', 'è', 'é', 'ì', 'ò', 'ù'],
                'indicators': ["è", "c'è", "perché", "più", "già"],
                'common_words': {
                    "di", "e", "il", "la", "che", "è", "per", "un", "in",
                    "non", "con", "si", "da", "come", "io", "questo", "ha"
                },
                'character_freq': {'e': 11.8, 'a': 11.7, 'i': 11.3, 'o': 9.8, 'n': 6.9}
            },
            'pt': {
                'accents': ['á', 'â', 'ã', 'à', 'ç', 'é', 'ê', 'í', 'ó', 'ô', 'õ', 'ú'],
                'indicators': ["não", "são", "está", "ção", "ões"],
                'common_words': {
                    "de", "a", "o", "que", "e", "do", "da", "em", "um",
                    "para", "é", "com", "não", "uma", "os", "no", "se"
                }
            },
            'ru': {
                'indicators': ["что", "это", "как", "где", "когда", "почему"],
                'common_words': {
                    "и", "в", "не", "на", "я", "что", "тот", "быть", "с",
                    "а", "весь", "это", "как", "она", "по", "но", "они"
                }
            },
            'mn': {
                'indicators': [
                    'бэр', 'гийн', 'хэд', 'хураамж', 'зогсоол', 'зөв', 'шөөрл',
                    'байх', 'болох', 'хийх', 'ийн', 'лын', 'ын', 'гэх', 'юу',
                    'энэ', 'тэр', 'настай', 'вэ', 'би', 'монгол', 'хүн', 'байна',
                    'яаж', 'нийслэл', 'хаана', 'байдаг', 'өө', 'үү'
                ],
                'patterns': [
                    'ийн', 'гийн', 'лын', 'хэд', 'өө', 'үү', 'эр', 'өр',
                    'энэ', 'юу', ' вэ', 'хүн', 'яаж', 'байна', 'байдаг'
                ],
                'special_chars': ['ө', 'ү'],
                'endings': [' вэ', ' уу', ' үү', ' юу', ' бэ']
            },
            'zh': {
                'common_chars': ['的', '一', '是', '了', '我', '不', '人', '在', '他', '有'],
                'indicators': ['吗', '呢', '吧', '啊', '么', '了']
            },
            'ja': {
                'particles': ['は', 'が', 'を', 'に', 'の', 'で', 'と', 'も', 'や', 'か'],
                'indicators': ['です', 'ます', 'でした', 'ました', 'ですか', 'ますか']
            },
            'ko': {
                'particles': ['은', '는', '이', '가', '을', '를', '에', '에서', '으로', '와'],
                'indicators': ['입니다', '습니다', '니다', '까요', '세요', '어요', '요']
            }
        }
    
    def get_patterns(self, language: str) -> Dict[str, Any]:
        """Get patterns for a specific language"""
        return self._patterns.get(language, {})
    
    def get_all_accented_chars(self) -> Set[str]:
        """Get all accented characters from all languages"""
        accented = set()
        for lang_patterns in self._patterns.values():
            if 'accents' in lang_patterns:
                accented.update(lang_patterns['accents'])
        return accented
    
    def get_language_by_accent(self, char: str) -> List[str]:
        """Get languages that use a specific accented character"""
        languages = []
        for lang, patterns in self._patterns.items():
            if 'accents' in patterns and char in patterns['accents']:
                languages.append(lang)
        return languages


# =============================================================================
# Script Analyzer
# =============================================================================

class ScriptAnalyzer:
    """Handles script analysis operations"""
    
    def __init__(self):
        self.script_ranges = self._initialize_script_ranges()
    
    def _initialize_script_ranges(self) -> Dict[str, List[Tuple[int, int]]]:
        """Initialize Unicode ranges for different scripts"""
        return {
            'latin': [(0x0000, 0x007F), (0x0080, 0x00FF), (0x0100, 0x017F), (0x0180, 0x024F)],
            'cyrillic': [(0x0400, 0x04FF), (0x0500, 0x052F)],
            'greek': [(0x0370, 0x03FF), (0x1F00, 0x1FFF)],
            'arabic': [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)],
            'hebrew': [(0x0590, 0x05FF)],
            'devanagari': [(0x0900, 0x097F), (0x0980, 0x09FF)],
            'chinese': [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x20000, 0x2A6DF)],
            'japanese': [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF)],
            'korean': [(0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)]
        }
    
    def analyze_script(self, text: str) -> ScriptInfo:
        """Analyze the script used in the text"""
        if not text:
            return ScriptInfo(ScriptType.UNKNOWN)
        
        char_counts = defaultdict(int)
        total_chars = 0
        
        for char in text:
            if not char.isalpha():
                continue
            
            total_chars += 1
            script = self._identify_script(char)
            char_counts[script] += 1
        
        if total_chars == 0:
            return ScriptInfo(ScriptType.UNKNOWN)
        
        # Calculate ratios
        script_ratios = {script: count / total_chars for script, count in char_counts.items()}
        
        # Determine primary script
        primary_script = self._determine_primary_script(script_ratios)
        
        return ScriptInfo(primary_script, script_ratios)
    
    def _identify_script(self, char: str) -> str:
        """Identify the script of a character"""
        code_point = ord(char)
        
        for script, ranges in self.script_ranges.items():
            for start, end in ranges:
                if start <= code_point <= end:
                    return script
        
        # Fallback to Unicode name analysis
        try:
            name = unicodedata.name(char, "UNKNOWN")
            category = name.split()[0].lower()
            
            script_mapping = {
                'latin': 'latin',
                'cyrillic': 'cyrillic',
                'cjk': 'chinese',
                'hangul': 'korean',
                'hiragana': 'japanese',
                'katakana': 'japanese',
                'arabic': 'arabic',
                'hebrew': 'hebrew',
                'devanagari': 'devanagari',
                'greek': 'greek'
            }
            
            return script_mapping.get(category, 'unknown')
        except:
            return 'unknown'
    
    def _determine_primary_script(self, script_ratios: Dict[str, float]) -> ScriptType:
        """Determine the primary script type"""
        if not script_ratios:
            return ScriptType.UNKNOWN
        
        max_ratio = max(script_ratios.values())
        if max_ratio < 0.5:
            return ScriptType.UNKNOWN
        
        script_map = {
            'latin': ScriptType.LATIN,
            'cyrillic': ScriptType.CYRILLIC,
            'chinese': ScriptType.CHINESE,
            'korean': ScriptType.KOREAN,
            'japanese': ScriptType.JAPANESE,
            'arabic': ScriptType.ARABIC,
            'hebrew': ScriptType.HEBREW,
            'devanagari': ScriptType.DEVANAGARI,
            'greek': ScriptType.GREEK
        }
        
        for script, ratio in script_ratios.items():
            if ratio == max_ratio:
                return script_map.get(script, ScriptType.UNKNOWN)
        
        return ScriptType.UNKNOWN


# =============================================================================
# Text Analyzer
# =============================================================================

class TextAnalyzer:
    """Handles text analysis operations"""
    
    def __init__(self):
        self.script_analyzer = ScriptAnalyzer()
    
    def calculate_char_stats(self, text: str) -> CharStats:
        """Calculate character statistics for a text"""
        if not text:
            return CharStats(0, 0, 0, 0, 0)
        
        total_len = len(text)
        alpha_count = sum(c.isalpha() for c in text)
        digit_count = sum(c.isdigit() for c in text)
        punct_count = sum(c in string.punctuation for c in text)
        space_count = sum(c.isspace() for c in text)
        special_count = total_len - alpha_count - digit_count - punct_count - space_count
        
        return CharStats(
            alpha_ratio=alpha_count / total_len,
            digit_ratio=digit_count / total_len,
            punct_ratio=punct_count / total_len,
            space_ratio=space_count / total_len,
            special_ratio=special_count / total_len
        )
    
    def analyze_script(self, text: str) -> ScriptInfo:
        """Analyze the script used in the text"""
        return self.script_analyzer.analyze_script(text)
    
    def generate_text_variations(self, text: str) -> List[str]:
        """Generate variations of the input text to improve detection reliability"""
        variations = [text]
        text_len = len(text)
        
        # Remove punctuation variation
        text_no_punct = re.sub(r'[^\w\s]', '', text)
        if text_no_punct != text and text_no_punct.strip():
            variations.append(text_no_punct)
        
        # Handle very short text
        if text_len < 20:
            # Duplication for better detection
            if not self._contains_code_indicators(text):
                variations.append(text + " " + text)
            
            # Lowercase variation for very short text
            if text_len < 10:
                variations.append(text.lower())
        
        # Handle medium-length text
        elif text_len < 60:
            if self._contains_code_indicators(text):
                variations.append(text + " " + text)
            else:
                variations.append(text + ". " + text)
        
        # Handle technical content
        elif text_len < 120 and self._contains_code_indicators(text):
            variations.append("Code example: " + text)
        
        return list(dict.fromkeys(variations))  # Remove duplicates while preserving order
    
    def _contains_code_indicators(self, text: str) -> bool:
        """Check if text contains code indicators"""
        code_indicators = {'{}', '[]', '()', '<>', '=>', '->', '==', '!=', '&&', '||'}
        return any(indicator in text for indicator in code_indicators)
    
    def extract_ngrams(self, text: str, n: int = 2) -> List[str]:
        """Extract n-grams from text"""
        words = text.lower().split()
        if len(words) < n:
            return []
        return [' '.join(words[i:i+n]) for i in range(len(words) - n + 1)]
    
    def calculate_text_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of the text"""
        if not text:
            return 0.0
        
        char_freq = defaultdict(int)
        for char in text:
            char_freq[char] += 1
        
        total_chars = len(text)
        entropy = 0.0
        
        for count in char_freq.values():
            probability = count / total_chars
            if probability > 0:
                entropy -= probability * (probability if probability == 1 else 
                                        probability * (1 / probability).bit_length())
        
        return entropy


# =============================================================================
# Language Detector Interface
# =============================================================================

class LanguageDetectorInterface(Protocol):
    """Interface for language detection backends"""
    
    def detect(self, text: str) -> Tuple[Optional[str], float]:
        """Detect language and return (language_code, confidence)"""
        ...


# =============================================================================
# Detector Implementations
# =============================================================================

class LangDetectBackend:
    """Langdetect backend implementation"""
    
    def __init__(self):
        self._detector = None
        self._exception = None
        self._initialize()
    
    def _initialize(self):
        """Initialize the langdetect library"""
        try:
            from langdetect import detect_langs, DetectorFactory
            from langdetect.lang_detect_exception import LangDetectException
            
            DetectorFactory.seed = 0
            self._detect_langs = detect_langs
            self._exception = LangDetectException
            self._detector = True
        except ImportError:
            logger.warning("langdetect not available")
    
    def detect(self, text: str) -> Tuple[Optional[str], float]:
        """Detect language using langdetect"""
        if not self._detector:
            return None, 0.0
        
        try:
            results = self._detect_langs(text)
            if results:
                return results[0].lang, results[0].prob
        except Exception:
            pass
        
        return None, 0.0


class LangIdBackend:
    """Langid backend implementation"""
    
    def __init__(self):
        self._detector = None
        self._initialize()
    
    def _initialize(self):
        """Initialize the langid library"""
        try:
            import langid
            self._detector = langid.classify
        except ImportError:
            logger.debug("langid not available")
    
    def detect(self, text: str) -> Tuple[Optional[str], float]:
        """Detect language using langid"""
        if not self._detector:
            return None, 0.0
        
        try:
            lang, confidence = self._detector(text)
            
            # Fix langid's negative confidence scores
            # Langid returns negative log probabilities, we need to convert them
            if confidence < 0:
                # Convert negative log probability to a more reasonable confidence score
                # Higher absolute values (more negative) mean lower confidence
                confidence = max(0.0, 1.0 + confidence / 100.0)  # Normalize to 0-1 range
            
            # Ensure confidence is in valid range
            confidence = max(0.0, min(1.0, confidence))
            
            return lang, confidence
        except Exception:
            return None, 0.0


class PyCLD2Backend:
    """PyCLD2 backend implementation"""
    
    def __init__(self):
        self._detector = None
        self._initialize()
    
    def _initialize(self):
        """Initialize the pycld2 library"""
        try:
            import pycld2
            self._detector = pycld2.detect
        except ImportError:
            logger.debug("pycld2 not available")
    
    def detect(self, text: str) -> Tuple[Optional[str], float]:
        """Detect language using pycld2"""
        if not self._detector:
            return None, 0.0
        
        try:
            is_reliable, text_bytes_found, details = self._detector(text)
            if is_reliable and details:
                confidence = min(1.0, text_bytes_found / len(text))
                return details[0][1], confidence
        except Exception:
            pass
        
        return None, 0.0


# =============================================================================
# Specialized Language Detectors
# =============================================================================

class EnglishDetector:
    """Specialized detector for English language"""
    
    def __init__(self, pattern_repo: LanguagePatternRepository):
        self.patterns = pattern_repo.get_patterns('en')
    
    def is_likely_english(self, text: str, script_info: ScriptInfo) -> bool:
        """Quick check for likely English text"""
        if script_info.script_type != ScriptType.LATIN:
            return False
        
        words = text.split()
        if not words:
            return False
        
        first_word = words[0].lower()
        
        # Check starters
        if first_word in self.patterns.get('starters', set()):
            return True
        
        # Check phrases
        if len(words) >= 2:
            two_word_start = f"{words[0].lower()} {words[1].lower()}"
            if two_word_start in self.patterns.get('phrases', set()):
                return True
        
        # Check common words
        common_words = self.patterns.get('common_words', set())
        text_words = set(word.lower() for word in words)
        common_count = len(text_words & common_words)
        
        return common_count >= min(3, len(words) // 2)


class CyrillicLanguageDetector:
    """Specialized detector for Cyrillic languages"""
    
    def __init__(self, pattern_repo: LanguagePatternRepository):
        self.pattern_repo = pattern_repo
    
    def detect_cyrillic_language(self, text: str) -> Optional[str]:
        """Detect specific Cyrillic language"""
        text_lower = text.lower()
        
        # Check for Mongolian
        if self._is_mongolian(text_lower):
            return 'mn'
        
        # Check for Russian
        if self._is_russian(text_lower):
            return 'ru'
        
        # Could add more Cyrillic languages here (Ukrainian, Bulgarian, etc.)
        return 'ru'  # Default to Russian
    
    def _is_mongolian(self, text_lower: str) -> bool:
        """Check if text is Mongolian Cyrillic"""
        patterns = self.pattern_repo.get_patterns('mn')
        
        # Count indicators
        indicator_count = sum(1 for indicator in patterns.get('indicators', [])
                            if indicator in text_lower)
        pattern_count = sum(1 for pattern in patterns.get('patterns', [])
                          if pattern in text_lower)
        
        # Count special characters
        special_char_count = sum(text_lower.count(char) 
                               for char in patterns.get('special_chars', []))
        
        # Check endings
        for ending in patterns.get('endings', []):
            if text_lower.endswith(ending):
                return True
        
        # Decision logic
        if indicator_count >= 2 or pattern_count >= 2:
            return True
        
        if special_char_count >= 2 and (indicator_count >= 1 or pattern_count >= 1):
            return True
        
        return False
    
    def _is_russian(self, text_lower: str) -> bool:
        """Check if text is Russian"""
        patterns = self.pattern_repo.get_patterns('ru')
        indicators = patterns.get('indicators', [])
        common_words = patterns.get('common_words', set())
        
        # Count indicators
        indicator_count = sum(1 for indicator in indicators if indicator in text_lower)
        
        # Count common words
        words = text_lower.split()
        common_count = sum(1 for word in words if word in common_words)
        
        return indicator_count >= 1 or common_count >= 2


# =============================================================================
# Confidence Calculator
# =============================================================================

class ConfidenceCalculator:
    """Calculates confidence scores for language detection"""
    
    def calculate_ensemble_confidence(self, 
                                    language_votes: Dict[str, float],
                                    target_language: str) -> float:
        """Calculate confidence from ensemble votes"""
        total_positive_votes = sum(max(0, vote) for vote in language_votes.values())
        
        if total_positive_votes == 0:
            return 0.0
        
        target_votes = max(0, language_votes.get(target_language, 0))
        base_confidence = target_votes / total_positive_votes
        
        # Adjust confidence based on vote distribution
        vote_values = list(language_votes.values())
        if len(vote_values) > 1:
            vote_values.sort(reverse=True)
            margin = (vote_values[0] - vote_values[1]) / max(vote_values[0], 1)
            base_confidence = base_confidence * (0.8 + 0.2 * margin)
        
        return min(1.0, base_confidence)
    
    def adjust_confidence_by_features(self,
                                    base_confidence: float,
                                    text: str,
                                    script_info: ScriptInfo,
                                    char_stats: CharStats) -> float:
        """Adjust confidence based on text features"""
        confidence = base_confidence
        
        # Boost confidence for longer texts
        text_len = len(text)
        if text_len > 100:
            confidence *= 1.1
        elif text_len < 20:
            confidence *= 0.9
        
        # Boost confidence for pure script texts
        primary_ratio = max(script_info.script_ratios.values()) if script_info.script_ratios else 0
        if primary_ratio > 0.95:
            confidence *= 1.05
        
        # Reduce confidence for technical content
        if char_stats.is_technical:
            confidence *= 0.95
        
        return min(1.0, confidence)


# =============================================================================
# Main Language Detector
# =============================================================================

class LanguageDetector:
    """
    Robust language detection class suitable for multilingual applications.
    
    This refactored version provides:
    - Better separation of concerns
    - More maintainable code structure
    - Enhanced extensibility
    - Improved error handling
    - Better confidence scoring
    """
    
    def __init__(self, 
                 verbose: bool = False, 
                 min_confidence: float = 0.7,
                 enable_backends: Optional[List[str]] = None):
        """
        Initialize the language detector
        
        Args:
            verbose: Enable verbose logging
            min_confidence: Minimum confidence threshold
            enable_backends: List of backends to enable (None = all available)
        """
        self.verbose = verbose
        self.min_confidence = min_confidence
        
        # Initialize components
        self.pattern_repo = LanguagePatternRepository()
        self.text_analyzer = TextAnalyzer()
        self.confidence_calc = ConfidenceCalculator()
        
        # Initialize backends
        self.backends = self._initialize_backends(enable_backends)
        
        # Initialize specialized detectors
        self.english_detector = EnglishDetector(self.pattern_repo)
        self.cyrillic_detector = CyrillicLanguageDetector(self.pattern_repo)
        
        # Log initialization
        if self.backends:
            backend_names = list(self.backends.keys())
            logger.info(f"Initialized with {len(backend_names)} backends: {', '.join(backend_names)}")
        else:
            logger.error("No language detection backends available!")
    
    def _initialize_backends(self, enable_backends: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """Initialize detection backends"""
        available_backends = {
            'langdetect': (LangDetectBackend, 1.0),
            'langid': (LangIdBackend, 1.2),
            'pycld2': (PyCLD2Backend, 1.5)
        }
        
        backends = {}
        
        for name, (backend_class, weight) in available_backends.items():
            if enable_backends and name not in enable_backends:
                continue
            
            try:
                backend = backend_class()
                # Test if backend works
                test_result = backend.detect("test")
                if test_result[0] is not None:
                    backends[name] = {
                        'backend': backend,
                        'weight': weight
                    }
                    if self.verbose:
                        logger.info(f"Loaded {name} backend")
            except Exception as e:
                if self.verbose:
                    logger.debug(f"Failed to load {name}: {str(e)}")
        
        return backends
    
    def detect(self, text: str) -> str:
        """
        Detect the language of the input text
        
        Args:
            text: Input text to detect
            
        Returns:
            ISO 639-1 language code
        """
        result = self.detect_with_details(text)
        return result.language
    
    def detect_with_details(self, text: str) -> DetectionResult:
        """
        Detect language with detailed results
        
        Args:
            text: Input text to detect
            
        Returns:
            DetectionResult with language, confidence, and details
        """
        try:
            # Preprocess text
            text = text.strip()
            
            # Handle empty or very short text
            if not text or len(text) < 3:
                return DetectionResult(
                    language="en",
                    confidence=0.5,
                    script=ScriptType.UNKNOWN,
                    method="default_short"
                )
            
            # Analyze text characteristics
            char_stats = self.text_analyzer.calculate_char_stats(text)
            script_info = self.text_analyzer.analyze_script(text)
            
            # Quick English detection
            if self.english_detector.is_likely_english(text, script_info):
                return DetectionResult(
                    language="en",
                    confidence=0.95,
                    script=script_info.script_type,
                    method="quick_english"
                )
            
            # Handle CJK languages
            if script_info.is_cjk:
                return self._handle_cjk_detection(text, script_info)
            
            # Handle Cyrillic languages
            if script_info.script_type == ScriptType.CYRILLIC:
                lang = self.cyrillic_detector.detect_cyrillic_language(text)
                if lang:
                    return DetectionResult(
                        language=lang,
                        confidence=0.9,
                        script=script_info.script_type,
                        method="cyrillic_specialized"
                    )
            
            # Handle Arabic script
            if script_info.script_type == ScriptType.ARABIC:
                return DetectionResult(
                    language="ar",
                    confidence=0.9,
                    script=script_info.script_type,
                    method="script_based"
                )
            
            # Perform ensemble detection for other cases
            return self._ensemble_detect(text, script_info, char_stats)
            
        except Exception as e:
            logger.error(f"Language detection failed: {str(e)}")
            return DetectionResult(
                language="en",
                confidence=0.0,
                script=ScriptType.UNKNOWN,
                method="error_fallback"
            )
    
    def _handle_cjk_detection(self, text: str, script_info: ScriptInfo) -> DetectionResult:
        """Handle detection for CJK languages"""
        script_to_lang = {
            ScriptType.CHINESE: 'zh',
            ScriptType.KOREAN: 'ko',
            ScriptType.JAPANESE: 'ja'
        }
        
        language = script_to_lang.get(script_info.script_type, 'zh')
        
        # For mixed CJK scripts, use pattern matching
        if script_info.get_ratio('chinese') > 0 and script_info.get_ratio('japanese') > 0:
            # Check for Japanese particles
            ja_patterns = self.pattern_repo.get_patterns('ja')
            if any(particle in text for particle in ja_patterns.get('particles', [])):
                language = 'ja'
        
        return DetectionResult(
            language=language,
            confidence=0.95,
            script=script_info.script_type,
            method="cjk_script"
        )
    
    def _ensemble_detect(self, 
                        text: str, 
                        script_info: ScriptInfo,
                        char_stats: CharStats) -> DetectionResult:
        """Perform ensemble detection using multiple backends"""
        if not self.backends:
            return DetectionResult(
                language="en",
                confidence=0.0,
                script=script_info.script_type,
                method="no_backends"
            )
        
        # Generate text variations
        variations = self.text_analyzer.generate_text_variations(text)
        
        # Collect votes from all backends
        language_votes = defaultdict(float)
        detection_details = defaultdict(list)
        
        for backend_name, backend_info in self.backends.items():
            backend = backend_info['backend']
            weight = backend_info['weight']
            
            # Try original text first
            lang, confidence = backend.detect(text)
            if lang:
                weighted_vote = weight * confidence
                language_votes[lang] += weighted_vote
                detection_details[lang].append(f"{backend_name}:{confidence:.2f}")
            
            # Try variations for langdetect
            if backend_name == 'langdetect' and len(variations) > 1:
                for variation in variations[1:]:  # Skip first (original)
                    lang, confidence = backend.detect(variation)
                    if lang:
                        weighted_vote = weight * confidence * 0.8  # Slightly lower weight
                        language_votes[lang] += weighted_vote
                        detection_details[lang].append(f"{backend_name}_var:{confidence:.2f}")
        
        # Apply pattern-based adjustments
        self._apply_pattern_adjustments(text, language_votes, script_info)
        
        # Calculate final result
        if not language_votes:
            return DetectionResult(
                language="en",
                confidence=0.0,
                script=script_info.script_type,
                method="no_detections"
            )
        
        # Get most likely language
        sorted_votes = sorted(language_votes.items(), key=lambda x: x[1], reverse=True)
        best_lang = sorted_votes[0][0]
        
        # Calculate confidence
        base_confidence = self.confidence_calc.calculate_ensemble_confidence(
            language_votes, best_lang
        )
        final_confidence = self.confidence_calc.adjust_confidence_by_features(
            base_confidence, text, script_info, char_stats
        )
        
        # Log details if verbose
        if self.verbose:
            self._log_detection_details(sorted_votes, final_confidence, detection_details)
        
        return DetectionResult(
            language=best_lang,
            confidence=final_confidence,
            script=script_info.script_type,
            method="ensemble",
            details={
                'votes': dict(language_votes),
                'backends': detection_details
            }
        )
    
    def _apply_pattern_adjustments(self, 
                                  text: str,
                                  language_votes: Dict[str, float],
                                  script_info: ScriptInfo) -> None:
        """Apply pattern-based adjustments to language votes"""
        import re
        
        text_lower = text.lower()
        
        # Check for language-specific indicators with much stronger weights
        for lang in ['fr', 'es', 'de', 'it', 'pt']:
            patterns = self.pattern_repo.get_patterns(lang)
            
            # Check indicators with strong boost - USE WORD BOUNDARIES
            indicators = patterns.get('indicators', [])
            if indicators:
                found_indicators = []
                for indicator in indicators:
                    # Use word boundaries to prevent false positives like "sabes" matching "es"
                    pattern = r'\b' + re.escape(indicator) + r'\b'
                    if re.search(pattern, text_lower):
                        found_indicators.append(indicator)
                
                if found_indicators:
                    # Give strong boost for found indicators
                    boost = 3.0 * len(found_indicators)
                    language_votes[lang] = language_votes.get(lang, 0.0) + boost
                    logger.debug(f"Language {lang}: +{boost} for indicators {found_indicators}")
            
            # Check accents (these are still character-based, so no word boundaries needed)
            accents = patterns.get('accents', [])
            if accents and any(accent in text for accent in accents):
                accent_count = sum(text.count(accent) for accent in accents if accent in text)
                boost = 2.0 * accent_count
                language_votes[lang] = language_votes.get(lang, 0.0) + boost
                logger.debug(f"Language {lang}: +{boost} for {accent_count} accent characters")
            
            # Check common words with word boundaries
            common_words = patterns.get('common_words', set())
            if common_words:
                found_words = []
                for word in common_words:
                    pattern = r'\b' + re.escape(word) + r'\b'
                    if re.search(pattern, text_lower):
                        found_words.append(word)
                
                if found_words:
                    # Moderate boost for common words (less than indicators)
                    boost = 1.0 * len(found_words)
                    language_votes[lang] = language_votes.get(lang, 0.0) + boost
                    logger.debug(f"Language {lang}: +{boost} for common words {found_words}")
        
        # Add specific fixes for Spanish question words that might be missed
        spanish_question_indicators = [
            'qué', 'cuál', 'cuáles', 'cómo', 'dónde', 'cuándo', 'por qué',
            'quién', 'quiénes', 'cuánto', 'cuánta', 'cuántos', 'cuántas'
        ]
        
        found_spanish_questions = []
        for indicator in spanish_question_indicators:
            pattern = r'\b' + re.escape(indicator) + r'\b'
            if re.search(pattern, text_lower):
                found_spanish_questions.append(indicator)
        
        if found_spanish_questions:
            boost = 4.0 * len(found_spanish_questions)  # Strong boost for Spanish questions
            language_votes['es'] = language_votes.get('es', 0.0) + boost
            logger.debug(f"Spanish: +{boost} for question words {found_spanish_questions}")
        
        # Add specific Spanish patterns that distinguish it from Portuguese
        spanish_specific_patterns = [
            'sabes', 'sabe', 'sabemos', 'sabéis', 'saben',  # "saber" conjugations more common in Spanish
            'hasta', 'ahora', 'luego', 'entonces', 'después',  # Spanish temporal words
            'de mi', 'de ti', 'de él', 'de ella',  # Spanish possessive patterns
            'dos', 'tres', 'cuatro', 'cinco',  # Spanish numbers
            'cervezas', 'cerveza', 'favor', 'por favor',  # Common Spanish words
            'hablas', 'habla', 'hablamos', 'habláis', 'hablan',  # "hablar" conjugations
            'podrías', 'podrían', 'ayudarme', 'encontrar', 'estación',  # More Spanish words
        ]
        
        found_spanish_specific = []
        for pattern in spanish_specific_patterns:
            regex_pattern = r'\b' + re.escape(pattern) + r'\b'
            if re.search(regex_pattern, text_lower):
                found_spanish_specific.append(pattern)
        
        if found_spanish_specific:
            boost = 2.0 * len(found_spanish_specific)  # Strong boost for Spanish-specific patterns
            language_votes['es'] = language_votes.get('es', 0.0) + boost
            logger.debug(f"Spanish: +{boost} for specific patterns {found_spanish_specific}")
        
        # Add specific Portuguese patterns that distinguish it from Spanish
        portuguese_specific_patterns = [
            'onde', 'fica', 'banheiro', 'você', 'está',  # Portuguese-specific words
            'não', 'são', 'estão', 'têm', 'vêm',  # Portuguese verb forms
            'ção', 'ões', 'ãe', 'õe',  # Portuguese endings
            'muito', 'tudo', 'bem', 'agora', 'fazer',  # Common Portuguese words
        ]
        
        found_portuguese_specific = []
        for pattern in portuguese_specific_patterns:
            regex_pattern = r'\b' + re.escape(pattern) + r'\b'
            if re.search(regex_pattern, text_lower):
                found_portuguese_specific.append(pattern)
        
        if found_portuguese_specific:
            boost = 3.0 * len(found_portuguese_specific)  # Strong boost for Portuguese-specific patterns
            language_votes['pt'] = language_votes.get('pt', 0.0) + boost
            logger.debug(f"Portuguese: +{boost} for specific patterns {found_portuguese_specific}")
        
        # Special Spanish question mark detection
        if text.startswith('¿') or '¿' in text:
            boost = 3.0
            language_votes['es'] = language_votes.get('es', 0.0) + boost
            logger.debug(f"Spanish: +{boost} for inverted question marks")
        
        # Add specific fixes for French question words
        french_question_indicators = [
            'quel', 'quelle', 'quels', 'quelles', 'comment', 'où', 'quand', 'pourquoi',
            'qui', 'combien', 'qu\'est-ce'
        ]
        
        found_french_questions = []
        for indicator in french_question_indicators:
            pattern = r'\b' + re.escape(indicator) + r'\b'
            if re.search(pattern, text_lower):
                found_french_questions.append(indicator)
        
        if found_french_questions:
            boost = 4.0 * len(found_french_questions)  # Strong boost for French questions
            language_votes['fr'] = language_votes.get('fr', 0.0) + boost
            logger.debug(f"French: +{boost} for question words {found_french_questions}")
        
        # Character frequency analysis (keep existing logic)
        for lang in ['fr', 'es', 'de', 'it', 'pt']:
            patterns = self.pattern_repo.get_patterns(lang)
            char_freq = patterns.get('character_freq', {})
            if char_freq and len(text) > 10:  # Only for longer texts
                score = 0.0
                for char, expected_freq in char_freq.items():
                    actual_freq = (text_lower.count(char) / len(text)) * 100
                    # Give positive score if frequency is close to expected
                    if abs(actual_freq - expected_freq) < 3.0:
                        score += 0.3
                
                if score > 0:
                    language_votes[lang] = language_votes.get(lang, 0.0) + score
                    logger.debug(f"Language {lang}: +{score:.2f} for character frequency match")
    
    def _log_detection_details(self,
                             sorted_votes: List[Tuple[str, float]],
                             confidence: float,
                             detection_details: Dict[str, List[str]]) -> None:
        """Log detailed detection information"""
        vote_str = ", ".join([f"{lang}: {score:.2f}" for lang, score in sorted_votes[:5]])
        logger.debug(f"Top votes: {vote_str}, confidence: {confidence:.2f}")
        
        for lang, details in list(detection_details.items())[:3]:
            detail_str = ", ".join(details)
            logger.debug(f"Details for {lang}: {detail_str}")
    
    def detect_batch(self, texts: List[str], n_jobs: int = 1) -> List[DetectionResult]:
        """
        Detect languages for a batch of texts
        
        Args:
            texts: List of texts to detect
            n_jobs: Number of parallel jobs (currently only supports 1)
            
        Returns:
            List of DetectionResult objects
        """
        return [self.detect_with_details(text) for text in texts]
    
    def get_supported_languages(self) -> List[str]:
        """Get list of supported language codes"""
        return list(self.pattern_repo._patterns.keys())


# =============================================================================
# Convenience Functions
# =============================================================================

def create_language_detector(verbose: bool = False,
                           min_confidence: float = 0.7) -> LanguageDetector:
    """
    Create a language detector instance with default settings
    
    Args:
        verbose: Enable verbose logging
        min_confidence: Minimum confidence threshold
        
    Returns:
        Configured LanguageDetector instance
    """
    return LanguageDetector(verbose=verbose, min_confidence=min_confidence)


def detect_language(text: str) -> str:
    """
    Quick function to detect language of a single text
    
    Args:
        text: Input text
        
    Returns:
        ISO 639-1 language code
    """
    detector = create_language_detector()
    return detector.detect(text)


def detect_language_with_confidence(text: str) -> Tuple[str, float]:
    """
    Detect language and return confidence score
    
    Args:
        text: Input text
        
    Returns:
        Tuple of (language_code, confidence)
    """
    detector = create_language_detector()
    result = detector.detect_with_details(text)
    return result.language, result.confidence