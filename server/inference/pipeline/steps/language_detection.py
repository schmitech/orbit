"""
Language Detection Step

This step detects the language of the user's message for better language matching.
"""

import logging
import re
import math
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
try:
    from langdetect import detect_langs, LangDetectException, DetectorFactory
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    # Provide dummies to avoid NameError if referenced
    detect_langs = None
    class LangDetectException(Exception):
        pass
    class DetectorFactory:
        seed = 0
from ..base import PipelineStep, ProcessingContext

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


@dataclass
class DetectionResult:
    """Result of language detection with confidence and metadata."""
    language: str
    confidence: float
    method: str
    raw_results: Dict[str, Any] = None


class LanguageDetectionStep(PipelineStep):
    """
    Detect the language of the user's message using multiple backends.
    
    This step uses an ensemble of detection libraries with weighted voting
    for improved accuracy and robustness.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only setup backends if language detection is enabled
        config = self.container.get_or_none('config') or {}
        lang_config = config.get('language_detection', {})
        if lang_config.get('enabled', False):
            self._setup_backends()
        else:
            self.backends = []
            self.min_confidence = 0.7
            self.fallback_language = 'en'
    
    def _setup_backends(self):
        """Initialize available backends with their weights."""
        config = self.container.get_or_none('config') or {}
        lang_config = config.get('language_detection', {})
        
        # Get configured backends or use defaults
        enabled_backends = lang_config.get('backends', ['langdetect', 'langid', 'pycld2'])
        
        self.backends = []
        backend_weights = lang_config.get('backend_weights', {
            'langdetect': 1.0,
            'langid': 1.2, 
            'pycld2': 1.5
        })
        
        # Only include langdetect if installed
        if 'langdetect' in enabled_backends and LANGDETECT_AVAILABLE:
            self.backends.append(('langdetect', backend_weights.get('langdetect', 1.0), self._detect_langdetect))
        
        # Optional backends
        if 'langid' in enabled_backends and LANGID_AVAILABLE:
            self.backends.append(('langid', backend_weights.get('langid', 1.2), self._detect_langid))
            
        if 'pycld2' in enabled_backends and PYCLD2_AVAILABLE:
            self.backends.append(('pycld2', backend_weights.get('pycld2', 1.5), self._detect_pycld2))
        
        # Store configuration
        self.min_confidence = lang_config.get('min_confidence', 0.7)
        # Minimum margin between top-2 to accept the winner
        self.min_margin = lang_config.get('min_margin', 0.2)
        # Prefer English for ASCII-only text when ambiguous
        self.prefer_english_for_ascii = lang_config.get('prefer_english_for_ascii', True)
        # Stickiness to avoid language flapping within a session
        self.enable_stickiness = lang_config.get('enable_stickiness', True)
        self.fallback_language = lang_config.get('fallback_language', 'en')
        
        self.logger.info(f"Initialized {len(self.backends)} language detection backends: {[b[0] for b in self.backends]}")
    
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.
        
        Returns:
            True if language detection is enabled and message exists
        """
        config = self.container.get_or_none('config') or {}
        language_detection_config = config.get('language_detection', {})
        
        # Only check the new config location
        enabled = language_detection_config.get('enabled', False)
        
        return enabled and bool(context.message) and not context.is_blocked
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process the context and detect the language.
        
        Args:
            context: The processing context
            
        Returns:
            The modified context with detected language
        """
        if context.is_blocked:
            return context
        
        self.logger.debug("Detecting language of user message")
        
        try:
            # Detect language using ensemble method
            result = self._detect_language_ensemble(context.message, previous_language=getattr(context, 'detected_language', None))
            context.detected_language = result.language
            
            # Store additional metadata for debugging
            if not hasattr(context, 'language_detection_meta'):
                context.language_detection_meta = {}
            context.language_detection_meta.update({
                'confidence': result.confidence,
                'method': result.method,
                'raw_results': result.raw_results
            })
            # Persist last detected language to help stabilize across turns
            context.metadata['last_detected_language'] = result.language
            
            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                self.logger.info(
                    f"DEBUG: Detected language: {result.language} "
                    f"(confidence: {result.confidence:.2f}, method: {result.method}) "
                    f"for message: {context.message[:50]}..."
                )
            
        except Exception as e:
            self.logger.error(f"Error during language detection: {str(e)}")
            # Use configured fallback language
            context.detected_language = self.fallback_language
            if not hasattr(context, 'language_detection_meta'):
                context.language_detection_meta = {}
            context.language_detection_meta.update({
                'confidence': 0.0,
                'method': 'fallback',
                'error': str(e)
            })
        
        return context
    
    def _detect_language_ensemble(self, text: str, previous_language: Optional[str] = None) -> DetectionResult:
        """
        Detect language using ensemble of multiple backends with confidence scoring.

        Args:
            text: The text to analyze
            previous_language: Previously detected language in this session (if any)

        Returns:
            DetectionResult with language, confidence, and metadata
        """
        if not text or len(text.strip()) < 3:
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

        # Run all available backends
        backend_results = []
        raw_results = {}
        
        for backend_name, weight, detector_func in self.backends:
            try:
                result = detector_func(clean_text)
                if result:
                    backend_results.append((result, weight, backend_name))
                    raw_results[backend_name] = result.__dict__ if hasattr(result, '__dict__') else str(result)
            except Exception as e:
                self.logger.warning(f"Backend {backend_name} failed: {str(e)}")
                raw_results[backend_name] = {'error': str(e)}

        if not backend_results:
            return DetectionResult(
                language=self.fallback_language,
                confidence=0.0,
                method='all_backends_failed',
                raw_results=raw_results
            )

        # Heuristic biasing for ASCII/Latin text to avoid Spanish-on-English mistakes
        ascii_ratio = self._ascii_ratio(clean_text)
        english_markers = self._count_markers(clean_text.lower(), [
            r'\bthe\b', r'\band\b', r'\bthis\b', r'\bthat\b', r'\bis\b', r'\bare\b',
            r'\bwhat\b', r'\bhow\b', r'\bwhy\b', r'\bwhere\b', r'\bcan\b', r'\bplease\b', r'\bthanks?\b'
        ])
        spanish_markers = self._count_markers(clean_text.lower(), [
            r'¿', r'¡', r'[áéíóúñ]', r'\bqué\b', r'\bcomo\b', r'\bcómo\b', r'\bestás?\b', r'\bgracias\b'
        ])

        # Strong safeguard: short, high-ASCII English-looking questions
        # This prevents false positives like classifying
        # "How do I export code?" as Portuguese.
        if self.prefer_english_for_ascii:
            lower = clean_text.lower()
            # Very high ASCII ratio and short prompt
            if ascii_ratio > 0.98 and len(clean_text) <= 120:
                # Starts with common English interrogatives/auxiliaries or contains please/thanks
                if re.search(r'^(how|what|why|where|when|who|can|could|should|would|is|are|does|do)\b', lower) \
                   or re.search(r'\b(please|thanks)\b', lower):
                    # No obvious non-English diacritics/markers
                    if spanish_markers == 0 and not re.search(r'[áéíóúñçãõàâêô]', lower):
                        return DetectionResult(
                            language='en',
                            confidence=0.9,
                            method='heuristic_ascii_bias',
                            raw_results={'reason': 'english_question_heuristic'}
                        )

        # Weighted voting
        language_votes = {}
        total_weight = 0
        
        for result, weight, backend_name in backend_results:
            lang = result.language if hasattr(result, 'language') else result
            conf = result.confidence if hasattr(result, 'confidence') else 0.8
            # Normalize confidence into [0, 1] to avoid negative/invalid values from some libraries (e.g., langid)
            if not isinstance(conf, (int, float)):
                conf = 0.8
            if conf < 0.0 or conf > 1.0:
                # Attempt to map arbitrary score to a probability using a logistic transform
                try:
                    conf = 1.0 / (1.0 + math.exp(-float(conf)))
                except Exception:
                    conf = 0.0 if conf < 0.0 else 1.0
            conf = max(0.0, min(1.0, conf))
            
            weighted_score = conf * weight
            if lang not in language_votes:
                language_votes[lang] = 0
            language_votes[lang] += weighted_score
            total_weight += weight

        # Apply heuristic nudges before finalizing the winner
        if self.prefer_english_for_ascii and ascii_ratio > 0.95 and english_markers > 0 and spanish_markers == 0:
            # Nudge English upwards and slightly down-weight Spanish in pure ASCII English-like text
            language_votes['en'] = language_votes.get('en', 0) + 0.2
            if 'es' in language_votes:
                language_votes['es'] = max(0, language_votes['es'] - 0.1)

        # Sort to get top candidates
        sorted_votes = sorted(language_votes.items(), key=lambda kv: kv[1], reverse=True)
        best_language, best_score = sorted_votes[0]
        second_score = sorted_votes[1][1] if len(sorted_votes) > 1 else 0.0
        best_confidence = (best_score / total_weight) if total_weight > 0 else 0.0
        # Clamp to [0, 1] for stability
        best_confidence = max(0.0, min(1.0, best_confidence))

        # If script detection had moderate confidence, boost it
        if script_result.confidence > 0.5 and script_result.language == best_language:
            best_confidence = min(0.95, best_confidence + 0.2)

        # Enforce minimum margin and confidence; prefer previous or English if ambiguous
        if best_confidence < self.min_confidence or (best_score - second_score) < self.min_margin:
            # Prefer sticky previous language when enabled and plausible
            if self.enable_stickiness and previous_language and previous_language in language_votes:
                return DetectionResult(
                    language=previous_language,
                    confidence=min(0.9, max(best_confidence, 0.7)),
                    method='sticky_previous',
                    raw_results={'reason': 'below_threshold_or_margin', 'votes': language_votes, 'raw': raw_results}
                )
            # Prefer English for high ASCII ratio without strong Spanish markers
            lower = clean_text.lower()
            if self.prefer_english_for_ascii and ascii_ratio > 0.95 and spanish_markers == 0 \
               and (english_markers > 0 or re.search(r'^(how|what|why|where|when|who|can|could|should|would|is|are|does|do)\b', lower) or re.search(r'\b(please|thanks)\b', lower)):
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

    def _detect_by_script(self, text: str) -> DetectionResult:
        """
        High-confidence script-based detection with comprehensive patterns.
        """
        text_lower = text.lower()
        
        # Comprehensive script patterns with confidence scores
        script_patterns = [
            ('zh', r'[\u4e00-\u9fff]', 0.95),           # Chinese
            ('ja', r'[\u3040-\u309f\u30a0-\u30ff]', 0.95),  # Japanese
            ('ko', r'[\uac00-\ud7af]', 0.95),           # Korean
            ('ar', r'[\u0600-\u06ff]', 0.95),           # Arabic
            ('he', r'[\u0590-\u05ff]', 0.95),           # Hebrew
            ('hi', r'[\u0900-\u097f]', 0.95),           # Devanagari
            ('th', r'[\u0e00-\u0e7f]', 0.95),           # Thai
            ('ru', r'[\u0400-\u04ff]', 0.8),            # Cyrillic (could be multiple languages)
            ('el', r'[\u0370-\u03ff]', 0.95),           # Greek
        ]
        
        for lang_code, pattern, confidence in script_patterns:
            if re.search(pattern, text):
                return DetectionResult(
                    language=lang_code,
                    confidence=confidence,
                    method='script_detection',
                    raw_results={'pattern': pattern, 'matched_script': lang_code}
                )

        # High-confidence phrase patterns for French short questions.
        # These help disambiguate cases like "Qui es tu?" that are often misclassified
        # as Spanish or English by statistical backends on short ASCII text.
        french_phrase_patterns: List[str] = [
            r"\bqui\s+es[- ]?tu\b",                    # qui es-tu / qui es tu
            r"\bqui\s+êtes[- ]?vous\b",               # qui êtes-vous (with accent)
            r"\bqui\s+etes[- ]?vous\b",               # qui etes vous (without accent)
            r"\best[- ]?ce\s+que\b",                  # est-ce que
        ]

        for pattern in french_phrase_patterns:
            if re.search(pattern, text_lower):
                return DetectionResult(
                    language='fr',
                    confidence=0.95,
                    method='phrase_pattern_detection',
                    raw_results={'pattern': pattern}
                )

        # High-confidence word patterns for Latin scripts
        word_patterns = [
            ('es', [r'¿', r'\baño\b', r'\bestá\b', r'\bqué\b'], 0.9),
            ('pt', [r'\bção\b', r'\bvocê\b', r'\bporque\b', r'\bestão\b'], 0.9),
            # Add common accentless/variant forms to better catch French without punctuation
            ('fr', [r"\bc[’']?est\b", r"\bqu'est-ce\b", r'\bvoilà\b', r'\bvoila\b', r'\bparce\b', r'\best[- ]?ce\b'], 0.9),
            ('de', [r'[äöüß]', r'\bund\b', r'\bdas\b', r'\bist\b'], 0.85),
            ('it', [r'\bperché\b', r'\banche\b', r'\bquesto\b', r'\bdopo\b'], 0.85),
        ]
        
        for lang_code, patterns, confidence in word_patterns:
            matches = sum(1 for pattern in patterns if re.search(pattern, text_lower))
            if matches >= 1:
                actual_confidence = min(confidence, confidence * (matches / len(patterns)) + 0.3)
                return DetectionResult(
                    language=lang_code,
                    confidence=actual_confidence,
                    method='word_pattern_detection',
                    raw_results={'patterns_matched': matches, 'total_patterns': len(patterns)}
                )

        return DetectionResult(
            language='unknown',
            confidence=0.0,
            method='script_detection',
            raw_results={'reason': 'no_patterns_matched'}
        )

    def _clean_text_for_detection(self, text: str) -> str:
        """Lightweight cleaning to remove tokens that confuse detectors."""
        # Remove URLs and emails
        text = re.sub(r'https?://\S+|www\.\S+', ' ', text)
        text = re.sub(r'\b\S+@\S+\.[A-Za-z]{2,}\b', ' ', text)
        # Remove code fences/inline code
        text = re.sub(r'```[\s\S]*?```', ' ', text)
        text = re.sub(r'`[^`]*`', ' ', text)
        # Collapse excessive punctuation and numbers
        text = re.sub(r'[0-9_\-]{3,}', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _ascii_ratio(self, text: str) -> float:
        """Compute ratio of ASCII letters/digits/spaces to total characters."""
        if not text:
            return 1.0
        total = len(text)
        ascii_count = sum(1 for c in text if ord(c) < 128)
        return ascii_count / total if total else 1.0

    def _count_markers(self, text_lower: str, patterns: List[str]) -> int:
        """Count occurrences of any patterns in text."""
        return sum(1 for p in patterns if re.search(p, text_lower))

    def _detect_langdetect(self, text: str) -> Optional[DetectionResult]:
        """Detect language using langdetect library."""
        try:
            lang_probs = detect_langs(text)
            if lang_probs:
                best = lang_probs[0]
                return DetectionResult(
                    language=best.lang,
                    confidence=best.prob,
                    method='langdetect'
                )
        except LangDetectException:
            pass
        return None

    def _detect_langid(self, text: str) -> Optional[DetectionResult]:
        """Detect language using langid library."""
        if not LANGID_AVAILABLE:
            return None
        try:
            # Prefer rank() to get comparable scores; convert via softmax to obtain a probability
            if hasattr(langid, 'rank'):
                ranked = langid.rank(text)
                if ranked:
                    # ranked is list of (lang, score), scores may be log-probs; use softmax over top-K
                    top_k = ranked[:5]
                    max_score = max(s for _, s in top_k)
                    exps = [math.exp(s - max_score) for _, s in top_k]
                    total = sum(exps) or 1.0
                    probs = [e / total for e in exps]
                    lang = top_k[0][0]
                    confidence = probs[0]
                    return DetectionResult(language=lang, confidence=confidence, method='langid')
            # Fallback to classify(); map score to probability via logistic transform
            lang, score = langid.classify(text)
            try:
                confidence = 1.0 / (1.0 + math.exp(-float(score)))
            except Exception:
                confidence = 0.7
            confidence = max(0.0, min(1.0, confidence))
            return DetectionResult(language=lang, confidence=confidence, method='langid')
        except Exception:
            pass
        return None

    def _detect_pycld2(self, text: str) -> Optional[DetectionResult]:
        """Detect language using pycld2 library."""
        if not PYCLD2_AVAILABLE:
            return None
        try:
            is_reliable, text_bytes_found, details = cld2.detect(text)
            if details and is_reliable:
                lang_code = details[0][1]
                confidence = details[0][2] / 100.0  # Convert percentage to decimal
                return DetectionResult(
                    language=lang_code,
                    confidence=confidence,
                    method='pycld2'
                )
        except Exception:
            pass
        return None
