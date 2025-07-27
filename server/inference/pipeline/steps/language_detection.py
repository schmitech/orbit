"""
Language Detection Step

This step detects the language of the user's message for better language matching.
"""

import logging
import re
from typing import Dict, Any
from ..base import PipelineStep, ProcessingContext

class LanguageDetectionStep(PipelineStep):
    """
    Detect the language of the user's message.
    
    This step uses a lightweight, fast approach to detect language
    without requiring external libraries for better performance.
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
            # Detect language using lightweight pattern matching
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
        Detect language using lightweight pattern matching.
        
        This is a fast, lightweight approach that covers common languages
        without requiring external dependencies.
        
        Args:
            text: The text to analyze
            
        Returns:
            Language code (ISO 639-1 format)
        """
        if not text or len(text.strip()) < 2:
            return 'en'  # Default to English for very short text
        
        text = text.lower().strip()
        
        # Common language patterns - order matters (most specific first)
        language_patterns = [
            # Chinese (Traditional and Simplified)
            ('zh', r'[\u4e00-\u9fff\u3400-\u4dbf]'),
            
            # Japanese (Hiragana, Katakana, Kanji)
            ('ja', r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]'),
            
            # Korean
            ('ko', r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]'),
            
            # Arabic
            ('ar', r'[\u0600-\u06ff\u0750-\u077f]'),
            
            # Russian/Cyrillic
            ('ru', r'[\u0400-\u04ff]'),
            
            # Greek
            ('el', r'[\u0370-\u03ff]'),
            
            # Hebrew
            ('he', r'[\u0590-\u05ff]'),
            
            # Thai
            ('th', r'[\u0e00-\u0e7f]'),
            
            # Hindi/Devanagari
            ('hi', r'[\u0900-\u097f]'),
            
            # French - common words and patterns
            ('fr', r'\b(je|tu|il|elle|nous|vous|ils|elles|le|la|les|un|une|des|du|de|et|ou|mais|donc|car|ni|que|qui|quoi|comment|pourquoi|où|quand|avec|sans|pour|par|sur|sous|dans|chez|être|avoir|faire|aller|venir|voir|savoir|pouvoir|vouloir|devoir|dire|prendre|donner|mettre|porter|tenir|garder|laisser|passer|rester|arriver|partir|sortir|entrer|monter|descendre|tomber|mourir|naître|vivre|aimer|détester|préférer|choisir|décider|penser|croire|espérer|attendre|chercher|trouver|perdre|gagner|jouer|travailler|étudier|apprendre|enseigner|parler|écouter|regarder|entendre|sentir|toucher|goûter|manger|boire|dormir|se|me|te|nous|vous|se|mon|ma|mes|ton|ta|tes|son|sa|ses|notre|nos|votre|vos|leur|leurs)\b'),
            
            # German - common words and patterns
            ('de', r'\b(ich|du|er|sie|es|wir|ihr|sie|der|die|das|ein|eine|eines|und|oder|aber|doch|denn|noch|auch|nur|schon|wieder|immer|nie|oft|manchmal|heute|morgen|gestern|hier|dort|da|wo|wie|was|wer|wann|warum|mit|ohne|für|gegen|um|über|unter|vor|nach|bei|zu|von|aus|in|an|auf|ab|bis|durch|seit|während|trotz|wegen|statt|außer|neben|zwischen|hinter|sein|haben|werden|können|müssen|sollen|wollen|dürfen|mögen|lassen|gehen|kommen|sehen|hören|sagen|machen|tun|geben|nehmen|bringen|holen|kaufen|verkaufen|arbeiten|spielen|lernen|lehren|sprechen|essen|trinken|schlafen|leben|sterben|lieben|hassen|denken|glauben|hoffen|warten|suchen|finden|verlieren|gewinnen|ich|mich|mir|mein|meine|du|dich|dir|dein|deine|er|ihn|ihm|sein|seine|sie|ihr|unser|unsere|euer|eure)\b'),
            
            # Spanish - common words and patterns
            ('es', r'\b(yo|tú|él|ella|nosotros|nosotras|vosotros|vosotras|ellos|ellas|el|la|los|las|un|una|unos|unas|y|o|pero|sino|porque|para|por|con|sin|de|del|en|a|al|desde|hasta|sobre|bajo|ante|tras|durante|mediante|según|contra|entre|hacia|dentro|fuera|arriba|abajo|delante|detrás|cerca|lejos|ser|estar|haber|tener|hacer|ir|venir|ver|saber|poder|querer|deber|decir|dar|poner|llevar|traer|coger|dejar|pasar|quedar|llegar|salir|entrar|subir|bajar|caer|morir|nacer|vivir|amar|odiar|preferir|elegir|decidir|pensar|creer|esperar|buscar|encontrar|perder|ganar|jugar|trabajar|estudiar|aprender|enseñar|hablar|escuchar|mirar|oír|sentir|tocar|probar|comer|beber|dormir|me|te|se|nos|os|mi|mis|tu|tus|su|sus|nuestro|nuestra|nuestros|nuestras|vuestro|vuestra|vuestros|vuestras|que|qué|quien|quién|cual|cuál|cuando|cuándo|donde|dónde|como|cómo|por|qué|porque)\b'),
            
            # Italian - common words
            ('it', r'\b(io|tu|lui|lei|noi|voi|loro|il|la|lo|gli|le|un|una|uno|e|o|ma|però|perché|per|con|senza|di|del|della|dello|dei|delle|degli|in|a|da|su|sotto|sopra|davanti|dietro|vicino|lontano|dentro|fuori|essere|avere|fare|andare|venire|vedere|sapere|potere|volere|dovere|dire|dare|mettere|portare|prendere|lasciare|rimanere|arrivare|partire|uscire|entrare|salire|scendere|cadere|morire|nascere|vivere|amare|odiare|preferire|scegliere|decidere|pensare|credere|sperare|aspettare|cercare|trovare|perdere|vincere|giocare|lavorare|studiare|imparare|insegnare|parlare|ascoltare|guardare|sentire|toccare|assaggiare|mangiare|bere|dormire|mi|ti|si|ci|vi|mio|mia|miei|mie|tuo|tua|tuoi|tue|suo|sua|suoi|sue|nostro|nostra|nostri|nostre|vostro|vostra|vostri|vostre|che|chi|quale|quando|dove|come|perché)\b'),
            
            # Portuguese - common words
            ('pt', r'\b(eu|tu|você|ele|ela|nós|vocês|eles|elas|o|a|os|as|um|uma|uns|umas|e|ou|mas|porém|porque|para|por|com|sem|de|do|da|dos|das|em|no|na|nos|nas|ao|à|aos|às|desde|até|sobre|sob|ante|após|durante|mediante|segundo|contra|entre|para|dentro|fora|acima|abaixo|diante|atrás|perto|longe|ser|estar|haver|ter|fazer|ir|vir|ver|saber|poder|querer|dever|dizer|dar|por|levar|trazer|pegar|deixar|ficar|chegar|sair|entrar|subir|descer|cair|morrer|nascer|viver|amar|odiar|preferir|escolher|decidir|pensar|acreditar|esperar|procurar|encontrar|perder|ganhar|jogar|trabalhar|estudar|aprender|ensinar|falar|escutar|olhar|ouvir|sentir|tocar|provar|comer|beber|dormir|me|te|se|nos|lhe|lhes|meu|minha|meus|minhas|teu|tua|teus|tuas|seu|sua|seus|suas|nosso|nossa|nossos|nossas|que|quem|qual|quando|onde|como|por|que)\b'),
            
            # Dutch - common words
            ('nl', r'\b(ik|jij|je|hij|zij|ze|wij|we|jullie|zij|ze|de|het|een|en|of|maar|echter|omdat|voor|met|zonder|van|in|op|aan|bij|naar|uit|over|onder|boven|achter|voor|naast|tussen|binnen|buiten|zijn|hebben|worden|kunnen|mogen|moeten|willen|zullen|doen|gaan|komen|zien|weten|zeggen|geven|nemen|brengen|halen|laten|blijven|gaan|komen|vertrekken|weggaan|binnengaan|opgaan|neergaan|vallen|sterven|geboren|leven|houden|haten|kiezen|beslissen|denken|geloven|hopen|wachten|zoeken|vinden|verliezen|winnen|spelen|werken|studeren|leren|onderwijzen|spreken|luisteren|kijken|horen|voelen|aanraken|proeven|eten|drinken|slapen|me|je|zich|ons|mijn|jouw|zijn|haar|ons|onze|jullie|hun|dat|wat|wie|welke|wanneer|waar|hoe|waarom)\b'),
        ]
        
        # Check for script-based languages first (higher confidence)
        for lang_code, pattern in language_patterns[:8]:  # Script-based languages
            if re.search(pattern, text):
                return lang_code
        
        # For Latin-script languages, we need more text to be confident
        if len(text) < 10:
            # For very short text, just check for obvious non-English patterns
            for lang_code, pattern in language_patterns[8:]:
                if re.search(pattern, text):
                    return lang_code
            return 'en'  # Default to English for short Latin-script text
        
        # For longer text, check Latin-script language patterns
        for lang_code, pattern in language_patterns[8:]:
            matches = len(re.findall(pattern, text))
            words = len(text.split())
            
            # If significant portion matches, likely that language
            if words > 0 and matches / words > 0.3:
                return lang_code
        
        # Check for common English patterns as final check
        english_patterns = r'\b(the|and|or|but|for|with|without|in|on|at|by|to|from|of|about|through|during|before|after|above|below|over|under|between|among|within|outside|inside|this|that|these|those|some|any|all|each|every|no|none|not|yes|very|quite|really|just|only|also|too|even|still|yet|already|never|always|often|sometimes|usually|generally|probably|maybe|perhaps|here|there|where|when|how|what|who|why|which|whose|whom|can|could|may|might|must|should|would|will|shall|do|does|did|have|has|had|am|is|are|was|were|been|being|get|got|give|gave|go|went|come|came|see|saw|know|knew|think|thought|say|said|tell|told|make|made|take|took|put|let|help|work|play|live|love|like|want|need|feel|look|seem|become|became)\b'
        
        english_matches = len(re.findall(english_patterns, text))
        words = len(text.split())
        
        if words > 0 and english_matches / words > 0.4:
            return 'en'
        
        # Default to English if no clear pattern found
        return 'en'