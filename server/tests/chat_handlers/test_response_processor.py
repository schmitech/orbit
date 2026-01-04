"""
Tests for ResponseProcessor.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.chat_handlers.response_processor import ResponseProcessor
from services.chat_handlers.conversation_history_handler import ConversationHistoryHandler


class TestResponseProcessor:
    """Test suite for ResponseProcessor."""

    @pytest.fixture
    def mock_conversation_handler(self):
        """Mock conversation history handler."""
        handler = AsyncMock(spec=ConversationHistoryHandler)
        handler.check_limit_warning = AsyncMock(return_value=None)
        # store_turn now returns (user_msg_id, assistant_msg_id)
        handler.store_turn = AsyncMock(return_value=("user_msg_123", "assistant_msg_456"))
        return handler

    def test_initialization(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test processor initialization."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        assert processor.config == base_config
        assert processor.conversation_handler == mock_conversation_handler
        assert processor.logger_service == mock_logger_service

    def test_format_response(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test response formatting."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # Test with text that needs formatting
        response = "Hello  world\n\nMultiple  spaces"
        result = processor.format_response(response)

        # Should clean up formatting issues
        assert isinstance(result, str)
        assert "Hello" in result
        assert "world" in result

    def test_inject_warning_with_warning(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test warning injection when warning provided."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        response = "Original response"
        warning = "This is a warning"

        result = processor.inject_warning(response, warning)

        assert "Original response" in result
        assert "This is a warning" in result
        assert "---" in result

    def test_inject_warning_without_warning(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test warning injection when no warning."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        response = "Original response"

        result = processor.inject_warning(response, None)

        assert result == "Original response"

    @pytest.mark.asyncio
    async def test_log_request_details(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test request details logging."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # Should not raise any exceptions
        await processor.log_request_details(
            message="Test message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            system_prompt_id="prompt123",
            api_key="sk-1234567890abcdef",
            session_id="session123",
            user_id="user456"
        )

    @pytest.mark.asyncio
    async def test_log_conversation_success(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test successful conversation logging."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        await processor.log_conversation(
            query="User query",
            response="Assistant response",
            client_ip="127.0.0.1",
            backend="openai",
            api_key="key123",
            session_id="session456",
            user_id="user789"
        )

        mock_logger_service.log_conversation.assert_called_once_with(
            query="User query",
            response="Assistant response",
            ip="127.0.0.1",
            backend="openai",
            blocked=False,
            api_key="key123",
            session_id="session456",
            user_id="user789"
        )

    @pytest.mark.asyncio
    async def test_log_conversation_handles_error(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test that logging errors are handled gracefully."""
        mock_logger_service.log_conversation.side_effect = Exception("Logging failed")

        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # Should not raise exception
        await processor.log_conversation(
            query="User query",
            response="Assistant response",
            client_ip="127.0.0.1",
            backend="openai"
        )

    @pytest.mark.asyncio
    async def test_process_response_complete_flow(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test complete response processing flow."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # process_response now returns (processed_response, assistant_message_id)
        processed_response, assistant_message_id = await processor.process_response(
            response="This is the response",
            message="User message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            session_id="session123",
            user_id="user456",
            api_key="key789",
            backend="openai",
            processing_time=1.5
        )

        # Check that response is formatted
        assert "This is the response" in processed_response
        # Check that assistant_message_id is returned
        assert assistant_message_id == "assistant_msg_456"

        # Check that conversation was stored
        mock_conversation_handler.store_turn.assert_called_once()
        call_args = mock_conversation_handler.store_turn.call_args
        assert call_args[1]['session_id'] == "session123"
        assert call_args[1]['user_message'] == "User message"
        assert call_args[1]['adapter_name'] == "test_adapter"

        # Check that conversation was logged
        mock_logger_service.log_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_response_with_warning(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test response processing with warning injection."""
        mock_conversation_handler.check_limit_warning.return_value = "Warning message"

        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        processed_response, assistant_message_id = await processor.process_response(
            response="Original response",
            message="User message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            session_id="session123",
            user_id=None,
            api_key=None,
            backend="openai",
            processing_time=1.0
        )

        assert "Original response" in processed_response
        assert "Warning message" in processed_response
        assert assistant_message_id == "assistant_msg_456"

    @pytest.mark.asyncio
    async def test_process_response_without_session(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test response processing without session ID."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        processed_response, assistant_message_id = await processor.process_response(
            response="Response",
            message="Message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            session_id=None,  # No session
            user_id=None,
            api_key=None,
            backend="openai",
            processing_time=1.0
        )

        # Should not store conversation turn (no session)
        mock_conversation_handler.store_turn.assert_not_called()

        # assistant_message_id should be None when no session
        assert assistant_message_id is None

        # But should still log
        mock_logger_service.log_conversation.assert_called_once()

    def test_build_result_basic(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test building basic result dictionary."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test response",
            sources=[{"title": "Source 1"}],
            metadata={"key": "value"},
            processing_time=1.5
        )

        assert result["response"] == "Test response"
        assert result["sources"] == [{"title": "Source 1"}]
        assert result["metadata"]["key"] == "value"
        assert result["metadata"]["processing_time"] == 1.5
        assert result["metadata"]["pipeline_used"] is True

    def test_build_result_with_audio(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test building result with audio data."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test response",
            sources=[],
            metadata={},
            processing_time=1.0,
            audio_data=b'test_audio_data',
            audio_format='mp3'
        )

        assert "audio" in result
        assert result["audio_format"] == "mp3"
        # Should be base64 encoded
        import base64
        decoded = base64.b64decode(result["audio"])
        assert decoded == b'test_audio_data'

    def test_build_result_without_audio(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test building result without audio data."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test response",
            sources=[],
            metadata={},
            processing_time=1.0,
            audio_data=None,
            audio_format=None
        )

        assert "audio" not in result
        assert "audio_format" not in result

    def test_build_result_preserves_metadata(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test that existing metadata is preserved."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test",
            sources=[],
            metadata={"existing_key": "existing_value", "another": 123},
            processing_time=2.0
        )

        assert result["metadata"]["existing_key"] == "existing_value"
        assert result["metadata"]["another"] == 123
        assert result["metadata"]["processing_time"] == 2.0
        assert result["metadata"]["pipeline_used"] is True


class TestResponseProcessorThreadingDetection:
    """Test suite for threading detection methods."""

    @pytest.fixture
    def processor(self, base_config, mock_conversation_handler, mock_logger_service):
        """Create a ResponseProcessor instance for testing."""
        return ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

    @pytest.fixture
    def mock_conversation_handler(self):
        """Mock conversation history handler."""
        handler = AsyncMock(spec=ConversationHistoryHandler)
        handler.check_limit_warning = AsyncMock(return_value=None)
        handler.store_turn = AsyncMock(return_value=("user_msg_123", "assistant_msg_456"))
        return handler

    # ==========================================
    # Tests for _response_indicates_no_results
    # ==========================================

    @pytest.mark.parametrize("response,expected", [
        # Explicit "couldn't find" patterns
        ("Sorry, but I couldn't find any results for that query.", True),
        ("I couldn't find any matching data.", True),
        ("Could not find any records for your search.", True),
        ("Unable to find relevant information.", True),
        ("I didn't find any results.", True),

        # "No results" variations
        ("No results were found for your query.", True),
        ("There are no matching records.", True),
        ("No data available for that time period.", True),
        ("Zero results returned.", True),

        # Apologetic patterns
        ("Sorry, I don't have information about mangos.", True),
        ("Unfortunately, there's no data matching your criteria.", True),
        ("I apologize, but I couldn't locate that information.", True),

        # Suggestion to try different query
        ("Please try a different question.", True),
        ("Try another search term.", True),
        ("Could you rephrase your question?", True),

        # Short responses with negative indicators
        ("Sorry, no results found. Try a different query.", True),
        ("I'm sorry, but that's outside my knowledge.", True),

        # Valid data responses (should NOT indicate no results)
        ("Here are the top 10 contracts with their values and dates.", False),
        ("The database returned 120,976 contracts totaling $5.2 billion.", False),
        ("Based on the data, Tesla has the highest market share at 45%.", False),
        ("The employee John Smith works in the Engineering department.", False),

        # Edge cases
        ("", True),  # Empty response
        (None, True),  # None response
    ])
    def test_response_indicates_no_results(self, processor, response, expected):
        """Test detection of 'no results' responses."""
        # Handle None case
        if response is None:
            result = processor._response_indicates_no_results(response)
        else:
            result = processor._response_indicates_no_results(response)
        assert result == expected, f"Failed for response: '{response}'"

    def test_response_indicates_no_results_long_valid_response(self, processor):
        """Test that long responses with actual data are not flagged."""
        long_response = """
        Here are the travel expenses for Q4 2024:

        | Department | Total Trips | Total Spending |
        |------------|-------------|----------------|
        | Sales      | 45          | $125,000       |
        | Marketing  | 32          | $89,500        |
        | Engineering| 18          | $52,300        |

        The Sales department had the highest travel spending, primarily due to
        client visits and trade shows. Marketing expenses were focused on
        conference attendance.
        """
        assert processor._response_indicates_no_results(long_response) is False

    def test_response_indicates_no_results_multilingual(self, processor):
        """Test detection works with common patterns regardless of surrounding text."""
        responses = [
            "Lo siento, no results found for that query.",
            "Désolé, I couldn't find any matching records.",
        ]
        for response in responses:
            assert processor._response_indicates_no_results(response) is True

    @pytest.mark.parametrize("response,expected", [
        # French
        ("Désolé, je n'ai trouvé aucun résultat pour cette requête.", True),
        ("Malheureusement, pas de données correspondantes.", True),
        ("Voici les résultats de votre recherche avec 150 contrats.", False),

        # Spanish
        ("Lo siento, no encontré ningún resultado.", True),
        ("Lamentablemente, no hay datos disponibles.", True),
        ("Aquí están los 120 contratos encontrados.", False),

        # German
        ("Leider konnte ich keine Ergebnisse finden.", True),
        ("Entschuldigung, keine Daten verfügbar.", True),
        ("Hier sind die 50 gefundenen Verträge.", False),

        # Italian
        ("Mi dispiace, non ho trovato risultati.", True),
        ("Purtroppo nessun dato disponibile.", True),
        ("Ecco i 75 contratti trovati.", False),

        # Portuguese
        ("Desculpe, não encontrei nenhum resultado.", True),
        ("Infelizmente, sem dados disponíveis.", True),
        ("Aqui estão os 200 contratos encontrados.", False),

        # Dutch
        ("Helaas kon ik geen resultaten vinden.", True),
        ("Hier zijn de 30 gevonden contracten.", False),
    ])
    def test_response_indicates_no_results_full_multilingual(self, processor, response, expected):
        """Test full multilingual 'no results' detection."""
        result = processor._response_indicates_no_results(response)
        assert result == expected, f"Failed for response: '{response}'"

    # ==========================================
    # Tests for _sources_contain_actual_data
    # ==========================================

    def test_sources_contain_actual_data_with_valid_sources(self, processor):
        """Test detection of sources with actual data."""
        sources = [
            {
                "content": "Employee: John Smith, Department: Engineering, Salary: $95,000",
                "confidence": 0.85,
                "metadata": {"row_count": 1}
            }
        ]
        assert processor._sources_contain_actual_data(sources) is True

    def test_sources_contain_actual_data_empty_sources(self, processor):
        """Test detection with empty sources list."""
        assert processor._sources_contain_actual_data([]) is False
        assert processor._sources_contain_actual_data(None) is False

    def test_sources_contain_actual_data_zero_row_count(self, processor):
        """Test detection when row_count is 0."""
        sources = [
            {
                "content": "Travel-expense summary\nTotal trips: 0\nTotal spending: N/A",
                "confidence": 0.75,
                "metadata": {"row_count": 0}
            }
        ]
        assert processor._sources_contain_actual_data(sources) is False

    def test_sources_contain_actual_data_empty_results_flag(self, processor):
        """Test detection when empty_results flag is set."""
        sources = [
            {
                "content": "Query executed successfully",
                "confidence": 0.9,
                "metadata": {"empty_results": True}
            }
        ]
        assert processor._sources_contain_actual_data(sources) is False

    def test_sources_contain_actual_data_no_data_flag(self, processor):
        """Test detection when no_data flag is set."""
        sources = [
            {
                "content": "Summary report",
                "confidence": 0.8,
                "metadata": {"no_data": True}
            }
        ]
        assert processor._sources_contain_actual_data(sources) is False

    def test_sources_contain_actual_data_mixed_sources(self, processor):
        """Test that one valid source among empty ones returns True."""
        sources = [
            {
                "content": "Total: 0",
                "confidence": 0.5,
                "metadata": {"row_count": 0}
            },
            {
                "content": "Employee: Jane Doe, Department: Sales, Salary: $85,000",
                "confidence": 0.85,
                "metadata": {"row_count": 1}
            }
        ]
        assert processor._sources_contain_actual_data(sources) is True

    # ==========================================
    # Tests for _content_indicates_empty
    # ==========================================

    @pytest.mark.parametrize("content,expected", [
        # Empty/null content
        ("", True),
        ("   ", True),
        (None, True),

        # Summary tables with all zeros/N/A
        ("Total trips: 0\nTotal spending: N/A\nTotal airfare: N/A", True),
        ("Count: 0\nSum: N/A", True),
        ("Total records: 0", True),

        # Explicit "0 results" indicators
        ("0 results returned", True),
        ("0 records found", True),
        ("0 rows matched", True),

        # "No data" messages in content
        ("No data found for the specified criteria", True),
        ("No results available", True),
        ("No records returned from database", True),

        # Valid content with actual data
        ("Total trips: 45\nTotal spending: $125,000", False),
        ("Count: 150\nSum: $1,500,000", False),
        ("Employee: John Smith, Salary: $95,000", False),

        # Content with mixed zeros but some real values
        ("Total trips: 0\nTotal spending: $5,000", False),
    ])
    def test_content_indicates_empty(self, processor, content, expected):
        """Test detection of empty content indicators."""
        # Handle None case
        result = processor._content_indicates_empty(content) if content is not None else processor._content_indicates_empty("")
        if content is None:
            result = processor._content_indicates_empty(content)
        assert result == expected, f"Failed for content: '{content}'"

    def test_content_indicates_empty_complex_table(self, processor):
        """Test with complex table content that has actual data."""
        content = """
        Contract Summary

        | Metric          | Value      |
        |-----------------|------------|
        | Total contracts | 120,976    |
        | Total value     | $5.2B      |
        | Average value   | $43,000    |
        """
        assert processor._content_indicates_empty(content) is False

    def test_content_indicates_empty_all_zero_table(self, processor):
        """Test with table content where all values are zero/N/A."""
        content = """
        Travel-expense summary

        | Metric         | Value |
        |----------------|-------|
        | Total trips    | 0     |
        | Total spending | N/A   |
        | Total airfare  | N/A   |
        | Total lodging  | N/A   |
        """
        assert processor._content_indicates_empty(content) is True

    # ==========================================
    # Tests for _has_meaningful_results
    # ==========================================

    def test_has_meaningful_results_no_results_response(self, processor):
        """Test that LLM 'no results' response disables threading."""
        sources = [
            {
                "content": "Contract data: Total contracts: 120,976",
                "confidence": 0.85,
                "metadata": {}
            }
        ]
        response = "Sorry, but I couldn't find any results for that query. Please try a different question."

        # Even with valid sources, the LLM response should take priority
        assert processor._has_meaningful_results(sources, response) is False

    def test_has_meaningful_results_valid_response_valid_sources(self, processor):
        """Test that valid response with valid sources enables threading."""
        sources = [
            {
                "content": "Employee: John Smith, Department: Engineering",
                "confidence": 0.85,
                "metadata": {"row_count": 1}
            }
        ]
        response = "Based on the data, John Smith works in the Engineering department."

        assert processor._has_meaningful_results(sources, response) is True

    def test_has_meaningful_results_no_confident_sources(self, processor):
        """Test that low confidence sources disable threading."""
        sources = [
            {
                "content": "Some data",
                "confidence": 0.001,
                "metadata": {}
            }
        ]
        response = "Here is the information you requested."

        assert processor._has_meaningful_results(sources, response) is False

    def test_has_meaningful_results_empty_sources(self, processor):
        """Test that empty sources disable threading."""
        sources = []
        response = "Here is the information you requested."

        assert processor._has_meaningful_results(sources, response) is False

    def test_has_meaningful_results_sources_with_zero_data(self, processor):
        """Test that sources with zero data disable threading."""
        sources = [
            {
                "content": "Total trips: 0\nTotal spending: N/A",
                "confidence": 0.85,
                "metadata": {"row_count": 0}
            }
        ]
        response = "The query returned zero trips for that period."

        assert processor._has_meaningful_results(sources, response) is False

    def test_has_meaningful_results_mango_query_scenario(self, processor):
        """Test the specific 'mangos in tree' false positive scenario."""
        # Retriever returned contracts data (false positive match)
        sources = [
            {
                "content": "Contract Count\n\nMetric: Total contracts\nValue: 120,976",
                "confidence": 0.45,  # Low but above threshold
                "metadata": {"similarity": 0.45}
            }
        ]
        # But LLM correctly said "no results"
        response = "Sorry, but I couldn't find any results for that query. Please try a different question."

        # Threading should be disabled because LLM recognized irrelevant query
        assert processor._has_meaningful_results(sources, response) is False

    # ==========================================
    # Tests for build_result with threading
    # ==========================================

    def test_build_result_threading_disabled_for_no_results_response(self, processor):
        """Test that threading is disabled when LLM says no results."""
        # Configure adapter to support threading
        processor.config['adapters'] = [
            {'name': 'intent-test', 'capabilities': {'supports_threading': True}}
        ]

        result = processor.build_result(
            response="Sorry, I couldn't find any results for that query.",
            sources=[{"content": "Some data", "confidence": 0.5}],
            metadata={},
            processing_time=1.0,
            assistant_message_id="msg_123",
            session_id="session_456",
            adapter_name="intent-test"
        )

        # Threading should NOT be in result
        assert "threading" not in result

    def test_build_result_threading_enabled_for_valid_results(self, processor):
        """Test that threading is enabled when there are valid results."""
        # Configure adapter to support threading
        processor.config['adapters'] = [
            {'name': 'intent-test', 'capabilities': {'supports_threading': True}}
        ]

        result = processor.build_result(
            response="Based on the data, here are the top contracts...",
            sources=[{
                "content": "Contract: ABC Corp, Value: $1.5M",
                "confidence": 0.85,
                "metadata": {"row_count": 10}
            }],
            metadata={},
            processing_time=1.0,
            assistant_message_id="msg_123",
            session_id="session_456",
            adapter_name="intent-test"
        )

        # Threading should be in result
        assert "threading" in result
        assert result["threading"]["supports_threading"] is True
        assert result["threading"]["message_id"] == "msg_123"
        assert result["threading"]["session_id"] == "session_456"

    def test_build_result_threading_disabled_for_empty_data(self, processor):
        """Test that threading is disabled when sources contain empty data."""
        processor.config['adapters'] = [
            {'name': 'intent-test', 'capabilities': {'supports_threading': True}}
        ]

        result = processor.build_result(
            response="The query completed but returned no matching records.",
            sources=[{
                "content": "Total: 0\nCount: 0",
                "confidence": 0.85,
                "metadata": {"row_count": 0}
            }],
            metadata={},
            processing_time=1.0,
            assistant_message_id="msg_123",
            session_id="session_456",
            adapter_name="intent-test"
        )

        # Threading should NOT be in result
        assert "threading" not in result
