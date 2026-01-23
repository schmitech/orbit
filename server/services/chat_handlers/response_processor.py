"""
Response Processor

Handles post-processing of chat responses including text formatting,
warning injection, conversation storage, and logging.
"""

import logging
import re
from typing import Dict, Any, Optional

from utils.text_utils import fix_text_formatting, mask_api_key
from .conversation_history_handler import ConversationHistoryHandler

logger = logging.getLogger(__name__)


class ResponseProcessor:
    """Handles post-processing of chat responses."""

    def __init__(
        self,
        config: Dict[str, Any],
        conversation_handler: ConversationHistoryHandler,
        logger_service,
        audit_service=None
    ):
        """
        Initialize the response processor.

        Args:
            config: Application configuration
            conversation_handler: Conversation history handler
            logger_service: Logger service for conversation logging (Elasticsearch)
            audit_service: Optional audit service for audit trail storage (SQLite/MongoDB/ES)
        """
        self.config = config
        self.conversation_handler = conversation_handler
        self.logger_service = logger_service
        self.audit_service = audit_service

    def format_response(self, text: str) -> str:
        """
        Apply text formatting to clean up response.

        Args:
            text: Raw response text

        Returns:
            Formatted text
        """
        return fix_text_formatting(text)

    def inject_warning(self, response: str, warning: Optional[str]) -> str:
        """
        Inject warning message into response if provided.

        Args:
            response: Original response text
            warning: Optional warning message

        Returns:
            Response with warning appended if provided
        """
        if warning:
            return f"{response}\n\n---\n{warning}"
        return response

    async def log_request_details(
        self,
        message: str,
        client_ip: str,
        adapter_name: str,
        system_prompt_id: Optional[str],
        api_key: Optional[str],
        session_id: Optional[str],
        user_id: Optional[str]
    ) -> None:
        """
        Log detailed request information for debugging.

        Args:
            message: The chat message
            client_ip: Client IP address
            adapter_name: Adapter name being used
            system_prompt_id: System prompt ID
            api_key: API key (will be masked)
            session_id: Session identifier
            user_id: User identifier
        """
        logger.debug(f"Processing chat message from {client_ip}, adapter: {adapter_name}")
        logger.debug(f"Message: {message}")

        # Mask API key for logging
        masked_api_key = "None"
        if api_key:
            masked_api_key = mask_api_key(api_key, show_last=True)

        logger.debug(f"System prompt ID: {system_prompt_id}")
        logger.debug(f"API key: {masked_api_key}")
        logger.debug(f"Session ID: {session_id}")
        logger.debug(f"User ID: {user_id}")

    async def log_conversation(
        self,
        query: str,
        response: str,
        client_ip: str,
        backend: str,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        adapter_name: Optional[str] = None
    ) -> None:
        """
        Log conversation asynchronously.

        Args:
            query: User query
            response: Assistant response
            client_ip: Client IP address
            backend: Backend/provider used
            api_key: Optional API key
            session_id: Optional session ID
            user_id: Optional user ID
            adapter_name: Optional adapter name used for this request
        """
        # Log metadata to Elasticsearch via LoggerService (query/response excluded - handled by audit)
        try:
            await self.logger_service.log_conversation(
                query=query,
                response=response,
                ip=client_ip,
                backend=backend,
                blocked=False,
                api_key=api_key,
                session_id=session_id,
                user_id=user_id
            )
        except Exception as e:
            logger.error(f"Error logging conversation to LoggerService: {str(e)}", exc_info=True)

        # Log full conversation to AuditService (SQLite/MongoDB/Elasticsearch based on config)
        if self.audit_service:
            try:
                await self.audit_service.log_conversation(
                    query=query,
                    response=response,
                    ip=client_ip,
                    backend=backend,
                    blocked=False,
                    api_key=api_key,
                    session_id=session_id,
                    user_id=user_id,
                    adapter_name=adapter_name
                )
            except Exception as e:
                logger.error(f"Error logging conversation to AuditService: {str(e)}", exc_info=True)

    async def process_response(
        self,
        response: str,
        message: str,
        client_ip: str,
        adapter_name: str,
        session_id: Optional[str],
        user_id: Optional[str],
        api_key: Optional[str],
        backend: str,
        processing_time: float,
        retrieved_docs: Optional[list] = None
    ) -> tuple[str, Optional[str]]:
        """
        Complete post-processing of a chat response.

        This includes:
        - Text formatting
        - Warning injection (if approaching conversation limit)
        - Conversation storage
        - Logging

        Args:
            response: Raw response text
            message: Original user message
            client_ip: Client IP address
            adapter_name: Adapter being used
            session_id: Session identifier
            user_id: User identifier
            api_key: API key
            backend: Backend/provider used
            processing_time: Pipeline processing time

        Returns:
            Tuple of (processed_response_text, assistant_message_id)
        """
        # Clean response text
        processed_response = self.format_response(response)

        # Check for conversation limit warning
        warning = await self.conversation_handler.check_limit_warning(session_id, adapter_name)
        processed_response = self.inject_warning(processed_response, warning)

        # Store conversation turn with retrieved_docs in metadata
        # Always store for threading support, even if chat history is disabled for context retrieval
        assistant_message_id = None
        if session_id:
            # Build metadata with retrieved_docs for thread creation
            metadata = {
                "adapter_name": adapter_name,
                "client_ip": client_ip,
                "pipeline_processing_time": processing_time,
                "original_query": message
            }
            
            # Include retrieved_docs if available (for thread creation)
            if retrieved_docs:
                metadata["retrieved_docs"] = retrieved_docs
                # Extract template_id and parameters from first doc if available
                if retrieved_docs and len(retrieved_docs) > 0:
                    first_doc_meta = retrieved_docs[0].get('metadata', {})
                    if first_doc_meta:
                        metadata["template_id"] = first_doc_meta.get('template_id')
                        metadata["parameters_used"] = first_doc_meta.get('parameters_used', {})
            
            # Store turn - this will store metadata even if chat history context is disabled
            # The store_turn method checks should_enable for context retrieval, but we need metadata for threading
            _, assistant_message_id = await self.conversation_handler.store_turn(
                session_id=session_id,
                user_message=message,
                assistant_response=processed_response,
                adapter_name=adapter_name,
                user_id=user_id,
                api_key=api_key,
                metadata=metadata
            )

        # Log conversation
        await self.log_conversation(
            query=message,
            response=processed_response,
            client_ip=client_ip,
            backend=backend,
            api_key=api_key,
            session_id=session_id,
            user_id=user_id,
            adapter_name=adapter_name
        )

        return processed_response, assistant_message_id

    def build_result(
        self,
        response: str,
        sources: list,
        metadata: Dict[str, Any],
        processing_time: float,
        audio_data: Optional[bytes] = None,
        audio_format: Optional[str] = None,
        assistant_message_id: Optional[str] = None,
        session_id: Optional[str] = None,
        adapter_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build the final result dictionary.

        Args:
            response: Processed response text
            sources: Source documents
            metadata: Additional metadata
            processing_time: Pipeline processing time
            audio_data: Optional audio data
            audio_format: Optional audio format
            assistant_message_id: Optional assistant message ID for threading
            session_id: Optional session ID for threading
            adapter_name: Optional adapter name for threading support detection

        Returns:
            Complete result dictionary
        """
        import base64

        result = {
            "response": response,
            "sources": sources,
            "metadata": {
                **metadata,
                "processing_time": processing_time,
                "pipeline_used": True
            }
        }

        # Add threading metadata if adapter supports it and has meaningful results
        # Only enable threading when there are actual sources/results to thread on
        # Filter out zero-confidence placeholder documents (e.g., "no matching templates found")
        if assistant_message_id and session_id and adapter_name:
            supports_threading = self._adapter_supports_threading(adapter_name)

            # Check for meaningful results using multiple signals
            has_results = self._has_meaningful_results(sources, response)

            if supports_threading and has_results:
                result["threading"] = {
                    "supports_threading": True,
                    "message_id": assistant_message_id,
                    "session_id": session_id
                }

        # Add audio if generated
        if audio_data:
            result["audio"] = base64.b64encode(audio_data).decode('utf-8')
            result["audio_format"] = audio_format or "mp3"

        return result
    
    def _adapter_supports_threading(self, adapter_name: str) -> bool:
        """
        Check if an adapter supports threading.

        Reads the `capabilities.supports_threading` setting from the adapter configuration.
        Falls back to name-based inference if capability is not explicitly set.

        Args:
            adapter_name: Name of the adapter

        Returns:
            True if adapter supports threading based on config or name inference
        """
        if not adapter_name:
            return False

        # Look up adapter configuration to check explicit capability setting
        adapters = self.config.get('adapters', [])
        adapter_config = None
        for adapter in adapters:
            if isinstance(adapter, dict) and adapter.get('name') == adapter_name:
                adapter_config = adapter
                break

        # If adapter config found, check explicit capability setting
        if adapter_config:
            capabilities = adapter_config.get('capabilities', {})
            if 'supports_threading' in capabilities:
                return bool(capabilities.get('supports_threading'))

        # Fall back to name-based inference if capability not explicitly set
        # Intent adapters support threading by default
        if adapter_name.startswith('intent-'):
            return True

        # QA adapters do NOT support threading by default (simple Q&A)
        if adapter_name.startswith('qa-') or 'qa' in adapter_name.lower():
            return False

        # Conversational and multimodal adapters do not support threading
        if 'conversational' in adapter_name.lower() or 'multimodal' in adapter_name.lower():
            return False

        return False

    def _has_meaningful_results(self, sources: list, response: str) -> bool:
        """
        Determine if there are meaningful results to enable threading.

        Uses multiple signals with priority:
        1. LLM response analysis (PRIMARY - if LLM says "no results", trust it)
        2. Confidence/similarity scores (filter out placeholders)
        3. Source content analysis (detect empty data like "0", "N/A")

        Args:
            sources: List of source documents from retrieval
            response: The LLM response text

        Returns:
            True if there are meaningful results worth threading on
        """
        # Signal 1 (PRIMARY): Check if LLM response indicates no results found
        # This is the most reliable signal - if the LLM says it couldn't find results,
        # we trust that determination even if the retriever returned confident matches
        # (which could be false-positive matches due to low confidence thresholds)
        if self._response_indicates_no_results(response):
            logger.debug("Threading disabled: LLM response indicates no results")
            return False

        # Signal 2: Check for sources with valid confidence scores
        has_confident_sources = False
        if sources and len(sources) > 0:
            meaningful_sources = [
                src for src in sources
                if (src.get('confidence', 0) > 0.01 or
                    src.get('metadata', {}).get('similarity', 0) > 0.01)
            ]
            has_confident_sources = len(meaningful_sources) > 0

        if not has_confident_sources:
            logger.debug("Threading disabled: no confident sources")
            return False

        # Signal 3: Check if sources contain actual data (not just empty/zero values)
        if not self._sources_contain_actual_data(sources):
            logger.debug("Threading disabled: sources contain no actual data")
            return False

        logger.debug("Threading enabled: has meaningful results")
        return True

    def _response_indicates_no_results(self, response: str) -> bool:
        """
        Check if the response text indicates no results were found.

        This is the PRIMARY signal for determining if threading should be disabled.
        If the LLM explicitly says it couldn't find results, we trust that determination
        regardless of what the retriever returned (which may be false-positive matches).

        Supports multilingual detection for: English, French, Spanish, German,
        Italian, Portuguese, and Dutch.

        Args:
            response: The LLM response text

        Returns:
            True if response indicates no results
        """
        if not response:
            return True

        response_lower = response.lower()
        response_stripped = response_lower.strip()

        # Heuristic 1: Short responses with apologetic/negative tone are likely "no results"
        # A genuine data response is typically longer than 100 chars
        is_short_response = len(response_stripped) < 150

        # Multilingual keywords that strongly indicate "no results"
        negative_indicators = [
            # English
            'sorry', 'couldn\'t', 'could not', 'couldnt', 'cannot', 'can\'t',
            'unable', 'no results', 'no data', 'not found', 'don\'t have',
            'do not have', 'doesn\'t', 'does not', 'wasn\'t', 'weren\'t',
            'try a different', 'try another', 'rephrase', 'no matching',
            'no information', 'unfortunately', 'apologize', 'outside',
            'beyond', 'not available', 'unavailable',

            # French
            'désolé', 'desole', 'je n\'ai pas', 'pas trouvé', 'pas trouve',
            'aucun résultat', 'aucun resultat', 'pas de résultat', 'pas de resultat',
            'impossible de trouver', 'malheureusement', 'je ne peux pas',
            'pas d\'information', 'essayez une autre', 'reformulez',

            # Spanish
            'lo siento', 'disculpa', 'no encontré', 'no encontre', 'no pude',
            'sin resultados', 'no hay resultados', 'no hay datos',
            'no se encontró', 'no se encontro', 'lamentablemente',
            'intente otra', 'pruebe con otra', 'no disponible',

            # German
            'entschuldigung', 'leider', 'keine ergebnisse', 'nicht gefunden',
            'konnte nicht finden', 'keine daten', 'nicht verfügbar',
            'versuchen sie', 'keine informationen',

            # Italian
            'mi dispiace', 'spiacente', 'nessun risultato', 'non trovato',
            'non ho trovato', 'purtroppo', 'nessuna informazione',
            'prova con', 'non disponibile',

            # Portuguese
            'desculpe', 'sinto muito', 'não encontrei', 'nao encontrei',
            'sem resultados', 'nenhum resultado', 'não disponível',
            'infelizmente', 'tente outra',

            # Dutch
            'helaas', 'geen resultaten', 'niet gevonden',
            'kon niet vinden', 'geen gegevens', 'probeer een andere',
        ]

        # Count negative indicators
        negative_count = sum(1 for indicator in negative_indicators if indicator in response_lower)

        # If short response with 2+ negative indicators, very likely "no results"
        if is_short_response and negative_count >= 2:
            logger.debug(f"Threading disabled: short response ({len(response_stripped)} chars) with {negative_count} negative indicators")
            return True

        # Heuristic 2: Explicit "no results" patterns (regex-based, multilingual)
        no_results_patterns = [
            # === ENGLISH ===
            r"couldn'?t find",
            r"could not find",
            r"didn'?t find",
            r"did not find",
            r"unable to find",
            r"failed to find",
            r"no results?",
            r"no matching",
            r"no data",
            r"no records?",
            r"no information",
            r"zero results?",
            r"0 results?",
            r"not found",
            r"wasn'?t found",
            r"were not found",
            r"weren'?t found",
            r"sorry.{0,50}(couldn'?t|could not|no |unable|don'?t)",
            r"unfortunately.{0,50}(no |couldn'?t|unable)",
            r"apologize.{0,50}(couldn'?t|could not|no |unable)",
            r"try (a |another )?(different|new|another)",
            r"rephrase",
            r"please try",
            r"i (don'?t|do not) have (any )?(information|data|results?)",
            r"(don'?t|doesn'?t|do not|does not) (have|contain|include)",
            r"(outside|beyond|not within) (my|the) (scope|knowledge|data)",
            r"not (available|accessible)",
            r"(query|search|request) (returned|yielded|produced) (no|zero|0)",
            r"(database|system|search) (has |contains? )?(no|zero)",

            # === FRENCH ===
            r"d[ée]sol[ée].{0,30}(pas|aucun|impossible)",
            r"je n['']?ai (pas |rien )?trouv[ée]",
            r"aucun(e)? r[ée]sultat",
            r"pas de r[ée]sultat",
            r"pas d['']?information",
            r"impossible de (trouver|localiser)",
            r"malheureusement.{0,30}(pas|aucun|impossible)",
            r"essayez (une autre|diff[ée]rent)",
            r"reformulez",
            r"je ne (peux|suis) pas",

            # === SPANISH ===
            r"lo siento.{0,30}(no |sin |imposible)",
            r"no (encontr[ée]|pude|hay)",
            r"sin resultados?",
            r"no hay (resultados?|datos|informaci[oó]n)",
            r"lamentablemente.{0,30}(no |sin )",
            r"intente (otra|con otra|de nuevo)",
            r"pruebe (con otra|de nuevo)",
            r"no (disponible|accesible)",
            r"disculpa.{0,30}(no |sin )",

            # === GERMAN ===
            r"entschuldigung.{0,30}(keine|nicht|leider)",
            r"leider.{0,30}(keine|nicht|konnte)",
            r"keine (ergebnisse|daten|informationen)",
            r"nicht gefunden",
            r"konnte.{0,20}nicht (finden|lokalisieren)",
            r"versuchen sie.{0,20}(andere|neu)",
            r"nicht verf[üu]gbar",

            # === ITALIAN ===
            r"mi dispiace.{0,30}(non|nessun)",
            r"spiacente.{0,30}(non|nessun)",
            r"nessun(a|o)? (risultat[oi]|dat[oi]|informazion[ei])",
            r"non (ho trovato|trovato|disponibile)",
            r"purtroppo.{0,30}(non|nessun)",
            r"prova con.{0,20}(altra|altro|diversa)",

            # === PORTUGUESE ===
            r"desculpe.{0,30}(n[ãa]o|sem|nenhum)",
            r"sinto muito.{0,30}(n[ãa]o|sem)",
            r"n[ãa]o (encontrei|h[áa]|existe)",
            r"sem resultados?",
            r"nenhum(a)? (resultado|dado|informa[çc][ãa]o)",
            r"infelizmente.{0,30}(n[ãa]o|sem)",
            r"tente (outra|novamente|de novo)",
            r"n[ãa]o dispon[ií]vel",

            # === DUTCH ===
            r"helaas.{0,30}(geen|niet|kon)",
            r"geen (resultaten|gegevens|informatie)",
            r"niet gevonden",
            r"kon.{0,20}niet vinden",
            r"probeer (een andere|opnieuw)",
            r"niet beschikbaar",
        ]

        for pattern in no_results_patterns:
            if re.search(pattern, response_lower):
                logger.debug(f"Threading disabled: matched pattern '{pattern}'")
                return True

        # Heuristic 3: Response starts with apologetic words (multilingual)
        apologetic_starters = [
            # English
            'sorry', 'i\'m sorry', 'unfortunately', 'i apologize',
            'i couldn\'t', 'i could not', 'i don\'t', 'i do not',
            'i wasn\'t able', 'i was unable', 'no,', 'no results',
            # French
            'désolé', 'desole', 'je suis désolé', 'malheureusement',
            'je n\'ai pas', 'aucun résultat', 'aucun resultat',
            # Spanish
            'lo siento', 'disculpa', 'lamentablemente', 'no encontré',
            'sin resultados', 'no hay',
            # German
            'entschuldigung', 'leider', 'es tut mir leid', 'keine ergebnisse',
            # Italian
            'mi dispiace', 'spiacente', 'purtroppo', 'nessun risultato',
            # Portuguese
            'desculpe', 'sinto muito', 'infelizmente', 'não encontrei',
            'nao encontrei',
            # Dutch
            'helaas', 'geen resultaten',
        ]

        for starter in apologetic_starters:
            if response_stripped.startswith(starter):
                # Additional check: if starts apologetically and is relatively short
                if len(response_stripped) < 300:
                    logger.debug(f"Threading disabled: apologetic start '{starter}' with short response")
                    return True

        return False

    def _sources_contain_actual_data(self, sources: list) -> bool:
        """
        Check if sources contain actual meaningful data.

        Detects empty result indicators like:
        - "Total: 0", "Count: 0"
        - All values being "N/A", "None", "null"
        - Empty content fields

        Args:
            sources: List of source documents

        Returns:
            True if sources contain actual data
        """
        if not sources:
            return False

        for source in sources:
            content = source.get('content', '') or source.get('text', '') or ''
            metadata = source.get('metadata', {}) or {}

            # Check for explicit empty result flags from retrievers
            if metadata.get('empty_results') or metadata.get('no_data'):
                continue

            # Check row_count if available (from SQL/DB retrievers)
            row_count = metadata.get('row_count') or metadata.get('result_count')
            if row_count is not None and int(row_count) == 0:
                continue

            # Check if content indicates zero results
            if self._content_indicates_empty(content):
                continue

            # This source appears to have actual data
            return True

        # All sources were empty or indicated no data
        return False

    def _content_indicates_empty(self, content: str) -> bool:
        """
        Check if content text indicates empty/zero results.

        Args:
            content: The content text to analyze

        Returns:
            True if content indicates empty results
        """
        if not content or not content.strip():
            return True

        content_lower = content.lower().strip()

        # Check for summary tables with all zeros/N/A
        # Supports multiple formats:
        # - "Total X: 0" or "Total X: N/A" style
        # - "| Total X | 0 |" markdown table style
        # - "Total X    0" tab-separated style
        total_patterns = [
            # Colon-separated: "Total trips: 0"
            r'total[^:\|]*:\s*(0|n/?a|none|null|\-)',
            r'count[^:\|]*:\s*(0|n/?a|none|null|\-)',
            r'sum[^:\|]*:\s*(0|n/?a|none|null|\-)',
            # Markdown table: "| Total trips | 0 |"
            r'\|\s*total[^|]*\|\s*(0|n/?a|none|null|\-)\s*\|',
            r'\|\s*count[^|]*\|\s*(0|n/?a|none|null|\-)\s*\|',
            r'\|\s*sum[^|]*\|\s*(0|n/?a|none|null|\-)\s*\|',
            # Tab/space separated: "Total trips    0"
            r'total\s+\w+\s+(0|n/?a|none|null|\-)(?:\s|$)',
        ]

        # If content has summary patterns, check if ALL values are empty
        has_summary = False
        all_empty = True

        for pattern in total_patterns:
            matches = re.findall(pattern, content_lower)
            if matches:
                has_summary = True
                # Check if any non-empty values exist
                for match in matches:
                    if match not in ('0', 'n/a', 'na', 'none', 'null', '-', ''):
                        all_empty = False
                        break

        # If it's a summary with all empty values, consider it empty
        if has_summary and all_empty:
            # Double check - look for any numeric values > 0
            # Exclude numbers that are part of table formatting (like column widths)
            numbers = re.findall(r'(?<!\|)\b(\d+(?:,\d{3})*(?:\.\d+)?)\b(?!\s*\|)', content)
            meaningful_numbers = [n.replace(',', '') for n in numbers if float(n.replace(',', '')) > 0]
            if not meaningful_numbers:
                return True

        # Check for explicit "0 results" or "0 records" indicators
        if re.search(r'\b0\s+(results?|records?|rows?|items?|entries?)\b', content_lower):
            return True

        # Check for "no data" type messages in the content itself
        if re.search(r'no (data|results?|records?) (found|available|returned)', content_lower):
            return True

        return False
