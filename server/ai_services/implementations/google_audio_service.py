"""
Google audio service implementation using unified architecture.

This implementation provides audio capabilities using Google Cloud
Speech-to-Text and Text-to-Speech APIs.
"""

from typing import Dict, Any, Optional, Union
from io import BytesIO

from ..base import ServiceType
from ..providers import GoogleBaseService
from ..services import AudioService


class GoogleAudioService(AudioService, GoogleBaseService):
    """
    Google audio service using unified architecture.

    Supports:
    - Speech-to-text using Google Cloud Speech-to-Text API
    - Text-to-speech using Google Cloud Text-to-Speech API
    - Audio transcription
    - Audio translation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Google audio service."""
        # Initialize via GoogleBaseService first
        GoogleBaseService.__init__(self, config, ServiceType.AUDIO, "google")
        
        # Get audio-specific configuration
        provider_config = self._extract_provider_config()
        self.stt_model = provider_config.get('stt_model', 'latest_long')
        self.stt_language_code = provider_config.get('stt_language_code', 'en-US')
        self.stt_sample_rate = provider_config.get('stt_sample_rate', 16000)
        self.stt_encoding = provider_config.get('stt_encoding', 'LINEAR16')
        
        self.tts_model = provider_config.get('tts_model', 'neural2')
        self.tts_voice = provider_config.get('tts_voice', 'en-US-Neural2-A')
        self.tts_language_code = provider_config.get('tts_language_code', 'en-US')
        self.tts_audio_encoding = provider_config.get('tts_audio_encoding', 'MP3')
        self.tts_speaking_rate = provider_config.get('tts_speaking_rate', 1.0)
        self.tts_pitch = provider_config.get('tts_pitch', 0.0)
        
        # Initialize clients lazily
        self._speech_client = None
        self._tts_client = None

    async def initialize(self) -> bool:
        """Initialize the Google audio service and clients."""
        try:
            if self.initialized:
                return True

            # Import Google Cloud libraries
            try:
                from google.cloud import speech
                from google.cloud import texttospeech
            except ImportError:
                raise ImportError(
                    "Google Cloud Speech and Text-to-Speech libraries are required. "
                    "Install with: pip install google-cloud-speech google-cloud-texttospeech"
                )

            # Initialize Speech-to-Text client
            self._speech_client = speech.SpeechAsyncClient()
            
            # Initialize Text-to-Speech client
            self._tts_client = texttospeech.TextToSpeechAsyncClient()

            # Call parent initialize
            return await super().initialize()

        except Exception as e:
            self.logger.error(f"Failed to initialize Google audio service: {str(e)}")
            return False

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Convert text to speech audio using Google Cloud Text-to-Speech."""
        if not self.initialized:
            await self.initialize()

        try:
            from google.cloud import texttospeech

            # Use provided voice or default from config
            tts_voice = voice or self.tts_voice
            
            # Use provided format or default from config
            audio_format = format or self.tts_audio_encoding.lower()
            
            # Map format to Google encoding
            encoding_map = {
                'mp3': texttospeech.AudioEncoding.MP3,
                'linear16': texttospeech.AudioEncoding.LINEAR16,
                'ogg_opus': texttospeech.AudioEncoding.OGG_OPUS,
            }
            audio_encoding = encoding_map.get(audio_format, texttospeech.AudioEncoding.MP3)

            # Build synthesis input
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Build voice configuration
            voice_config = texttospeech.VoiceSelectionParams(
                language_code=self.tts_language_code,
                name=tts_voice,
                ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
            )

            # Build audio configuration
            audio_config = texttospeech.AudioConfig(
                audio_encoding=audio_encoding,
                speaking_rate=self.tts_speaking_rate,
                pitch=self.tts_pitch
            )

            # Call Google TTS API
            response = await self._tts_client.synthesize_speech(
                input=synthesis_input,
                voice=voice_config,
                audio_config=audio_config
            )

            return response.audio_content

        except Exception as e:
            self._handle_google_error(e, "text-to-speech")
            raise

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Convert speech audio to text using Google Cloud Speech-to-Text."""
        if not self.initialized:
            await self.initialize()

        try:
            from google.cloud import speech

            # Prepare audio data
            audio_data = self._prepare_audio(audio)
            
            # Get audio format
            audio_format = self._get_audio_format(audio) if isinstance(audio, str) else 'wav'

            # Map format to Google encoding
            encoding_map = {
                'linear16': speech.RecognitionConfig.AudioEncoding.LINEAR16,
                'flac': speech.RecognitionConfig.AudioEncoding.FLAC,
                'mulaw': speech.RecognitionConfig.AudioEncoding.MULAW,
                'amr': speech.RecognitionConfig.AudioEncoding.AMR,
                'amr_wb': speech.RecognitionConfig.AudioEncoding.AMR_WB,
                'ogg_opus': speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                'speex': speech.RecognitionConfig.AudioEncoding.SPEEX_WITH_HEADER_BYTE,
            }
            
            # Default to LINEAR16 if format not recognized
            audio_encoding = encoding_map.get(self.stt_encoding.lower(), 
                                             speech.RecognitionConfig.AudioEncoding.LINEAR16)

            # Use provided language or default from config
            language_code = language or self.stt_language_code

            # Build recognition config
            config = speech.RecognitionConfig(
                encoding=audio_encoding,
                sample_rate_hertz=self.stt_sample_rate,
                language_code=language_code,
                model=self.stt_model,
                **kwargs
            )

            # Build recognition audio
            recognition_audio = speech.RecognitionAudio(content=audio_data)

            # Call Google Speech-to-Text API
            response = await self._speech_client.recognize(
                config=config,
                audio=recognition_audio
            )

            # Extract transcript
            if response.results:
                return response.results[0].alternatives[0].transcript
            else:
                return ""

        except Exception as e:
            self._handle_google_error(e, "speech-to-text")
            raise

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Transcribe audio to text (alias for speech_to_text)."""
        return await self.speech_to_text(audio, language, **kwargs)

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """Translate audio from one language to another using Google Cloud."""
        if not self.initialized:
            await self.initialize()

        try:
            # First transcribe the audio
            transcript = await self.speech_to_text(audio, source_language, **kwargs)
            
            # Then translate using Google Cloud Translation API
            # Note: This requires google-cloud-translate library
            try:
                from google.cloud import translate_v2 as translate
                
                translate_client = translate.Client()
                
                # Translate text
                result = translate_client.translate(
                    transcript,
                    target_language=target_language
                )
                
                return result['translatedText']
            except ImportError:
                # Fallback: return transcript if translation library not available
                self.logger.warning(
                    "Google Cloud Translation library not available. "
                    "Returning transcript without translation. "
                    "Install with: pip install google-cloud-translate"
                )
                return transcript

        except Exception as e:
            self._handle_google_error(e, "audio translation")
            raise

    async def close(self) -> None:
        """Close the Google audio service and release resources."""
        if self._speech_client:
            # Google Cloud clients don't have explicit close methods
            self._speech_client = None
        
        if self._tts_client:
            self._tts_client = None
        
        await super().close()

