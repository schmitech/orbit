"""
Language detection service for multilingual applications

This module provides a robust language detection service that can detect
languages from short text inputs with high accuracy. It handles edge cases
like short texts, product descriptions, and technical content.
"""

import re
import logging
import string
import unicodedata
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass
from collections import defaultdict

# Initialize logger
logger = logging.getLogger(__name__)

@dataclass
class ScriptInfo:
    """Information about the script used in text"""
    script_type: str
    latin_ratio: float
    cyrillic_ratio: float
    chinese_ratio: float
    korean_ratio: float
    japanese_ratio: float
    cjk_ratio: float
    arabic_ratio: float

@dataclass
class CharStats:
    """Character statistics for text analysis"""
    alpha_ratio: float
    digit_ratio: float
    punct_ratio: float
    space_ratio: float

class LanguagePatterns:
    """Language-specific patterns and indicators"""
    
    ENGLISH_STARTERS = {
        "who", "what", "when", "where", "why", "how", "which",
        "can", "could", "will", "would", "should", "shall", "may", "might", "must",
        "do", "does", "did", "don't", "doesn't", "didn't", "won't", "wouldn't", 
        "shouldn't", "can't", "couldn't", "isn't", "aren't", "wasn't", "weren't",
        "have", "has", "had", "haven't", "hasn't", "hadn't"
    }
    
    ENGLISH_PHRASES = {
        "can you", "could you", "will you", "would you", "do you", "did you",
        "are you", "is it", "was it", "were you", "have you", "has it"
    }
    
    FRENCH_INDICATORS = ["c'est", "qu'est", "qu'il", "qu'elle", "n'est", "n'a", "j'ai", "j'aime", "ça", "où"]
    
    LANGUAGE_ACCENTS = {
        'fr': ['é', 'è', 'ê', 'à', 'ù', 'ç', 'ô', 'î', 'ï', 'û'],
        'es': ['á', 'é', 'í', 'ó', 'ú', 'ñ', 'ü'],
        'de': ['ä', 'ö', 'ü', 'ß'],
        'it': ['à', 'è', 'é', 'ì', 'ò', 'ù']
    }
    
    MONGOLIAN_INDICATORS = [
        'бэр', 'гийн', 'хэд', 'хураамж', 'зогсоол', 'зөв', 'шөөрл', 'олон',
        'байх', 'болох', 'хийх', 'ийн', 'лын', 'ын', 'гэх', 'юу', 'энэ',
        'тэр', 'настай', 'вэ', 'би', 'монгол', 'хүн', 'байна', 'яаж',
        'нийслэл', 'хаана', 'байдаг'
    ]
    
    MONGOLIAN_PATTERNS = [
        'ийн', 'гийн', 'лын', 'хэд', 'өө', 'үү', 'эр', 'өр', 'энэ',
        'юу', ' вэ', 'хүн', 'яаж', 'байна', 'байдаг'
    ]

class DetectorLoader:
    """Handles loading and configuring language detection libraries"""
    
    @staticmethod
    def load_detectors(verbose: bool = False) -> Dict[str, Dict[str, Any]]:
        """Load available language detection libraries"""
        detectors = {}
        
        # Load langdetect
        try:
            from langdetect import detect_langs, DetectorFactory
            from langdetect.lang_detect_exception import LangDetectException
            
            DetectorFactory.seed = 0
            
            def langdetect_with_confidence(text):
                try:
                    results = detect_langs(text)
                    if results:
                        return results[0].lang, results[0].prob
                    return None, 0.0
                except:
                    return None, 0.0
            
            detectors['langdetect'] = {
                'detect': langdetect_with_confidence,
                'exception': LangDetectException,
                'weight': 1.0
            }
            
            if verbose:
                logger.info("Loaded langdetect for language detection")
        except ImportError:
            logger.warning("langdetect not available - this is the primary detector")
        
        # Load langid
        try:
            import langid
            
            detectors['langid'] = {
                'detect': lambda text: langid.classify(text),
                'exception': Exception,
                'weight': 1.2
            }
            
            if verbose:
                logger.info("Loaded langid for language detection")
        except ImportError:
            if verbose:
                logger.debug("langid not available for language detection")
        
        # Load pycld2
        try:
            import pycld2
            
            def pycld2_detect(text):
                try:
                    isReliable, textBytesFound, details = pycld2.detect(text)
                    if isReliable and details:
                        confidence = min(1.0, textBytesFound / len(text))
                        return details[0][1], confidence
                    return None, 0.0
                except:
                    return None, 0.0
            
            detectors['pycld2'] = {
                'detect': pycld2_detect,
                'exception': Exception,
                'weight': 1.5
            }
            
            if verbose:
                logger.info("Loaded pycld2 for language detection")
        except ImportError:
            if verbose:
                logger.debug("pycld2 not available for language detection")
        
        return detectors

