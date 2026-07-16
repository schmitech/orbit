"""Shared key-naming for the per-session "generation memory" namespace.

Image/video/document generation pipeline steps (see
inference/pipeline/steps/_utils.py) store the previous turn's effective
prompt/spec directly in ThreadDatasetService, keyed by adapter+session rather
than through ThreadService's conversation_threads table. Conversation deletion
(chat_history_service._cascade_delete_session) needs the same key format to
clean those rows up — this module is the one place both sides import it from,
so pipeline steps (which write) and the service layer (which deletes) can't
drift apart.
"""

GENERATION_ADAPTER_TYPES = frozenset({'image_generation', 'video_generation', 'document_generation'})


def generation_memory_key(adapter_name: str, session_id: str) -> str:
    return f"genmem:{adapter_name}:{session_id}"
