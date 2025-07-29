"""
Language Detection Step

This step detects the language of the user's message for better language matching.
"""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from langdetect import detect_langs, LangDetectException, DetectorFactory
from ..base import PipelineStep, ProcessingContext

# Seed the language detector for deterministic results
DetectorFactory.seed = 0

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
        
        # Always available - langdetect
        if 'langdetect' in enabled_backends:
            self.backends.append(('langdetect', backend_weights.get('langdetect', 1.0), self._detect_langdetect))
        
        # Optional backends
        if 'langid' in enabled_backends and LANGID_AVAILABLE:
            self.backends.append(('langid', backend_weights.get('langid', 1.2), self._detect_langid))
            
        if 'pycld2' in enabled_backends and PYCLD2_AVAILABLE:
            self.backends.append(('pycld2', backend_weights.get('pycld2', 1.5), self._detect_pycld2))
        
        # Store configuration
        self.min_confidence = lang_config.get('min_confidence', 0.7)
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
            result = self._detect_language_ensemble(context.message)
            context.detected_language = result.language
            
            # Store additional metadata for debugging
            if not hasattr(context, 'language_detection_meta'):
                context.language_detection_meta = {}
            context.language_detection_meta.update({
                'confidence': result.confidence,
                'method': result.method,
                'raw_results': result.raw_results
            })
            
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
    
    def _detect_language_ensemble(self, text: str) -> DetectionResult:
        """
        Detect language using ensemble of multiple backends with confidence scoring.

        Args:
            text: The text to analyze

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

        # First try high-confidence script-based detection
        script_result = self._detect_by_script(text)
        if script_result.confidence > 0.9:
            return script_result

        # Run all available backends
        backend_results = []
        raw_results = {}
        
        for backend_name, weight, detector_func in self.backends:
            try:
                result = detector_func(text)
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

        # Weighted voting
        language_votes = {}
        total_weight = 0
        
        for result, weight, backend_name in backend_results:
            lang = result.language if hasattr(result, 'language') else result
            conf = result.confidence if hasattr(result, 'confidence') else 0.8
            
            weighted_score = conf * weight
            if lang not in language_votes:
                language_votes[lang] = 0
            language_votes[lang] += weighted_score
            total_weight += weight

        # Find best language
        best_language = max(language_votes.keys(), key=lambda k: language_votes[k])
        best_confidence = language_votes[best_language] / total_weight if total_weight > 0 else 0
        
        # If script detection had moderate confidence, boost it
        if script_result.confidence > 0.5 and script_result.language == best_language:
            best_confidence = min(0.95, best_confidence + 0.2)

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

        # High-confidence word patterns for Latin scripts
        word_patterns = [
            ('es', [r'¿', r'\baño\b', r'\bestá\b', r'\bqué\b'], 0.9),
            ('pt', [r'\bção\b', r'\bvocê\b', r'\bporque\b', r'\bestão\b'], 0.9),
            ('fr', [r"\bc'est\b", r"\bqu'est-ce\b", r'\bvoilà\b', r'\bparce\b'], 0.9),
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
            lang, confidence = langid.classify(text)
            return DetectionResult(
                language=lang,
                confidence=confidence,
                method='langid'
            )
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