class TextAnalyzer:
    """Handles text analysis operations"""
    
    @staticmethod
    def calculate_char_stats(text: str) -> CharStats:
        """Calculate character statistics for a text"""
        if not text:
            return CharStats(0, 0, 0, 0)
        
        total_len = len(text)
        return CharStats(
            alpha_ratio=sum(c.isalpha() for c in text) / total_len,
            digit_ratio=sum(c.isdigit() for c in text) / total_len,
            punct_ratio=sum(c in string.punctuation for c in text) / total_len,
            space_ratio=sum(c.isspace() for c in text) / total_len
        )
    
    @staticmethod
    def analyze_script(text: str) -> ScriptInfo:
        """Analyze the script used in the text"""
        if not text:
            return ScriptInfo("Unknown", 0, 0, 0, 0, 0, 0, 0)
        
        char_counts = defaultdict(int)
        total_chars = 0
        
        for char in text:
            if not char.isalpha():
                continue
            
            total_chars += 1
            category = unicodedata.name(char, "UNKNOWN").split()[0]
            
            if category in ("LATIN", "BASIC", "ASCII"):
                char_counts['latin'] += 1
            elif category == "CYRILLIC":
                char_counts['cyrillic'] += 1
            elif '\uAC00' <= char <= '\uD7A3':  # Korean Hangul
                char_counts['korean'] += 1
            elif '\u3040' <= char <= '\u309F' or '\u30A0' <= char <= '\u30FF':  # Japanese
                char_counts['japanese'] += 1
            elif category == "CJK":
                char_counts['chinese'] += 1
            elif category in ("HIRAGANA", "KATAKANA"):
                char_counts['japanese'] += 1
            elif category == "HANGUL":
                char_counts['korean'] += 1
            elif category == "ARABIC":
                char_counts['arabic'] += 1
        
        if total_chars == 0:
            return ScriptInfo("Unknown", 0, 0, 0, 0, 0, 0, 0)
        
        # Calculate ratios
        ratios = {k: v / total_chars for k, v in char_counts.items()}
        
        # Determine primary script
        max_ratio = max(ratios.values()) if ratios else 0
        script_type = "Unknown"
        
        if max_ratio > 0.5:
            script_map = {
                'latin': "Latin", 'cyrillic': "Cyrillic", 'chinese': "Chinese",
                'korean': "Korean", 'japanese': "Japanese", 'arabic': "Arabic"
            }
            for script, name in script_map.items():
                if ratios.get(script, 0) == max_ratio:
                    script_type = name
                    break
        
        cjk_ratio = ratios.get('chinese', 0) + ratios.get('korean', 0) + ratios.get('japanese', 0)
        
        return ScriptInfo(
            script_type=script_type,
            latin_ratio=ratios.get('latin', 0),
            cyrillic_ratio=ratios.get('cyrillic', 0),
            chinese_ratio=ratios.get('chinese', 0),
            korean_ratio=ratios.get('korean', 0),
            japanese_ratio=ratios.get('japanese', 0),
            cjk_ratio=cjk_ratio,
            arabic_ratio=ratios.get('arabic', 0)
        )
    
    @staticmethod
    def generate_text_variations(text: str) -> List[str]:
        """Generate variations of the input text to improve detection reliability"""
        variations = [text]
        
        # Remove punctuation
        text_no_punct = re.sub(r'[^\w\s]', '', text)
        if text_no_punct != text:
            variations.append(text_no_punct)
        
        text_len = len(text)
        
        if text_len < 20:
            # Check if it's obvious English
            words = text.lower().split()
            english_words = {"can", "you", "the", "a", "an", "is", "are", "was", "were", 
                           "do", "does", "did", "have", "has", "had", "will", "would", 
                           "could", "should", "plot", "it"}
            if not any(word in english_words for word in words):
                variations.append(text + " " + text)
        elif text_len < 60:
            variations.append(text + " " + text)
            if any(c in text for c in '{}[]()<>'):
                variations.append(text + " " + text)
            else:
                variations.append(text + ". " + text)
        elif text_len < 120:
            if any(c in text for c in '{}[]()<>'):
                variations.append("Code example: " + text)
            elif text.endswith(('.', '?', '!')):
                variations.append("Note: " + text)
        
        if text_len < 10:
            variations.append(text.lower())
        
        return variations

