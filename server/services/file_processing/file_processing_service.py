"""
File Processing Service

Main service for processing uploaded files: extraction, chunking, and storage preparation.
"""

import asyncio
import json
import logging
import uuid
import hashlib
import weakref
from typing import Dict, Any, List, Optional
from datetime import datetime, UTC

from services.file_processing.processor_registry import FileProcessorRegistry
from services.file_processing.chunking import (
    FixedSizeChunker, SemanticChunker, TokenChunker, RecursiveChunker, MarkdownHeaderChunker, Chunk
)
from services.file_processing.magika_detector import (
    FileValidationError,
    MagikaDetector,
    canonicalize_label,
    canonicalize_mime_type,
)
from services.file_storage import (
    FileStorageBackend, create_storage_backend, FileEncryptor, EncryptedFileStorageBackend,
)
from services.file_metadata.metadata_store import FileMetadataStore

logger = logging.getLogger(__name__)

# MIME types where HTML/JS patterns are expected content (not injections)
_CONTENT_SCAN_SKIP_MIME_TYPES = frozenset({
    'text/javascript', 'application/javascript',
    'text/typescript', 'application/typescript',
    'text/x-python', 'text/x-python-script',
    'text/x-java-source', 'text/x-java',
    'text/x-sql', 'application/x-sql', 'application/sql',
    'text/x-c++src', 'text/x-csrc', 'text/x-c',
    'text/x-go', 'text/x-rust', 'text/x-ruby', 'text/x-php',
    'text/x-shellscript', 'text/x-sh',
    'text/html',
})

# Patterns that indicate embedded HTML/JS in non-code files (polyglot / injection attacks)
_DANGEROUS_CONTENT_PATTERNS = (
    b'<script',
    b'javascript:',
    b'<iframe',
    b'onerror=',
    b'onload=',
    b'onclick=',
)


