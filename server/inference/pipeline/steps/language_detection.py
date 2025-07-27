"""
Language Detection Step

This step detects the language of the user's message for better language matching.
"""

import logging
import re
from typing import Dict, Any
from langdetect import detect, LangDetectException, DetectorFactory
from ..base import PipelineStep, ProcessingContext

# Seed the language detector for deterministic results
DetectorFactory.seed = 0


class LanguageDetectionStep(PipelineStep):
    """
    Detect the language of the user's message.
    
    This step uses the 'langdetect' library to determine the language of the message.
    """
    
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.
        
        Returns:
            True if language detection is enabled and message exists
        """
        config = self.container.get_or_none('config') or {}
        language_detection_enabled = config.get('general', {}).get('language_detection', False)
        
        return language_detection_enabled and bool(context.message) and not context.is_blocked
    
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
            # Detect language using the langdetect library
            detected_language = self._detect_language(context.message)
            context.detected_language = detected_language
            
            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                self.logger.info(f"DEBUG: Detected language: {detected_language} for message: {context.message[:50]}...")
            
        except Exception as e:
            self.logger.error(f"Error during language detection: {str(e)}")
            # Default to English on error
            context.detected_language = 'en'
        
        return context
    
    def _detect_language(self, text: str) -> str:
        """
        Detect language using a hybrid approach: lightweight patterns first,
        then the langdetect library as a fallback.

        Args:
            text: The text to analyze

        Returns:
            Language code (ISO 639-1 format)
        """
        if not text or len(text.strip()) < 3:
            return 'en'  # Default to English for very short text

        text_lower = text.lower()

        # High-confidence script-based detection (from old module)
        language_patterns = [
            ('zh', r'[\u4e00-\u9fff]'),      # Chinese
            ('ja', r'[\u3040-\u309f\u30a0-\u30ff]'),  # Japanese (Hiragana/Katakana)
            ('ko', r'[\uac00-\ud7af]'),      # Korean
            ('ru', r'[\u0400-\u04ff]'),      # Cyrillic
            ('ar', r'[\u0600-\u06ff]'),      # Arabic
            ('he', r'[\u0590-\u05ff]'),      # Hebrew
            ('hi', r'[\u0900-\u097f]'),      # Devanagari
        ]

        for lang_code, pattern in language_patterns:
            if re.search(pattern, text):
                return lang_code

        # High-confidence word/accent patterns for Latin languages
        # Inspired by the old module's pattern repository
        if '¿' in text:
            return 'es'
        if 'ção' in text_lower or 'você' in text_lower:
            return 'pt'
        if 'c\'est' in text_lower or 'qu\'est-ce' in text_lower:
            return 'fr'
        if 'ä' in text_lower or 'ö' in text_lower or 'ü' in text_lower or 'ß' in text_lower:
            return 'de'

        # Fallback to langdetect library
        try:
            return detect(text)
        except LangDetectException:
            self.logger.warning("Language detection failed, defaulting to English.")
            return 'en'