class LanguageDetector:
    """
    Robust language detection class suitable for multilingual applications.
    
    Handles short texts, technical content, and product descriptions with improved 
    accuracy. Configurable to use multiple detection libraries when available.
    """
    
    def __init__(self, verbose: bool = False, min_confidence: float = 0.7):
        """Initialize the language detector"""
        self.verbose = verbose
        self.min_confidence = min_confidence
        self.detectors = DetectorLoader.load_detectors(verbose)
        self.analyzer = TextAnalyzer()
        self.patterns = LanguagePatterns()
        
        if len(self.detectors) == 0:
            logger.error("No language detectors available! Defaulting to English for all text.")
        else:
            logger.info(f"Using {len(self.detectors)} language detectors: {', '.join(self.detectors.keys())}")
    
    def detect(self, text: str) -> str:
        """Detect the language of the input text"""
        try:
            text = text.strip()
            
            # Quick checks for very short or empty text
            if not text or len(text) < 5:
                if self.verbose:
                    logger.debug(f"Text too short for detection: '{text}', defaulting to English")
                return "en"
            
            # Quick English detection
            if self._is_likely_english(text):
                return "en"
            
            # Analyze text characteristics
            stats = self.analyzer.calculate_char_stats(text)
            script_info = self.analyzer.analyze_script(text)
            
            # Handle mostly non-alphabetic text
            if stats.alpha_ratio < 0.5 and stats.digit_ratio + stats.punct_ratio > 0.4:
                if self.verbose:
                    logger.debug("Text contains mostly non-alphabetic characters, defaulting to English")
                return "en"
            
            # Handle CJK languages
            cjk_result = self._handle_cjk_languages(script_info)
            if cjk_result:
                return cjk_result
            
            # Handle short Latin text
            if self._is_short_latin_text(text, script_info):
                return self._detect_short_latin_text(text, script_info)
            
            # Perform ensemble detection
            result = self._ensemble_detect(text, script_info, stats)
            
            # Handle Cyrillic text that might be Mongolian
            if result in ['ru', 'bg', 'mk', 'sr'] and script_info.script_type == 'Cyrillic':
                if self._is_mongolian_cyrillic(text):
                    if self.verbose:
                        logger.info(f"Cyrillic text detected as Mongolian (was {result})")
                    return 'mn'
            
            return result
            
        except Exception as e:
            logger.warning(f"Language detection failed: {str(e)}")
            return "en"
    
    def _is_likely_english(self, text: str) -> bool:
        """Quick check for likely English text"""
        words = text.split()
        if not words:
            return False
        
        # Only apply English detection to Latin script text
        script_info = self.analyzer.analyze_script(text)
        if script_info.script_type != 'Latin':
            return False
        
        first_word = words[0].lower()
        
        # Check for English question words
        if first_word in {"who", "what", "when", "where", "why", "how", "which"}:
            if self.verbose:
                logger.debug(f"Detected English wh-question: '{first_word}'")
            return True
        
        # Check for English starters (only for obvious cases)
        obvious_english_starters = {
            "can", "could", "will", "would", "should", "shall", "may", "might", "must",
            "don't", "doesn't", "didn't", "won't", "wouldn't", 
            "shouldn't", "can't", "couldn't", "isn't", "aren't", "wasn't", "weren't",
            "haven't", "hasn't", "hadn't"
        }
        if first_word in obvious_english_starters:
            if self.verbose:
                logger.debug(f"Detected English starter word: '{first_word}'")
            return True
        
        # Check for English phrases
        if len(words) >= 2:
            two_word_start = f"{words[0].lower()} {words[1].lower()}"
            if two_word_start in self.patterns.ENGLISH_PHRASES:
                if self.verbose:
                    logger.debug(f"Detected English phrase: '{two_word_start}'")
                return True
        
        return False
    
    def _handle_cjk_languages(self, script_info: ScriptInfo) -> Optional[str]:
        """Handle CJK language detection"""
        if script_info.script_type == 'Chinese':
            return 'zh'
        elif script_info.script_type == 'Korean':
            return 'ko'
        elif script_info.script_type == 'Japanese':
            return 'ja'
        return None
    
    def _is_short_latin_text(self, text: str, script_info: ScriptInfo) -> bool:
        """Check if text is short Latin text needing special handling"""
        return (len(text.split()) == 1 and 
                len(text) < 15 and 
                text[0].isupper() and
                script_info.script_type == 'Latin' and 
                script_info.latin_ratio > 0.8)
    
    def _detect_short_latin_text(self, text: str, script_info: ScriptInfo) -> str:
        """Specialized detection for short Latin-script texts"""
        language_votes = defaultdict(int)
        
        # Try all detectors
        for detector_name, detector in self.detectors.items():
            try:
                lang, confidence = detector['detect'](text)
                if lang:
                    language_votes[lang] += 1
            except:
                continue
        
        # Apply character analysis
        latin_result = self._analyze_latin_characters(text)
        if latin_result:
            language_votes[latin_result] += 2
        
        # Bias toward English for capitalized product names
        if text.istitle() and len(text.split()) == 1:
            language_votes["en"] += 1
        
        # Check for language-specific accents
        for lang, chars in self.patterns.LANGUAGE_ACCENTS.items():
            if any(c in text for c in chars):
                language_votes[lang] += 2
        
        if language_votes:
            return max(language_votes.items(), key=lambda x: x[1])[0]
        
        return "en"
    
    def _ensemble_detect(self, text: str, script_info: ScriptInfo, stats: CharStats) -> str:
        """Perform ensemble detection using multiple detectors"""
        variations = self.analyzer.generate_text_variations(text)
        language_votes = defaultdict(float)
        detection_details = defaultdict(list)
        
        # No detectors available
        if not self.detectors:
            return "en"
        
        # Run detection with each detector
        for detector_name, detector in self.detectors.items():
            self._run_detector(detector_name, detector, text, variations, 
                             language_votes, detection_details)
        
        # Handle no votes
        if not language_votes:
            return self._fallback_detect(text)
        
        # Calculate result
        sorted_votes = sorted(language_votes.items(), key=lambda x: x[1], reverse=True)
        most_likely_lang = sorted_votes[0][0]
        confidence = self._calculate_confidence(language_votes, most_likely_lang)
        
        if self.verbose:
            self._log_detection_details(sorted_votes, confidence, detection_details)
        
        # Handle low confidence
        if confidence < self.min_confidence:
            return self._handle_low_confidence(text, most_likely_lang, language_votes, 
                                             script_info, confidence)
        
        # Special handling for short texts
        if len(text) < 20:
            return self._handle_short_text_special_cases(text, most_likely_lang, language_votes)
        
        return most_likely_lang
    
    def _run_detector(self, detector_name: str, detector: Dict[str, Any], 
                     text: str, variations: List[str],
                     language_votes: Dict[str, float], 
                     detection_details: Dict[str, List[str]]) -> None:
        """Run a single detector on text and variations"""
        detect_func = detector['detect']
        exception_type = detector.get('exception', Exception)
        detector_weight = detector.get('weight', 1.0)
        
        try:
            if detector_name == 'langdetect':
                # Try variations for langdetect
                for variant in variations:
                    try:
                        lang, confidence = detect_func(variant)
                        if lang:
                            weighted_vote = detector_weight * confidence
                            language_votes[lang] += weighted_vote
                            detection_details[lang].append(
                                f"{detector_name}:{confidence:.2f}:'{variant}'"
                            )
                    except exception_type:
                        continue
            else:
                # Other detectors use original text only
                lang, confidence = detect_func(text)
                if lang:
                    weighted_vote = detector_weight * confidence
                    if weighted_vote < 0:
                        weighted_vote = max(weighted_vote, -2.0)
                    language_votes[lang] += weighted_vote
                    detection_details[lang].append(
                        f"{detector_name}:{confidence:.2f}:original"
                    )
        except Exception as e:
            if self.verbose:
                logger.debug(f"Error with {detector_name}: {str(e)}")
    
    def _fallback_detect(self, text: str) -> str:
        """Fallback detection when no votes"""
        if 'langdetect' in self.detectors:
            try:
                lang, _ = self.detectors['langdetect']['detect'](text)
                return lang if lang else "en"
            except:
                pass
        return "en"
    
    def _calculate_confidence(self, language_votes: Dict[str, float], 
                            most_likely_lang: str) -> float:
        """Calculate confidence score"""
        total_positive_votes = sum(max(0, vote) for vote in language_votes.values())
        if total_positive_votes > 0:
            return max(0, language_votes[most_likely_lang]) / total_positive_votes
        return 0.0
    
    def _log_detection_details(self, sorted_votes: List[Tuple[str, float]], 
                             confidence: float, 
                             detection_details: Dict[str, List[str]]) -> None:
        """Log detailed detection information"""
        vote_info = ", ".join([f"{lang}: {votes:.2f}" for lang, votes in sorted_votes])
        logger.debug(f"Language votes: {vote_info}, confidence: {confidence:.2f}")
        
        for lang, details in detection_details.items():
            detail_str = ", ".join(details)
            logger.debug(f"Detection details for {lang}: {detail_str}")
    
    def _handle_low_confidence(self, text: str, most_likely_lang: str,
                             language_votes: Dict[str, float],
                             script_info: ScriptInfo, confidence: float) -> str:
        """Handle low confidence detection results"""
        # Check for French indicators
        has_french = any(indicator in text.lower() for indicator in self.patterns.FRENCH_INDICATORS)
        
        # Only default to English for Latin script text
        if (len(text) < 30 and not has_french and 
            script_info.script_type == 'Latin'):
            has_accents = any(c in text for c in 'àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ')
            if not has_accents:
                if self.verbose:
                    logger.debug(f"Short Latin text with low confidence and no accents, defaulting to English")
                return 'en'
        
        if has_french and 'fr' in language_votes:
            if self.verbose:
                logger.debug(f"Low confidence but found French indicators, using French")
            return 'fr'
        
        # Try character analysis for Latin text
        if len(text) < 20 and confidence < 0.7 and script_info.script_type == 'Latin':
            latin_result = self._analyze_latin_characters(text)
            if latin_result and latin_result in language_votes:
                if self.verbose:
                    logger.debug(f"Using Latin character analysis, detected: {latin_result}")
                return latin_result
        
        # For non-Latin scripts or when we have a reasonable detection, trust it
        if most_likely_lang and most_likely_lang != 'en':
            if self.verbose:
                logger.debug(f"Low confidence but non-Latin script or reasonable detection, using: {most_likely_lang}")
            return most_likely_lang
        
        # Final fallback: prefer English only if we have votes for it
        if 'en' in language_votes:
            if self.verbose:
                logger.debug(f"Low confidence detection, defaulting to English")
            return 'en'
            
        return most_likely_lang
    
    def _handle_short_text_special_cases(self, text: str, most_likely_lang: str,
                                       language_votes: Dict[str, float]) -> str:
        """Handle special cases for short texts"""
        # Check for product listings and prices
        if (re.search(r'\$|\€|\£|\¥', text) or 
            re.search(r'\d+\s*(oz|lb|g|kg|ml|L)', text)):
            if 'en' in language_votes:
                if self.verbose:
                    logger.debug("Detected product listing or price, preferring English")
                return 'en'
        
        return most_likely_lang
    
    def _analyze_latin_characters(self, text: str) -> Optional[str]:
        """Use character frequency analysis to distinguish between Latin-script languages"""
        text = ''.join(c.lower() for c in text if c.isalpha())
        if not text:
            return None
        
        # Count character frequencies
        char_counts = defaultdict(int)
        for char in text:
            char_counts[char] += 1
        
        total_chars = len(text)
        char_freqs = {char: count / total_chars * 100 for char, count in char_counts.items()}
        
        # Language characteristic patterns
        patterns = {
            'en': {'e', 't', 'a', 'o', 'i', 'n', 's'},
            'fr': {'e', 'a', 's', 'i', 'é', 'è', 'à', 'ù', 'ç'},
            'es': {'e', 'a', 'o', 's', 'n', 'r', 'ñ', 'á', 'é', 'í', 'ó', 'ú'},
            'de': {'e', 'n', 'i', 's', 'r', 'a', 'ä', 'ö', 'ü', 'ß'}
        }
        
        scores = {}
        for lang, chars in patterns.items():
            scores[lang] = sum(char_freqs.get(c, 0) for c in chars)
        
        # Apply biases
        if len(text) < 10 and not any(ord(c) > 127 for c in text):
            return "en"
        
        if len(text) < 10 and text[0].isupper():
            scores["en"] *= 1.1
        
        if all(ord(c) < 128 for c in text) and len(text) < 15:
            scores["en"] *= 1.05
        
        return max(scores, key=scores.get) if scores else None
    
    def _is_mongolian_cyrillic(self, text: str) -> bool:
        """Detect if Cyrillic text is likely Mongolian rather than Russian"""
        text_lower = text.lower()
        
        # Count indicators
        indicator_count = sum(1 for indicator in self.patterns.MONGOLIAN_INDICATORS 
                            if indicator in text_lower)
        pattern_count = sum(1 for pattern in self.patterns.MONGOLIAN_PATTERNS 
                          if pattern in text_lower)
        
        # Count Mongolian-specific letters
        mongolian_letters_count = text_lower.count('ө') + text_lower.count('ү')
        
        # Decision logic
        if indicator_count >= 2 or pattern_count >= 2:
            return True
        
        if mongolian_letters_count >= 2 and (indicator_count >= 1 or pattern_count >= 1):
            return True
        
        # For short text, check strong indicators
        if len(text) < 50:
            strong_indicators = ['хэд', 'зөв', 'ийн', 'гийн', 'хураамж', 'энэ', 
                               'юу', 'вэ', 'монгол', 'хүн', 'яаж', 'байна']
            if any(indicator in text_lower for indicator in strong_indicators):
                return True
            
            if text_lower.endswith(' вэ?') or text_lower.endswith(' вэ'):
                return True
        
        return False