class FileProcessingService:
    """
    Main service for file processing pipeline.
    
    Handles:
    - File type detection
    - Text extraction
    - Chunking
    - Storage preparation
    - Metadata tracking
    """
    
    def __init__(self, config: Dict[str, Any], app_state=None):
        """
        Initialize file processing service.

        Args:
            config: Configuration dictionary
            app_state: Optional FastAPI app state for accessing services (e.g., adapter_manager)
        """
        self.config = config
        self.app_state = app_state
        self.logger = logging.getLogger(self.__class__.__name__)

        # Get files configuration section
        files_config = config.get('files', {})
        processing_config = files_config.get('processing', {})

        # Initialize components
        self.storage = self._init_storage()
        self._file_encryptor = self._init_file_encryptor(files_config)
        self.encrypted_storage = (
            EncryptedFileStorageBackend(self.storage, self._file_encryptor)
            if self._file_encryptor else None
        )
        self.metadata_store = FileMetadataStore(config=config)
        self.processor_registry = FileProcessorRegistry(config=config)
        self.chunker = self._init_chunker()
        self.magika_config = processing_config.get('magika', {})
        self.magika_detector = self._init_magika_detector()
        # Serializes final persistence and deletion for each file. Weak references
        # keep completed uploads from accumulating locks for process lifetime.
        self._file_operation_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

        # Configuration - get from adapter config first, then files.processing, then default
        self.max_file_size = config.get('max_file_size') or \
                             processing_config.get('max_file_size', 52428800)  # 50MB
        self.supported_types = config.get('supported_types') or \
                              processing_config.get('supported_types', [
            'application/pdf',
            'text/plain',
            'text/markdown',
            'text/csv',
            'application/json',
            'text/html',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
            # Code file types
            'text/x-python',
            'text/x-python-script',  # Alternative MIME type for Python files
            'text/x-java-source',
            'text/x-java',
            'text/x-sql',
            'application/x-sql',
            'application/sql',
            'text/javascript',
            'application/javascript',
            'text/typescript',
            'application/typescript',
            'text/x-c++src',
            'text/x-csrc',
            'text/x-c',
            'text/x-go',
            'text/x-rust',
            'text/x-ruby',
            'text/x-php',
            'text/x-shellscript',
            'text/x-sh',
            'text/yaml',
            'text/x-yaml',
            'text/xml',
            'application/xml',
            'text/css',
            'text/x-scss',
            'text/x-sass',
            'text/x-less',
            # Image types
            'image/png',
            'image/jpeg',
            'image/jpg',
            'image/gif',
            'image/bmp',
            'image/tiff',
            'image/webp',
            # Audio types
            'audio/wav',
            'audio/mpeg',
            'audio/mp3',
            'audio/mp4',
            'audio/ogg',
            'audio/flac',
            'audio/webm',
            'audio/x-m4a',
            'audio/aac',
        ])

        # Vision service configuration - follows same pattern as embeddings/inference
        # Priority: adapter config > global vision config > default
        # NOTE: Default vision provider is set here, but can be overridden per-file based on API key's adapter
        vision_config = config.get('vision', {})

        # Enable/disable vision processing
        # Priority: adapter config > global vision config > default True
        self.enable_vision = config.get('enable_vision', vision_config.get('enabled', True))

        # Get DEFAULT vision provider (can be overridden per-upload based on adapter)
        # Priority: adapter config > global vision config > default
        self.default_vision_provider = config.get('vision_provider', vision_config.get('provider', 'gemini'))

        # Get provider-specific configs from 'visions' section (plural, like 'embeddings', 'inferences')
        self.vision_config = config.get('visions', {})

        # Log default vision configuration
        if self.enable_vision:
            provider_config = self.vision_config.get(self.default_vision_provider, {})
            model = provider_config.get('model', 'default')
            logger.info(f"Default vision service configured: provider={self.default_vision_provider}, model={model}")
            logger.info("Vision provider can be overridden per-upload based on API key's adapter configuration")

        # Audio service configuration - follows same pattern as vision/embeddings/inference
        # Uses stt.yaml for STT (speech-to-text) configuration
        # Priority: adapter config > global stt config > default
        # NOTE: Default STT provider is set here, but can be overridden per-file based on API key's adapter
        stt_config = config.get('stt', {})

        # Enable/disable audio processing
        # Priority: adapter config > global stt config > default True
        self.enable_audio = config.get('enable_audio', stt_config.get('enabled', True))

        # Get DEFAULT STT provider for audio transcription (can be overridden per-upload based on adapter)
        # Priority: adapter config > global stt config > default
        self.default_audio_provider = config.get('stt_provider', stt_config.get('provider', 'whisper'))

        # Store the full config for passing to AIServiceFactory
        # The factory expects 'stt_providers' and 'tts_providers' keys
        self.stt_providers_config = config.get('stt_providers', {})
        self.tts_providers_config = config.get('tts_providers', {})

        # Log default audio configuration
        if self.enable_audio:
            provider_config = self.stt_providers_config.get(self.default_audio_provider, {})
            model = provider_config.get('stt_model', provider_config.get('model_size', 'default'))
            logger.info(f"Default STT service configured: provider={self.default_audio_provider}, model={model}")
            logger.info("STT provider can be overridden per-upload based on API key's adapter configuration")

    def _init_magika_detector(self) -> Optional[MagikaDetector]:
        """Initialize Magika upload inspection if configured."""
        if not self.magika_config.get('enabled', False):
            return None

        detector = MagikaDetector(
            enabled=True,
            prediction_mode=self.magika_config.get('prediction_mode', 'HIGH_CONFIDENCE'),
            log_detection_details=self.magika_config.get('log_detection_details', True),
        )
        logger.info(
            "Magika upload inspection enabled (enforcement=%s, prediction_mode=%s)",
            self.magika_config.get('enforcement', 'block'),
            self.magika_config.get('prediction_mode', 'HIGH_CONFIDENCE'),
        )
        return detector
    
    def _init_storage(self) -> FileStorageBackend:
        """Initialize storage backend (filesystem, s3/minio, or azure)."""
        return create_storage_backend(self.config)

    def _init_file_encryptor(self, files_config: Dict[str, Any]) -> Optional[FileEncryptor]:
        """
        Initialize the shared FileEncryptor if files.encryption.enabled is true.

        Used both to build self.encrypted_storage (file bytes + metadata
        sidecar) and to encrypt indexed chunk text/metadata. Fails loudly if
        enabled but the key is missing/invalid, matching the fail-fast
        convention used for cloud bucket/container verification.
        """
        encryption_config = files_config.get('encryption', {})
        if not encryption_config.get('enabled', False):
            return None
        return FileEncryptor.from_env()
    
    def _init_chunker(self):
        """Initialize chunking strategy."""
        # Get from adapter config first, then global files config, then defaults
        files_config = self.config.get('files', {})
        strategy = self.config.get('chunking_strategy') or \
                  files_config.get('default_chunking_strategy', 'fixed')
        chunk_size = self.config.get('chunk_size') or \
                    files_config.get('default_chunk_size', 1000)
        overlap = self.config.get('chunk_overlap') or \
                 files_config.get('default_chunk_overlap', 200)
        
        # Get optional tokenizer configuration
        tokenizer = self.config.get('tokenizer') or files_config.get('tokenizer')
        use_tokens = self.config.get('use_tokens', False) or files_config.get('use_tokens', False)
        
        # Get strategy-specific options
        chunking_options = self.config.get('chunking_options', {}) or files_config.get('chunking_options', {})
        
        # Log chunking strategy initialization
        logger.debug(f"Initializing chunking strategy: '{strategy}' (chunk_size={chunk_size}, overlap={overlap})")
        
        if strategy == 'semantic':
            # Semantic chunking options
            model_name = chunking_options.get('model_name')
            use_advanced = chunking_options.get('use_advanced', False)
            chunk_size_tokens = chunking_options.get('chunk_size_tokens')
            threshold = chunking_options.get('threshold', 0.8)
            similarity_window = chunking_options.get('similarity_window', 3)
            min_sentences_per_chunk = chunking_options.get('min_sentences_per_chunk', 1)
            min_characters_per_sentence = chunking_options.get('min_characters_per_sentence', 24)
            skip_window = chunking_options.get('skip_window', 0)
            filter_window = chunking_options.get('filter_window', 5)
            filter_polyorder = chunking_options.get('filter_polyorder', 3)
            filter_tolerance = chunking_options.get('filter_tolerance', 0.2)
            
            chunker = SemanticChunker(
                chunk_size=chunk_size,
                overlap=overlap,
                model_name=model_name,
                use_advanced=use_advanced,
                threshold=threshold,
                similarity_window=similarity_window,
                min_sentences_per_chunk=min_sentences_per_chunk,
                min_characters_per_sentence=min_characters_per_sentence,
                skip_window=skip_window,
                filter_window=filter_window,
                filter_polyorder=filter_polyorder,
                filter_tolerance=filter_tolerance,
                tokenizer=tokenizer,
                chunk_size_tokens=chunk_size_tokens
            )
            logger.debug(f"  Semantic chunker configured: use_advanced={use_advanced}, model={model_name or 'none'}")
            return chunker

        elif strategy == 'token':
            # Token-based chunking
            chunker = TokenChunker(
                chunk_size=chunk_size,
                overlap=overlap,
                tokenizer=tokenizer or 'character'
            )
            logger.debug(f"  Token chunker configured: tokenizer={tokenizer or 'character'}")
            return chunker
        elif strategy == 'recursive':
            # Recursive chunking
            min_characters = chunking_options.get('min_characters_per_chunk', 24)
            chunker = RecursiveChunker(
                chunk_size=chunk_size,
                min_characters_per_chunk=min_characters,
                tokenizer=tokenizer
            )
            logger.debug(f"  Recursive chunker configured: min_characters_per_chunk={min_characters}")
            return chunker
        elif strategy == 'markdown_header':
            # Markdown-header-aware recursive chunking
            min_characters = chunking_options.get('min_characters_per_chunk', 24)
            chunker = MarkdownHeaderChunker(
                chunk_size=chunk_size,
                min_characters_per_chunk=min_characters,
                tokenizer=tokenizer
            )
            logger.debug(f"  Markdown header chunker configured: min_characters_per_chunk={min_characters}")
            return chunker
        else:
            # Fixed-size chunking (default)
            chunker = FixedSizeChunker(
                chunk_size=chunk_size,
                overlap=overlap,
                use_tokens=use_tokens,
                tokenizer=tokenizer
            )
            if logger.isEnabledFor(logging.DEBUG):
                mode = "token-based" if use_tokens else "character-based"
                logger.debug(f"  Fixed-size chunker configured: mode={mode}")
            return chunker

    def _resolve_supported_type(self, mime_type: Optional[str], label: Optional[str] = None) -> Optional[str]:
        """Resolve a MIME type or Magika label to one of the configured supported types."""
        candidates = []

        canonical_mime = canonicalize_mime_type(mime_type)
        if canonical_mime:
            candidates.append(canonical_mime)

        canonical_label = canonicalize_label(label)
        if canonical_label and canonical_label not in candidates:
            candidates.append(canonical_label)

        if mime_type and mime_type not in candidates:
            candidates.append(mime_type)

        for candidate in candidates:
            if candidate in self.supported_types:
                return candidate

        return None

    def _scan_for_dangerous_content(self, file_data: bytes, mime_type: str) -> None:
        """
        Scan the first 8 KB of a file for HTML/JS injection patterns.
        Skipped for code file types where these patterns are legitimate content.
        Raises FileValidationError if a dangerous pattern is found.
        """
        if mime_type in _CONTENT_SCAN_SKIP_MIME_TYPES:
            return

        scan_bytes = file_data[:8192].lower()
        for pattern in _DANGEROUS_CONTENT_PATTERNS:
            if pattern in scan_bytes:
                raise FileValidationError(
                    "Potentially dangerous content detected in uploaded file"
                )

    def inspect_upload(
        self,
        *,
        file_data: bytes,
        filename: str,
        claimed_mime_type: str,
    ) -> str:
        """
        Validate an upload and return the MIME type that should be used downstream.
        """
        if len(file_data) > self.max_file_size:
            raise ValueError(f"File size exceeds maximum {self.max_file_size} bytes")

        if not self.magika_detector:
            self._scan_for_dangerous_content(file_data, claimed_mime_type)
            return claimed_mime_type

        detection = self.magika_detector.identify_bytes(file_data)
        if detection is None:
            self._scan_for_dangerous_content(file_data, claimed_mime_type)
            return claimed_mime_type

        if self.magika_config.get('log_detection_details', True):
            logger.debug(
                "Magika upload inspection: filename=%s claimed_mime=%s detected_label=%s detected_mime=%s score=%.4f generic=%s",
                filename,
                claimed_mime_type,
                detection.label,
                detection.mime_type,
                detection.score,
                detection.is_generic,
            )

        if detection.is_generic_text and not self.magika_config.get('allow_generic_text_fallback', False):
            raise FileValidationError(
                "Uploaded file content could not be confidently classified beyond generic text"
            )

        if detection.is_generic_binary and not self.magika_config.get('allow_generic_binary_fallback', False):
            raise FileValidationError(
                "Uploaded file content could not be confidently classified and appears to be unknown binary data"
            )

        detected_type = self._resolve_supported_type(detection.mime_type, detection.label)
        if not detected_type:
            raise FileValidationError(
                f"Uploaded file content was detected as unsupported type '{detection.label or detection.mime_type}'"
            )

        claimed_type = self._resolve_supported_type(claimed_mime_type)
        if claimed_type and claimed_type != detected_type:
            raise FileValidationError(
                "Uploaded file content does not match the declared file type"
            )

        if not claimed_type and claimed_mime_type != 'application/octet-stream':
            raise FileValidationError(
                "Uploaded file content does not match the declared file type"
            )

        self._scan_for_dangerous_content(file_data, detected_type)
        return detected_type

    def _get_live_config(self) -> Dict[str, Any]:
        """
        Return the current full application config, preferring the hot-reloaded
        config held by the adapter manager over the startup snapshot.

        Provider-specific sections (``visions``, ``stt_providers``, ``tts_providers``)
        are captured at construction time, but adapters and providers can be updated
        and reloaded at runtime via the admin panel. Reading the adapter manager's
        live config ensures provider/model changes take effect without a server
        restart. Falls back to the startup snapshot if the live config is unavailable.
        """
        try:
            if self.app_state and hasattr(self.app_state, 'adapter_manager'):
                config_manager = getattr(self.app_state.adapter_manager, 'config_manager', None)
                live_config = getattr(config_manager, 'config', None)
                if live_config:
                    return live_config
        except Exception as e:
            logger.debug(f"Could not access live config from adapter manager, using startup snapshot: {e}")
        return self.config

    def _ai_ocr_is_priority(self) -> bool:
        """Whether the AI OCR processor is enabled and set as the priority processor."""
        processing = self.config.get('files', {}).get('processing', {})
        return (
            processing.get('ai_document_enabled', False)
            and processing.get('processor_priority') == 'ai_document'
        )

    async def _create_vision_service(self, vision_provider: str) -> Any:
        """
        Create (or fetch the cached) vision service for the given provider.

        Built from the current hot-reloaded config so that provider/model changes
        applied via adapter reload take effect without a server restart. The factory
        caches the instance, and that cache is invalidated on adapter reload.
        """
        from ai_services import AIServiceFactory, ServiceType

        live_config = self._get_live_config()
        return AIServiceFactory.create_service(
            ServiceType.VISION,
            vision_provider,
            {'visions': live_config.get('visions', {})}
        )

    async def _get_vision_provider_for_api_key(self, api_key: str) -> str:
        """
        Get the vision provider for a given API key by looking up its adapter configuration.

        This enables adapter-specific vision provider overrides (e.g., adapter A uses OpenAI, adapter B uses Gemini).

        Args:
            api_key: The API key to lookup

        Returns:
            Vision provider name (e.g., 'openai', 'gemini', 'anthropic')
        """
        try:
            # Try to get adapter manager from app state
            # Note: The adapter manager is stored as 'adapter_manager' in app.state (set by service_factory.py)
            if self.app_state and hasattr(self.app_state, 'adapter_manager'):
                adapter_manager = self.app_state.adapter_manager

                # Get API key service to lookup which adapter this API key uses
                if hasattr(self.app_state, 'api_key_service'):
                    api_key_service = self.app_state.api_key_service

                    # Get adapter name for this API key (pass adapter_manager to check live configs)
                    adapter_name, _ = await api_key_service.get_adapter_for_api_key(api_key, adapter_manager)

                    if adapter_name:
                        # Get adapter config from adapter manager
                        adapter_config = adapter_manager.get_adapter_config(adapter_name)

                        if adapter_config:
                            # Check if adapter has vision_provider override
                            vision_provider = adapter_config.get('vision_provider')

                            if vision_provider:
                                logger.info(f"Using adapter-specific vision provider '{vision_provider}' for adapter '{adapter_name}' (api_key: {api_key[:8]}...)")
                                return vision_provider

        except Exception as e:
            logger.warning(f"Could not lookup adapter-specific vision provider for API key: {e}")

        # Fall back to default vision provider
        logger.debug(f"Using default vision provider '{self.default_vision_provider}' for api_key: {api_key[:8]}...")
        return self.default_vision_provider

    async def _get_audio_provider_for_api_key(self, api_key: str) -> str:
        """
        Get the STT provider for a given API key by looking up its adapter configuration.

        This enables adapter-specific STT provider overrides (e.g., adapter A uses Whisper, adapter B uses Gemini).

        Args:
            api_key: The API key to lookup

        Returns:
            STT provider name (e.g., 'whisper', 'openai', 'gemini')
        """
        try:
            # Try to get adapter manager from app state
            # Note: The adapter manager is stored as 'adapter_manager' in app.state (set by service_factory.py)
            if self.app_state and hasattr(self.app_state, 'adapter_manager'):
                adapter_manager = self.app_state.adapter_manager

                # Get API key service to lookup which adapter this API key uses
                if hasattr(self.app_state, 'api_key_service'):
                    api_key_service = self.app_state.api_key_service

                    # Get adapter name for this API key (pass adapter_manager to check live configs)
                    adapter_name, _ = await api_key_service.get_adapter_for_api_key(api_key, adapter_manager)

                    if adapter_name:
                        # Get adapter config from adapter manager
                        adapter_config = adapter_manager.get_adapter_config(adapter_name)

                        if adapter_config:
                            # Check if adapter has stt_provider override
                            stt_provider = adapter_config.get('stt_provider')

                            if stt_provider:
                                logger.info(f"Using adapter-specific STT provider '{stt_provider}' for adapter '{adapter_name}' (api_key: {api_key[:8]}...)")
                                return stt_provider

        except Exception as e:
            logger.warning(f"Could not lookup adapter-specific STT provider for API key: {e}")

        # Fall back to default STT provider
        logger.debug(f"Using default STT provider '{self.default_audio_provider}' for api_key: {api_key[:8]}...")
        return self.default_audio_provider

    async def _requires_encryption_for_api_key(self, api_key: str) -> bool:
        """
        Check whether the adapter associated with this API key requires
        encrypted file storage (capabilities.requires_encryption).

        Args:
            api_key: The API key to lookup

        Returns:
            True if the adapter declares requires_encryption; False when there
            is nothing to resolve (no app_state/adapter_manager/api_key_service,
            or the API key has no associated adapter).

        Note:
            Deliberately does NOT catch exceptions from the lookup calls
            themselves (get_adapter_for_api_key / get_adapter_config). Unlike
            the vision/STT provider lookups this mirrors, defaulting to False
            on a transient failure here would silently store a classified
            adapter's upload in plaintext. A genuine lookup failure must fail
            the upload, not fail open.
        """
        if not (self.app_state and hasattr(self.app_state, 'adapter_manager')):
            return False
        adapter_manager = self.app_state.adapter_manager

        if not hasattr(self.app_state, 'api_key_service'):
            return False
        api_key_service = self.app_state.api_key_service

        adapter_name, _ = await api_key_service.get_adapter_for_api_key(api_key, adapter_manager)
        if not adapter_name:
            return False

        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if not adapter_config:
            return False

        from adapters.capabilities import AdapterCapabilities
        capabilities = AdapterCapabilities.from_config(adapter_config)
        return capabilities.requires_encryption

    def _select_storage_for_upload(self, requires_encryption: bool) -> FileStorageBackend:
        """
        Pick the storage backend to use for a new upload based on whether the
        adapter requires encryption. Fails loudly if encryption is required but
        files.encryption.enabled is false — a classified upload must never
        silently fall back to plaintext storage.
        """
        if not requires_encryption:
            return self.storage
        if self.encrypted_storage is None:
            raise ValueError(
                "This adapter requires encrypted file storage (capabilities.requires_encryption) "
                "but files.encryption.enabled is false. Set files.encryption.enabled: true and "
                "ORBIT_FILE_ENCRYPTION_KEY before uploading through this adapter."
            )
        return self.encrypted_storage

    def _select_storage_for_read(self, file_info: Dict[str, Any]) -> FileStorageBackend:
        """
        Pick the storage backend to use for reading back a previously-stored
        file, based on the persisted 'encrypted' flag recorded at upload time
        (not the adapter's current capability, so reads stay correct even if
        the adapter's config changes later).

        Raises:
            ValueError: If the file was stored encrypted but files.encryption
                is no longer enabled/configured. Must fail loudly rather than
                silently returning raw ciphertext through the plaintext path.
        """
        was_encrypted = bool((file_info.get('metadata') or {}).get('encrypted', False))
        if not was_encrypted:
            return self.storage
        if self.encrypted_storage is None:
            raise ValueError(
                "This file was stored with encryption enabled, but files.encryption "
                "is not currently configured (enabled: false or missing "
                "ORBIT_FILE_ENCRYPTION_KEY). Cannot decrypt this file's contents."
            )
        return self.encrypted_storage

    def _encrypt_chunk_metadata(self, chunks: List[Chunk], requires_encryption: bool) -> None:
        """
        Envelope-encrypt each chunk's metadata dict in place (mirrors
        EncryptedFileStorageBackend's sidecar envelope: {"encrypted": True,
        "payload": <hex>}), AAD-bound to the chunk's id.

        Mutates `chunks` so both downstream consumers — vector-store indexing
        (which spreads chunk.metadata into the stored metadata payload) and
        metadata_store.record_chunk (which persists chunk.metadata verbatim
        into file_chunks.chunk_metadata) — see the same ciphertext. This
        covers extracted content (image_description, image_text,
        transcribed_text) that would otherwise be duplicated in plaintext
        alongside the encrypted chunk text.

        Raises:
            ValueError: If requires_encryption but no encryptor is configured.
        """
        if not requires_encryption:
            return
        if self._file_encryptor is None:
            raise ValueError(
                "This adapter requires encrypted file storage (capabilities.requires_encryption) "
                "but files.encryption.enabled is false. Set files.encryption.enabled: true and "
                "ORBIT_FILE_ENCRYPTION_KEY before uploading through this adapter."
            )
        for chunk in chunks:
            aad = chunk.chunk_id.encode('utf-8')
            payload = self._file_encryptor.encrypt(json.dumps(chunk.metadata).encode('utf-8'), aad)
            chunk.metadata = {'encrypted': True, 'payload': payload.hex()}

    async def quick_upload(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str
    ) -> str:
        """
        Quick file upload - stores file and returns file_id immediately.
        Content processing happens in background via process_file_content.
        
        Args:
            file_data: File contents as bytes
            filename: Original filename
            mime_type: MIME type
            api_key: API key of uploader
            
        Returns:
            file_id: Unique file identifier
        """
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        # Validate file
        if not self._validate_file(file_data, mime_type):
            raise ValueError(f"Unsupported file type: {mime_type}")
        
        # Store file
        storage_key = f"{api_key}/{file_id}/{filename}"
        requires_encryption = await self._requires_encryption_for_api_key(api_key)
        metadata = {
            'filename': filename,
            'mime_type': mime_type,
            'file_size': len(file_data),
            'upload_time': datetime.now(UTC).isoformat(),
            'encrypted': requires_encryption,
        }

        storage = self._select_storage_for_upload(requires_encryption)
        await storage.put_file(file_data, storage_key, metadata)

        # Record in metadata store with status 'processing'
        await self.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=filename,
            mime_type=mime_type,
            file_size=len(file_data),
            storage_key=storage_key,
            storage_type='vector',
            metadata=metadata,
        )

        # Set status to processing
        await self.metadata_store.update_processing_status(file_id, 'processing')
        
        return file_id
    
    def _get_file_operation_lock(self, file_id: str) -> asyncio.Lock:
        """Return the lock shared by processing and deletion for a file."""
        lock = self._file_operation_locks.get(file_id)
        if lock is None:
            lock = asyncio.Lock()
            self._file_operation_locks[file_id] = lock
        return lock

    async def process_file_content(
        self,
        file_id: str,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str,
        vision_prompt: Optional[str] = None
    ) -> None:
        """
        Process file content (extraction, chunking, indexing) in background.
        Called after quick_upload for async processing.
        
        Args:
            file_id: File identifier from quick_upload
            file_data: File contents as bytes
            filename: Original filename
            mime_type: MIME type
            api_key: API key of uploader
        """
        # Timeout for the entire processing pipeline (2 minutes).
        # Prevents files from being stuck in 'processing' forever when
        # external API calls (e.g. Gemini vision) hang or fail silently.
        processing_timeout_seconds = 120

        try:
            async with asyncio.timeout(processing_timeout_seconds):
                # Extract text and metadata
                extracted_text, file_metadata = await self._extract_content(
                    file_data, filename, mime_type, api_key=api_key, vision_prompt=vision_prompt
                )

                # Chunk content
                chunks = await self._chunk_content(extracted_text, file_id, file_metadata)

                # A user can cancel while an async processor is extracting content.
                # Serialize persistence with deletion so we either observe the missing
                # file and stop, or finish atomically before deletion cleans it up.
                async with self._get_file_operation_lock(file_id):
                    # Encrypt chunk metadata if this file was stored encrypted (data-driven,
                    # not the adapter's current capability — mirrors _select_storage_for_read).
                    file_info = await self.metadata_store.get_file_info(file_id)
                    if not file_info:
                        logger.info(f"Skipping persistence for cancelled file {file_id}")
                        return

                    requires_encryption = bool(file_info.get('metadata', {}).get('encrypted', False))
                    self._encrypt_chunk_metadata(chunks, requires_encryption)

                    # Index chunks into vector store.
                    index_result = await self._index_chunks_in_vector_store(
                        file_id=file_id,
                        api_key=api_key,
                        chunks=chunks,
                        requires_encryption=requires_encryption,
                    )

                    collection_name = None
                    embedding_provider = None
                    embedding_dimensions = None
                    if index_result:
                        collection_name, embedding_provider, embedding_dimensions = index_result

                    # Record chunks in metadata store (with collection name).
                    for chunk in chunks:
                        await self.metadata_store.record_chunk(
                            chunk_id=chunk.chunk_id,
                            file_id=file_id,
                            chunk_index=chunk.chunk_index,
                            vector_store_id=chunk.chunk_id,
                            collection_name=collection_name,
                            metadata=chunk.metadata
                        )

                    await self.metadata_store.update_processing_status(
                        file_id,
                        'completed',
                        chunk_count=len(chunks),
                        collection_name=collection_name,
                        embedding_provider=embedding_provider,
                        embedding_dimensions=embedding_dimensions
                    )

            logger.debug(f"File content processed successfully: {file_id} ({len(chunks)} chunks)")

        except TimeoutError:
            error_message = f"File processing timed out after {processing_timeout_seconds}s"
            logger.error(f"Timeout processing file {file_id} ({filename}): {error_message}")

            await self.metadata_store.update_processing_status(
                file_id, 'failed', chunk_count=0
            )
            try:
                await self.metadata_store.update_file_metadata(
                    file_id,
                    {'error': error_message, 'failed_at': datetime.now(UTC).isoformat()}
                )
            except Exception as meta_error:
                logger.warning(f"Failed to store error metadata for {file_id}: {meta_error}")

        except Exception as e:
            error_message = str(e)
            logger.error(f"Error processing file content for {file_id}: {error_message}")

            # Update status to failed with error details
            await self.metadata_store.update_processing_status(
                file_id,
                'failed',
                chunk_count=0
            )

            # Store error message in file metadata for user feedback
            try:
                await self.metadata_store.update_file_metadata(
                    file_id,
                    {'error': error_message, 'failed_at': datetime.now(UTC).isoformat()}
                )
            except Exception as meta_error:
                logger.warning(f"Failed to store error metadata for {file_id}: {meta_error}")

            # Don't raise - let background task complete gracefully
            # The file is now marked as "failed" so users can see the error

    async def _extract_audio_content(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str,
        transcription_language: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        """Extract content from audio file using audio services for transcription."""
        import asyncio
        from ai_services import AIServiceFactory, ServiceType

        try:
            # Get adapter-specific STT provider (or fallback to default)
            audio_provider = await self._get_audio_provider_for_api_key(api_key)

            # Get audio service - pass config with stt_providers and tts_providers keys
            # as expected by ProviderAIService._extract_provider_config()
            try:
                live_config = self._get_live_config()
                audio_service = AIServiceFactory.create_service(
                    ServiceType.AUDIO,
                    audio_provider,
                    {
                        'stt_providers': live_config.get('stt_providers', {}),
                        'tts_providers': live_config.get('tts_providers', {})
                    }
                )
            except ValueError as e:
                # This happens when STT is globally disabled or provider is not registered
                logger.error(f"Failed to create audio service: {str(e)}")
                raise Exception("Audio transcription is not available. Please check that STT services are enabled in the configuration.")

            # Initialize if needed
            if not audio_service.initialized:
                await audio_service.initialize()

            logger.info(f"Starting audio transcription for {filename} (provider: {audio_provider})")

            # Transcribe audio to text
            try:
                transcribed_text = await audio_service.transcribe(
                    audio=file_data,
                    language=transcription_language,
                    filename=filename,
                    mime_type=mime_type
                )
            except asyncio.TimeoutError as e:
                logger.error(f"Audio transcription API timeout for {filename}: {e}")
                raise Exception("Audio transcription API request timed out. The audio file may be too large or the API is experiencing latency. Please try again or contact support if the issue persists.")
            except Exception as e:
                logger.error(f"Audio transcription API error for {filename}: {e}")
                raise Exception(f"Audio transcription failed: {str(e)}")

            logger.info(f"Audio transcription completed for {filename}")

            metadata = {
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'extraction_method': 'audio_transcription',
                'stt_provider': audio_provider,
                'transcribed_text': transcribed_text,
            }

            # Use transcribed text as the content
            text = transcribed_text

            # Validate that we got meaningful content
            if not text.strip():
                logger.warning(f"Audio service returned empty transcription for {filename}")
                raise Exception("Audio service did not transcribe any content from the audio file")

            return text, metadata

        except Exception as e:
            # Don't swallow exceptions - let them bubble up
            # This ensures files are marked as "failed" instead of "completed with 0 chunks"
            logger.error(f"Failed to process audio file {filename}: {e}")
            raise
    
    async def process_file(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str
    ) -> Dict[str, Any]:
        """
        Process an uploaded file through the complete pipeline.
        
        Args:
            file_data: File contents as bytes
            filename: Original filename
            mime_type: MIME type
            api_key: API key of uploader
            
        Returns:
            Processing result with file_id and status
        """
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        try:
            # 1. Validate file
            if not self._validate_file(file_data, mime_type):
                raise ValueError(f"Unsupported file type: {mime_type}")
            
            # 2. Store file
            storage_key = f"{api_key}/{file_id}/{filename}"
            requires_encryption = await self._requires_encryption_for_api_key(api_key)
            metadata = {
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'upload_time': datetime.now(UTC).isoformat(),
                'encrypted': requires_encryption,
            }

            storage = self._select_storage_for_upload(requires_encryption)
            await storage.put_file(file_data, storage_key, metadata)

            # 3. Record in metadata store
            await self.metadata_store.record_file_upload(
                file_id=file_id,
                api_key=api_key,
                filename=filename,
                mime_type=mime_type,
                file_size=len(file_data),
                storage_key=storage_key,
                storage_type='vector',
                metadata=metadata,
            )
            
            # 4. Update status to processing
            await self.metadata_store.update_processing_status(file_id, 'processing')

            # 5. Extract text and metadata
            extracted_text, file_metadata = await self._extract_content(
                file_data, filename, mime_type, api_key=api_key
            )

            # 6. Chunk content
            chunks = await self._chunk_content(extracted_text, file_id, file_metadata)
            self._encrypt_chunk_metadata(chunks, requires_encryption)

            # 7. Index chunks into vector store
            index_result = await self._index_chunks_in_vector_store(
                file_id=file_id,
                api_key=api_key,
                chunks=chunks,
                requires_encryption=requires_encryption,
            )

            # Extract collection info
            collection_name = None
            embedding_provider = None
            embedding_dimensions = None
            if index_result:
                collection_name, embedding_provider, embedding_dimensions = index_result

            # 8. Record chunks in metadata store (with collection name)
            for chunk in chunks:
                await self.metadata_store.record_chunk(
                    chunk_id=chunk.chunk_id,
                    file_id=file_id,
                    chunk_index=chunk.chunk_index,
                    vector_store_id=chunk.chunk_id,  # Use chunk_id as vector_store_id
                    collection_name=collection_name,
                    metadata=chunk.metadata
                )

            # 9. Update metadata store with chunk count, collection name, and provider info
            await self.metadata_store.update_processing_status(
                file_id,
                'completed',
                chunk_count=len(chunks),
                collection_name=collection_name,
                embedding_provider=embedding_provider,
                embedding_dimensions=embedding_dimensions
            )
            
            # 10. Prepare response
            return {
                'file_id': file_id,
                'status': 'completed',
                'chunk_count': len(chunks),
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'collection_name': collection_name,
                'chunks': chunks,
                'metadata': file_metadata,
            }
        
        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}")
            
            # Update status to failed
            await self.metadata_store.update_processing_status(file_id, 'failed')
            
            raise
    
    def _validate_file(self, file_data: bytes, mime_type: str) -> bool:
        """Validate file size and type."""
        # Check size
        if len(file_data) > self.max_file_size:
            raise ValueError(f"File size exceeds maximum {self.max_file_size} bytes")
        
        # Check MIME type
        if mime_type not in self.supported_types:
            return False
        
        # Special handling for image and audio files (handled by vision/audio services, not processors)
        if mime_type.startswith('image/') or mime_type.startswith('audio/'):
            return True
        
        # Check if processor exists for other file types
        processor = self.processor_registry.get_processor(mime_type)
        return processor is not None
    
    async def _extract_content(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str,
        vision_prompt: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        """Extract text and metadata from file."""
        # Check if this is an image file. When the AI OCR processor is the active
        # priority processor, let images fall through to it (via the registry)
        # instead of the generic vision path.
        if self.enable_vision and mime_type.startswith('image/') and not self._ai_ocr_is_priority():
            return await self._extract_image_content(
                file_data, filename, mime_type, api_key=api_key, vision_prompt=vision_prompt
            )

        # Check if this is an audio file
        if self.enable_audio and mime_type.startswith('audio/'):
            return await self._extract_audio_content(
                file_data, filename, mime_type, api_key=api_key
            )

        processors = self.processor_registry.get_processors(mime_type)

        if not processors:
            raise ValueError(f"No processor available for MIME type: {mime_type}")

        # Try each processor in priority order, falling back on failure
        last_error = None
        for processor in processors:
            processor_name = processor.__class__.__name__
            try:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Processing file '{filename}' (MIME: {mime_type}) with {processor_name}")

                text = await processor.extract_text(file_data, filename)
                metadata = await processor.extract_metadata(file_data, filename)

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Extraction complete for '{filename}': {len(text)} chars extracted by {processor_name}")

                return text, metadata
            except Exception as e:
                last_error = e
                if len(processors) > 1:
                    logger.warning(f"{processor_name} failed for '{filename}', trying next processor: {e}")
                else:
                    raise

        raise last_error
    
    async def _extract_image_content(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str,
        vision_prompt: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        """Extract content from image using vision services."""
        import asyncio

        try:
            # Get adapter-specific vision provider (or fallback to default)
            vision_provider = await self._get_vision_provider_for_api_key(api_key)

            # Resolve the vision service through the adapter manager's managed
            # VisionCacheManager. That cache is keyed/invalidated on adapter reload
            # and always built from live config, so provider/model changes take
            # effect without a server restart. Fall back to a direct factory call
            # with live config when the adapter manager is unavailable (e.g. tests).
            vision_service = await self._create_vision_service(vision_provider)

            # Initialize if needed
            if not vision_service.initialized:
                await vision_service.initialize()

            # PERFORMANCE FIX: Make both API calls concurrently instead of sequentially
            # This reduces total processing time from ~120s to ~60s
            logger.info(f"Starting vision processing for {filename} (provider: {vision_provider})")

            # Use custom prompt if provided, otherwise use default describe_image
            try:
                if vision_prompt:
                    logger.info(f"Using custom prompt for vision analysis: {vision_prompt[:50]}...")
                    # Use analyze_image with custom prompt instead of describe_image
                    extracted_text, description = await asyncio.gather(
                        vision_service.extract_text_from_image(file_data),
                        vision_service.analyze_image(file_data, prompt=vision_prompt)
                    )
                else:
                    extracted_text, description = await asyncio.gather(
                        vision_service.extract_text_from_image(file_data),
                        vision_service.describe_image(file_data)
                    )
            except asyncio.TimeoutError as e:
                logger.error(f"Vision API timeout for {filename}: {e}")
                raise Exception("Vision API request timed out. The image may be too large or the API is experiencing latency. Please try again or contact support if the issue persists.")
            except Exception as e:
                logger.error(f"Vision API error for {filename}: {e}")
                raise Exception(f"Vision processing failed: {str(e)}")

            logger.info(f"Vision processing completed for {filename}")

            metadata = {
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'extraction_method': 'vision',
                'vision_provider': vision_provider,
                'image_description': description,
                'image_text': extracted_text,
            }

            # Combine description and extracted text
            text = f"Image Description:\n{description}\n\nExtracted Text:\n{extracted_text}"

            # Validate that we got meaningful content
            if not text.strip() or (not description and not extracted_text):
                logger.warning(f"Vision service returned empty content for {filename}")
                raise Exception("Vision service did not extract any content from the image")

            return text, metadata

        except Exception as e:
            # PRODUCTION FIX: Don't swallow exceptions - let them bubble up
            # This ensures files are marked as "failed" instead of "completed with 0 chunks"
            logger.error(f"Failed to process image {filename}: {e}")
            raise
    
    async def _chunk_content(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk text content using the configured chunking strategy.
        
        Args:
            text: Text to chunk
            file_id: File identifier
            metadata: File metadata
            
        Returns:
            List of Chunk objects
        """
        if logger.isEnabledFor(logging.DEBUG):
            strategy_name = self.chunker.__class__.__name__
            logger.debug(f"Chunking content for file {file_id} using strategy: {strategy_name}")
            logger.debug(f"  Text length: {len(text)} characters")

        chunks = self.chunker.chunk_text(text, file_id, metadata)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"  Created {len(chunks)} chunks from file {file_id}")
            if chunks:
                avg_chunk_size = sum(len(c.text) for c in chunks) / len(chunks)
                logger.debug(f"  Average chunk size: {avg_chunk_size:.0f} characters")
        
        return chunks
    
    async def _get_adapter_config_for_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Get the adapter configuration for a given API key.

        This enables adapter-specific provider overrides (e.g., adapter A uses OpenAI, adapter B uses Ollama).

        Args:
            api_key: The API key to lookup

        Returns:
            Dict containing adapter config merged with global config, or just global config as fallback
        """
        fallback_reason = None

        try:
            # Try to get adapter manager from app state
            # Note: The adapter manager is stored as 'adapter_manager' in app.state (set by service_factory.py)
            if not self.app_state:
                fallback_reason = "app_state not available"
            elif not hasattr(self.app_state, 'adapter_manager'):
                fallback_reason = "adapter_manager not in app_state"
            else:
                adapter_manager = self.app_state.adapter_manager

                # Get API key service to lookup which adapter this API key uses
                if not hasattr(self.app_state, 'api_key_service'):
                    fallback_reason = "api_key_service not in app_state"
                else:
                    api_key_service = self.app_state.api_key_service

                    # Get adapter name for this API key (pass adapter_manager to check live configs)
                    adapter_name, _ = await api_key_service.get_adapter_for_api_key(api_key, adapter_manager)

                    if not adapter_name:
                        fallback_reason = f"no adapter found for api_key {api_key[:8]}..."
                    else:
                        # Get adapter config from adapter manager
                        adapter_config = adapter_manager.get_adapter_config(adapter_name)

                        if not adapter_config:
                            fallback_reason = f"adapter '{adapter_name}' has no config"
                        else:
                            logger.debug(f"Using adapter-specific config for adapter '{adapter_name}' (api_key: {api_key[:8]}...)")

                            # Merge adapter config with global config using deep copy to avoid modifying global config
                            import copy
                            merged_config = copy.deepcopy(self.config)

                            # Override embedding provider if specified in adapter
                            if 'embedding_provider' in adapter_config:
                                if 'embedding' not in merged_config:
                                    merged_config['embedding'] = {}
                                merged_config['embedding']['provider'] = adapter_config['embedding_provider']
                                logger.debug(f"Using adapter embedding provider: {adapter_config['embedding_provider']}")
                            else:
                                # Log what embedding provider will be used
                                default_provider = merged_config.get('embedding', {}).get('provider', 'ollama')
                                logger.debug(f"Adapter '{adapter_name}' has no embedding_provider override, using default: {default_provider}")

                            # Override embedding model if specified in adapter
                            if 'embedding_model' in adapter_config:
                                embedding_provider = adapter_config.get('embedding_provider') or merged_config.get('embedding', {}).get('provider', 'ollama')
                                if 'embeddings' not in merged_config:
                                    merged_config['embeddings'] = {}
                                if embedding_provider not in merged_config['embeddings']:
                                    merged_config['embeddings'][embedding_provider] = {}
                                merged_config['embeddings'][embedding_provider]['model'] = adapter_config['embedding_model']
                                logger.debug(f"Using adapter embedding model: {adapter_config['embedding_model']} (provider: {embedding_provider})")

                            # Pass adapter-specific config to retriever
                            merged_config['adapter_config'] = adapter_config.get('config', {})

                            return merged_config

        except Exception as e:
            fallback_reason = f"exception: {e}"
            logger.warning(f"Could not lookup adapter-specific config for API key: {e}")

        # Fall back to global config - LOG WARNING so users know the embedding provider might not match
        global_embedding_provider = self.config.get('embedding', {}).get('provider', 'ollama')
        logger.warning(f"FileProcessingService: Falling back to global config for api_key {api_key[:8]}... "
                      f"(reason: {fallback_reason}). Embedding provider will be: {global_embedding_provider}. "
                      f"If adapter specifies a different embedding_provider, there may be a mismatch!")
        return self.config

    async def _index_chunks_in_vector_store(
        self,
        file_id: str,
        api_key: str,
        chunks: List[Chunk],
        requires_encryption: bool = False
    ) -> Optional[tuple]:
        """
        Index chunks into vector store with provider-aware collection naming.

        Args:
            file_id: File identifier
            api_key: API key
            chunks: List of chunks to index
            requires_encryption: If True, chunk text is encrypted (AES-256-GCM,
                AAD-bound to chunk_id) before being stored as the vector
                store's document/content field. Embeddings are always
                computed from the original plaintext beforehand.

        Returns:
            Tuple of (collection_name, embedding_provider, embedding_dimensions) if successful, None otherwise
        """
        if not chunks:
            return None

        try:
            from services.retriever_cache import get_retriever_cache

            # Get adapter-specific config for this API key (includes embedding provider override)
            adapter_aware_config = await self._get_adapter_config_for_api_key(api_key)

            # Get or create cached file retriever with adapter-aware config
            retriever_cache = get_retriever_cache()
            retriever = await retriever_cache.get_retriever(adapter_aware_config)

            # Get embedding provider info for collection naming (now uses adapter-specific provider)
            embedding_provider = adapter_aware_config.get('embedding', {}).get('provider', 'ollama')

            # Get embedding dimensions
            try:
                if retriever.embeddings and hasattr(retriever.embeddings, 'get_dimensions'):
                    embedding_dimensions = await retriever.embeddings.get_dimensions()
                else:
                    # Fallback: try to get dimensions by embedding a test query
                    test_embedding = await retriever.embed_query("test")
                    embedding_dimensions = len(test_embedding)
            except Exception as e:
                logger.warning(f"Could not determine embedding dimensions: {e}. Using default 768")
                embedding_dimensions = 768

            # Generate collection name with provider and dimensions
            collection_prefix = adapter_aware_config.get('collection_prefix', 'files_')

            # Hash API key with salt for collection naming (don't expose raw key)
            salted_key = f"orbit_collection_{api_key}"
            api_key_hash = hashlib.sha256(salted_key.encode()).hexdigest()[:16]

            # Format: files_{provider}_{dimensions}_{apikey_hash}
            collection_name = f"{collection_prefix}{embedding_provider}_{embedding_dimensions}_{api_key_hash}"

            logger.debug(f"Creating collection with provider-aware naming: {collection_name}")

            # Index chunks
            success = await retriever.index_file_chunks(
                file_id=file_id,
                chunks=chunks,
                collection_name=collection_name,
                encryptor=self._file_encryptor if requires_encryption else None,
            )

            if success:
                logger.debug(f"Indexed {len(chunks)} chunks into collection {collection_name}")
                return (collection_name, embedding_provider, embedding_dimensions)
            else:
                logger.warning(f"Failed to index chunks for file {file_id}")
                return None

        except Exception as e:
            logger.error(f"Error indexing chunks into vector store: {e}")
            # Don't fail the upload if indexing fails
            return None
    
    async def get_file(self, file_id: str, api_key: str) -> bytes:
        """Retrieve file contents."""
        file_info = await self.metadata_store.get_file_info(file_id)
        
        if not file_info:
            raise FileNotFoundError(f"File not found: {file_id}")
        
        if file_info['api_key'] != api_key:
            raise PermissionError("Access denied")
        
        storage_key = file_info['storage_key']
        storage = self._select_storage_for_read(file_info)
        return await storage.get_file(storage_key)
    
    async def delete_file(self, file_id: str, api_key: str) -> bool:
        """Delete a file without racing its background processor."""
        async with self._get_file_operation_lock(file_id):
            return await self._delete_file_locked(file_id, api_key)

    async def _delete_file_locked(self, file_id: str, api_key: str) -> bool:
        """Delete file and all associated chunks from vector store, storage, and metadata store."""
        file_info = await self.metadata_store.get_file_info(file_id)
        
        if not file_info:
            return False
        
        if file_info['api_key'] != api_key:
            raise PermissionError("Access denied")
        
        # 1. Delete chunks from vector store and metadata store
        chunks_already_deleted = await self._delete_file_chunks(file_id, api_key)

        # 2. Delete file from storage (filesystem)
        try:
            storage_key = file_info['storage_key']
            await self.storage.delete_file(storage_key)
            logger.debug(f"Deleted file from storage: {storage_key}")
        except Exception as e:
            logger.error(f"Error deleting file from storage {storage_key}: {e}")
            # Continue even if storage deletion fails

        # 3. Delete from metadata store (skip chunk deletion if already done)
        metadata_deleted = await self.metadata_store.delete_file(file_id, skip_chunks=chunks_already_deleted)

        if metadata_deleted:
            logger.debug(f"Successfully deleted file {file_id} and all associated data")
        else:
            logger.error(f"Failed to delete file {file_id} from metadata store")
        
        return metadata_deleted
    
    async def _delete_file_chunks(self, file_id: str, api_key: str) -> bool:
        """
        Delete a file's chunks from the vector store and metadata store.

        Returns True if the chunks were successfully removed, False otherwise.
        Failures are logged but not raised so callers can continue.
        """
        try:
            # Get adapter-specific config for this API key (includes embedding provider override)
            adapter_aware_config = await self._get_adapter_config_for_api_key(api_key)

            # Get or create cached file retriever with adapter-aware config to delete chunks from vector store
            from services.retriever_cache import get_retriever_cache
            retriever_cache = get_retriever_cache()
            retriever = await retriever_cache.get_retriever(adapter_aware_config)

            # Delete chunks from both vector store and metadata store
            chunks_deleted = await retriever.delete_file_chunks(file_id)
            if not chunks_deleted:
                logger.warning(f"Failed to delete chunks for file {file_id}")
            return bool(chunks_deleted)
        except Exception as e:
            logger.error(f"Error deleting chunks from vector store for file {file_id}: {e}")
            return False

    async def reprocess_file(
        self,
        file_id: str,
        api_key: str,
        vision_prompt: Optional[str] = None
    ) -> None:
        """
        Re-extract and re-index an already-uploaded file using the currently
        configured providers.

        Vision (for images) and STT (for audio) run only at processing time and
        the result is persisted as chunks. After changing an adapter's
        ``vision_provider``/``stt_provider`` (and reloading), call this to refresh
        an existing file's extraction without requiring the user to re-upload.

        The original bytes are reloaded from storage, the previously-extracted
        chunks are removed, and the standard processing pipeline is re-run. Provider
        resolution inside the pipeline happens live, so the current provider is used.

        Args:
            file_id: Identifier of the file to re-process
            api_key: API key that owns the file (ownership is enforced)
            vision_prompt: Optional custom prompt for image analysis. Not persisted
                from the original upload, so defaults to None (standard description).

        Raises:
            FileNotFoundError: If the file does not exist
            PermissionError: If the API key does not own the file
        """
        file_info = await self.metadata_store.get_file_info(file_id)
        if not file_info:
            raise FileNotFoundError(f"File not found: {file_id}")
        if file_info['api_key'] != api_key:
            raise PermissionError("Access denied")

        filename = file_info['filename']
        mime_type = file_info['mime_type']
        storage_key = file_info['storage_key']

        logger.info(f"Re-processing file {file_id} ({filename}, {mime_type})")

        # Reload the original bytes from storage
        storage = self._select_storage_for_read(file_info)
        file_data = await storage.get_file(storage_key)

        # Remove previously-extracted chunks so re-processing does not duplicate them
        await self._delete_file_chunks(file_id, api_key)

        # Reset status and re-run extraction/chunking/indexing with live providers
        await self.metadata_store.update_processing_status(file_id, 'processing', chunk_count=0)
        await self.process_file_content(
            file_id=file_id,
            file_data=file_data,
            filename=filename,
            mime_type=mime_type,
            api_key=api_key,
            vision_prompt=vision_prompt,
        )

    async def list_files(self, api_key: str) -> List[Dict[str, Any]]:
        """List all files for an API key."""
        return await self.metadata_store.list_files(api_key)

    async def get_generated_file_ids_for_session(self, session_id: str, api_key: str) -> List[str]:
        """Return IDs of all server-persisted generated images for a conversation session."""
        return await self.metadata_store.get_generated_file_ids_for_session(session_id, api_key)
