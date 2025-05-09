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

# Initialize logger
logger = logging.getLogger(__name__)

class LanguageDetector:
    """
    Robust language detection class suitable for multilingual applications.
    
    Handles short texts, technical content, and product descriptions with improved 
    accuracy. Configurable to use multiple detection libraries when available.
    """
    
    def __init__(self, verbose: bool = False, min_confidence: float = 0.7):
        """
        Initialize the language detector.
        
        Args:
            verbose: Whether to log detailed information about detections
            min_confidence: Minimum confidence threshold for language detection
        """
        self.verbose = verbose
        self.min_confidence = min_confidence
        self.detectors = {}
        
        # Try to load langdetect (primary detector)
        try:
            from langdetect import detect as langdetect_detect
            from langdetect import DetectorFactory
            from langdetect.lang_detect_exception import LangDetectException
            
            # Make langdetect results deterministic
            DetectorFactory.seed = 0
            
            def langdetect_with_confidence(text):
                try:
                    from langdetect import detect_langs
                    results = detect_langs(text)
                    if results:
                        return results[0].lang, results[0].prob
                    return None, 0.0
                except:
                    return None, 0.0
            
            self.detectors['langdetect'] = {
                'detect': langdetect_with_confidence,
                'exception': LangDetectException,
                'weight': 1.0  # Base weight
            }
            
            if self.verbose:
                logger.info("Loaded langdetect for language detection")
                
        except ImportError:
            logger.warning("langdetect not available - this is the primary detector")
        
        # Try to import langid if available
        try:
            import langid
            
            def langid_detect(text):
                lang, score = langid.classify(text)
                return lang, score
                
            self.detectors['langid'] = {
                'detect': langid_detect,
                'exception': Exception,
                'weight': 1.2  # Slightly higher weight for technical text
            }
            
            if self.verbose:
                logger.info("Loaded langid for language detection")
                
        except ImportError:
            if self.verbose:
                logger.debug("langid not available for language detection")
        
        # Try to import pycld2 if available
        try:
            import pycld2
            
            def pycld2_detect(text):
                try:
                    isReliable, textBytesFound, details = pycld2.detect(text)
                    if isReliable and details:
                        # Calculate confidence based on reliability and bytes found
                        confidence = min(1.0, textBytesFound / len(text))
                        return details[0][1], confidence
                    return None, 0.0
                except:
                    return None, 0.0
                
            self.detectors['pycld2'] = {
                'detect': pycld2_detect,
                'exception': Exception,
                'weight': 1.5  # Higher weight for technical content
            }
            
            if self.verbose:
                logger.info("Loaded pycld2 for language detection")
                
        except ImportError:
            if self.verbose:
                logger.debug("pycld2 not available for language detection")
        
        # Count how many detectors we have
        if len(self.detectors) == 0:
            logger.error("No language detectors available! Defaulting to English for all text.")
        else:
            logger.info(f"Using {len(self.detectors)} language detectors: {', '.join(self.detectors.keys())}")
    
    def detect(self, text: str) -> str:
        """
        Detect the language of the input text.
        
        Args:
            text: The text to detect the language of
            
        Returns:
            ISO 639-1 language code (e.g., 'en' for English, 'fr' for French)
            Defaults to 'en' if detection fails or confidence is low
        """
        try:
            # Clean the text - remove excess whitespace but preserve content
            text = text.strip()
            
            # For very short texts (fewer than 5 characters), default to 'en'
            if not text or len(text) < 5:
                if self.verbose:
                    logger.debug(f"Text too short for detection: '{text}', defaulting to English")
                return "en"
            
            # Quick check for English wh-words at the start
            words = text.split()
            if words and words[0].lower() in {"who", "what", "when", "where", "why", "how", "which"}:
                if self.verbose:
                    logger.debug(f"Detected English wh-question: '{words[0]}', returning English")
                return "en"
            
            # Calculate character statistics
            stats = self._calculate_char_stats(text)
            script_info = self._analyze_script(text)
            
            # If text contains mostly numeric and symbols, default to English
            if stats['alpha_ratio'] < 0.5 and stats['digit_ratio'] + stats['punct_ratio'] > 0.4:
                if self.verbose:
                    logger.debug(f"Text contains mostly non-alphabetic characters, defaulting to English")
                return "en"
            
            # For short product names (single words with capitalization)
            if len(text.split()) == 1 and len(text) < 15 and text[0].isupper():
                # This is likely a product name or proper noun
                # Check if it uses primarily Latin script (common for English and romance languages)
                if script_info['script_type'] == 'Latin' and script_info['latin_ratio'] > 0.8:
                    # For single Latin-script words, try to get a robust detection
                    return self._robust_detect_short_latin_text(text)
            
            # Generate text variations for more robust detection
            variations = self._generate_text_variations(text)
            
            # If we have no detectors available, default to English
            if not self.detectors:
                return "en"
                
            # Run ensemble detection with voting
            language_votes = {}
            detection_details = {}
            
            # Test with each available detector
            for detector_name, detector in self.detectors.items():
                detect_func = detector['detect']
                exception_type = detector.get('exception', Exception)
                detector_weight = detector.get('weight', 1.0)
                
                try:
                    # For langdetect, try all variations for robust results
                    if detector_name == 'langdetect':
                        for variant in variations:
                            try:
                                lang, confidence = detect_func(variant)
                                if lang:
                                    # Apply detector weight and confidence
                                    weighted_vote = detector_weight * confidence
                                    language_votes[lang] = language_votes.get(lang, 0) + weighted_vote
                                    
                                    # Store details for debugging
                                    if lang not in detection_details:
                                        detection_details[lang] = []
                                    detection_details[lang].append(f"{detector_name}:{confidence:.2f}:'{variant}'")
                                
                            except exception_type:
                                continue
                    # For other detectors, just use the original text
                    else:
                        lang, confidence = detect_func(text)
                        if lang:
                            # Apply detector weight and confidence
                            weighted_vote = detector_weight * confidence
                            language_votes[lang] = language_votes.get(lang, 0) + weighted_vote
                            
                            # Store details for debugging
                            if lang not in detection_details:
                                detection_details[lang] = []
                            detection_details[lang].append(f"{detector_name}:{confidence:.2f}:original")
                            
                except Exception as e:
                    if self.verbose:
                        logger.debug(f"Error with {detector_name}: {str(e)}")
                    continue
            
            # If no votes, fallback to original method with langdetect
            if not language_votes and 'langdetect' in self.detectors:
                try:
                    lang, confidence = self.detectors['langdetect']['detect'](text)
                    return lang if lang else "en"
                except:
                    return "en"
            elif not language_votes:
                return "en"
                
            # Find the language with the most votes
            sorted_votes = sorted(language_votes.items(), key=lambda x: x[1], reverse=True)
            most_likely_lang = sorted_votes[0][0]
            
            # Calculate confidence
            total_votes = sum(language_votes.values())
            confidence = language_votes[most_likely_lang] / total_votes
            
            # Log detailed information if verbose
            if self.verbose:
                vote_info = ", ".join([f"{lang}: {votes:.2f}" for lang, votes in sorted_votes])
                logger.debug(f"Language votes: {vote_info}, confidence: {confidence:.2f}")
                
                for lang, details in detection_details.items():
                    detail_str = ", ".join(details)
                    logger.debug(f"Detection details for {lang}: {detail_str}")
            
            # For short texts with low confidence, try a structural approach
            if len(text) < 20 and confidence < 0.7:
                # Script analysis can provide better clues for short texts
                if script_info['script_type'] == 'Latin':
                    # For Latin script short texts with low confidence, check character frequencies
                    latin_result = self._analyze_latin_characters(text)
                    if latin_result and latin_result in language_votes:
                        if self.verbose:
                            logger.debug(f"Using Latin character analysis for short text, detected: {latin_result}")
                        return latin_result
            
            # If confidence is below threshold and English is a possibility, use English
            if confidence < self.min_confidence and 'en' in language_votes:
                if self.verbose:
                    logger.debug(f"Low confidence detection ({confidence:.2f}), defaulting to English")
                return 'en'
            
            # Special case for short texts that might be confused between similar languages
            if len(text) < 20:
                # For product listings and prices, prefer English detection
                if (re.search(r'\$|\€|\£|\¥', text) or 
                    re.search(r'\d+\s*(oz|lb|g|kg|ml|L)', text)):
                    if 'en' in language_votes:
                        if self.verbose:
                            logger.debug(f"Detected product listing or price, preferring English")
                        return 'en'
            
            return most_likely_lang
            
        except Exception as e:
            logger.warning(f"Language detection failed completely: {str(e)}")
            return "en"
    
    def _analyze_script(self, text: str) -> Dict[str, Any]:
        """
        Analyze the script used in the text.
        
        This helps identify the general writing system (Latin, Cyrillic, etc.)
        which can provide clues about possible languages.
        """
        if not text:
            return {"script_type": "Unknown", "latin_ratio": 0, "cyrillic_ratio": 0, "cjk_ratio": 0, "arabic_ratio": 0}
        
        total_chars = 0
        latin_chars = 0
        cyrillic_chars = 0
        cjk_chars = 0
        arabic_chars = 0
        
        for char in text:
            if not char.isalpha():
                continue
                
            total_chars += 1
            category = unicodedata.name(char, "UNKNOWN").split()[0]
            
            if category in ("LATIN", "BASIC", "ASCII"):
                latin_chars += 1
            elif category == "CYRILLIC":
                cyrillic_chars += 1
            elif category in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL"):
                cjk_chars += 1
            elif category == "ARABIC":
                arabic_chars += 1
        
        # Determine primary script
        script_type = "Unknown"
        if total_chars > 0:
            latin_ratio = latin_chars / total_chars
            cyrillic_ratio = cyrillic_chars / total_chars
            cjk_ratio = cjk_chars / total_chars
            arabic_ratio = arabic_chars / total_chars
            
            max_ratio = max(latin_ratio, cyrillic_ratio, cjk_ratio, arabic_ratio)
            
            if max_ratio > 0.5:  # If more than 50% of chars are of one script type
                if latin_ratio == max_ratio:
                    script_type = "Latin"
                elif cyrillic_ratio == max_ratio:
                    script_type = "Cyrillic"
                elif cjk_ratio == max_ratio:
                    script_type = "CJK"
                elif arabic_ratio == max_ratio:
                    script_type = "Arabic"
        
        return {
            "script_type": script_type,
            "latin_ratio": latin_chars / total_chars if total_chars > 0 else 0,
            "cyrillic_ratio": cyrillic_chars / total_chars if total_chars > 0 else 0,
            "cjk_ratio": cjk_chars / total_chars if total_chars > 0 else 0,
            "arabic_ratio": arabic_chars / total_chars if total_chars > 0 else 0
        }
    
    def _analyze_latin_characters(self, text: str) -> Optional[str]:
        """
        Use character frequency analysis to distinguish between Latin-script languages.
        
        This is especially useful for short texts where statistical methods struggle.
        Based on character frequency patterns specific to different languages.
        """
        # Only count alphabetic characters
        text = ''.join(c.lower() for c in text if c.isalpha())
        if not text:
            return None
            
        # Count character frequencies
        char_counts = {}
        for char in text:
            char_counts[char] = char_counts.get(char, 0) + 1
            
        total_chars = len(text)
        
        # Calculate frequency percentages
        char_freqs = {char: count / total_chars * 100 for char, count in char_counts.items()}
        
        # Check for characteristic patterns in different languages
        
        # English: high frequency of 'e', 't', 'a' and relatively low 'é', 'à', 'ñ', etc.
        english_chars = {'e', 't', 'a', 'o', 'i', 'n', 's'}
        english_score = sum(char_freqs.get(c, 0) for c in english_chars)
        
        # French: high frequency of 'e', 'a', 's', 'i' and accented chars like 'é', 'è', 'à'
        french_chars = {'e', 'a', 's', 'i', 'é', 'è', 'à', 'ù', 'ç'}
        french_score = sum(char_freqs.get(c, 0) for c in french_chars)
        
        # Spanish: high frequency of 'e', 'a', 'o' and 'ñ', accented vowels
        spanish_chars = {'e', 'a', 'o', 's', 'n', 'r', 'ñ', 'á', 'é', 'í', 'ó', 'ú'}
        spanish_score = sum(char_freqs.get(c, 0) for c in spanish_chars)
        
        # German: high frequency of 'e', 'n', 'i', 's' and umlauts
        german_chars = {'e', 'n', 'i', 's', 'r', 'a', 'ä', 'ö', 'ü', 'ß'}
        german_score = sum(char_freqs.get(c, 0) for c in german_chars)
        
        # For very short texts, if no special characters, default to English
        if len(text) < 10 and not any(c for c in text if ord(c) > 127):
            return "en"
        
        # Find language with highest score
        scores = {
            "en": english_score,
            "fr": french_score, 
            "es": spanish_score,
            "de": german_score
        }
        
        # Apply bias for common language detection issues:
        # Bias slightly toward English for short product names
        if len(text) < 10 and text[0].isupper():
            scores["en"] *= 1.1
        
        # If the text contains only ASCII characters and is short, favor English
        if all(ord(c) < 128 for c in text) and len(text) < 15:
            scores["en"] *= 1.05
        
        return max(scores, key=scores.get)
    
    def _robust_detect_short_latin_text(self, text: str) -> str:
        """
        Specialized detection for short Latin-script texts.
        
        This combines multiple approaches for better accuracy with product names,
        single words, and other short texts.
        """
        # For single words that look like product names, try multiple approaches
        
        # 1. First, try standard detection with all detectors
        language_votes = {}
        
        for detector_name, detector in self.detectors.items():
            try:
                lang, confidence = detector['detect'](text)
                language_votes[lang] = language_votes.get(lang, 0) + 1
            except:
                continue
        
        # 2. Apply character analysis
        latin_result = self._analyze_latin_characters(text)
        if latin_result:
            language_votes[latin_result] = language_votes.get(latin_result, 0) + 2  # Give extra weight
        
        # 3. For single capitalized words like product names, bias slightly toward English
        if text.istitle() and len(text.split()) == 1:
            language_votes["en"] = language_votes.get("en", 0) + 1
        
        # 4. Check for language-specific characters
        accents = {
            'fr': ['é', 'è', 'ê', 'à', 'ù', 'ç', 'ô', 'î', 'ï', 'û'],
            'es': ['á', 'é', 'í', 'ó', 'ú', 'ñ', 'ü'],
            'de': ['ä', 'ö', 'ü', 'ß'],
            'it': ['à', 'è', 'é', 'ì', 'ò', 'ù']
        }
        
        for lang, chars in accents.items():
            if any(c in text for c in chars):
                language_votes[lang] = language_votes.get(lang, 0) + 2
        
        # Get the language with the most votes
        if language_votes:
            most_likely = max(language_votes.items(), key=lambda x: x[1])[0]
            return most_likely
        
        # Fallback to English for Latin-script text with no clear signal
        return "en"
    
    def _calculate_char_stats(self, text: str) -> Dict[str, float]:
        """Calculate character statistics for a text"""
        if not text:
            return {"alpha_ratio": 0, "digit_ratio": 0, "punct_ratio": 0, "space_ratio": 0}
        
        total_len = len(text)
        alpha_count = sum(c.isalpha() for c in text)
        digit_count = sum(c.isdigit() for c in text)
        punct_count = sum(c in string.punctuation for c in text)
        space_count = sum(c.isspace() for c in text)
        
        return {
            "alpha_ratio": alpha_count / total_len,
            "digit_ratio": digit_count / total_len,
            "punct_ratio": punct_count / total_len,
            "space_ratio": space_count / total_len
        }
    
    def _generate_text_variations(self, text: str) -> List[str]:
        """
        Generate variations of the input text to improve detection reliability.
        
        For short texts, language detection can be unreliable. By creating
        multiple variations and testing each one, we get more robust results.
        
        Strategy:
        - Very short texts (<20 chars): Duplicate the entire text
        - Short texts (20-60 chars): Duplicate with slight modifications
        - Medium texts (60-120 chars): Add context variations
        - Long texts (>120 chars): Use original only
        """
        variations = [text]  # Original text
        
        # Remove punctuation
        text_no_punct = re.sub(r'[^\w\s]', '', text)
        if text_no_punct != text:
            variations.append(text_no_punct)
        
        text_len = len(text)
        
        # For very short texts (<20 chars), duplicate as is
        if text_len < 20:
            variations.append(text + " " + text)
            
        # For short texts (20-60 chars), try different duplication strategies
        elif text_len < 60:
            # Simple duplication
            variations.append(text + " " + text)
            
            # Duplicate with slight modifications for technical content
            if any(c in text for c in '{}[]()<>'):
                # For code-like content, add a space between duplicates
                variations.append(text + " " + text)
            else:
                # For regular text, try with a period
                variations.append(text + ". " + text)
                
        # For medium texts (60-120 chars), try context variations
        elif text_len < 120:
            # For technical content, try adding common context
            if any(c in text for c in '{}[]()<>'):
                variations.append("Code example: " + text)
            # For documentation-like content
            elif text.endswith('.') or text.endswith('?') or text.endswith('!'):
                variations.append("Note: " + text)
        
        # Add capitalization variations for very short texts
        if text_len < 10:
            variations.append(text.lower())
            
        return variations