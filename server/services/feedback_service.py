"""
Feedback Service
================

This service manages user feedback (thumbs up/down) on chat responses.
Handles feedback submission, retrieval, and toggle logic.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, UTC
from utils.id_utils import generate_id

from services.database_service import create_database_service

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service for managing user feedback on chat responses"""

    def __init__(self, config: Dict[str, Any], database_service=None):
        """
        Initialize the feedback service.

        Args:
            config: Application configuration
            database_service: Optional database service instance
        """
        self.config = config

        # Initialize database service
        if database_service is None:
            self.database_service = create_database_service(config)
        else:
            self.database_service = database_service

        # Collection/table name
        self.collection_name = 'feedback'

        self._initialized = False

        logger.debug("FeedbackService initialized")

    async def initialize(self) -> None:
        """Initialize the service and create indexes."""
        if self._initialized:
            return

        await self.database_service.initialize()

        # Create indexes for MongoDB (SQLite indexes are defined in sqlite_service.py)
        backend_type = self.config.get('internal_services', {}).get('backend', {}).get('type', 'mongodb')
        if backend_type == 'mongodb':
            await self.database_service.create_index(
                self.collection_name, [("message_id", 1), ("session_id", 1)], unique=True
            )
            await self.database_service.create_index(
                self.collection_name, "session_id"
            )
            await self.database_service.create_index(
                self.collection_name, "feedback_type"
            )
            await self.database_service.create_index(
                self.collection_name, "adapter_name"
            )

        self._initialized = True

    def _generate_id(self) -> str:
        """Generate a unique ID appropriate for the backend."""
        backend_type = self.config.get('internal_services', {}).get('backend', {}).get('type', 'mongodb')
        return generate_id(backend_type)

    async def submit_feedback(
        self,
        message_id: str,
        session_id: str,
        feedback_type: str,
        user_id: Optional[str] = None,
        adapter_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit or toggle feedback for a message.

        Idempotent logic:
        - If no existing feedback: create new
        - If same feedback_type: remove (toggle off)
        - If different feedback_type: update to new type

        Args:
            message_id: Database message ID
            session_id: Session ID
            feedback_type: 'up' or 'down'
            user_id: Optional user ID
            adapter_name: Optional adapter name

        Returns:
            Dict with message_id, feedback_type (or None if removed), and action
        """
        if not self._initialized:
            await self.initialize()

        if feedback_type not in ('up', 'down'):
            raise ValueError(f"Invalid feedback_type: {feedback_type}. Must be 'up' or 'down'.")

        now = datetime.now(UTC).isoformat()

        # Check for existing feedback
        existing = await self.database_service.find_one(
            self.collection_name,
            {"message_id": message_id, "session_id": session_id}
        )

        if existing:
            existing_type = existing.get('feedback_type')
            existing_id = existing.get('_id') or existing.get('id')

            if existing_type == feedback_type:
                # Same type: toggle off (remove)
                await self.database_service.delete_one(
                    self.collection_name,
                    {"_id": existing_id}
                )
                logger.debug(f"Feedback removed for message {message_id} (was {feedback_type})")
                return {
                    "message_id": message_id,
                    "feedback_type": None,
                    "action": "removed"
                }
            else:
                # Different type: update
                await self.database_service.update_one(
                    self.collection_name,
                    {"_id": existing_id},
                    {"$set": {"feedback_type": feedback_type, "updated_at": now}}
                )
                logger.debug(f"Feedback updated for message {message_id}: {existing_type} -> {feedback_type}")
                return {
                    "message_id": message_id,
                    "feedback_type": feedback_type,
                    "action": "updated"
                }
        else:
            # No existing feedback: create new
            document = {
                "_id": self._generate_id(),
                "message_id": message_id,
                "session_id": session_id,
                "user_id": user_id,
                "feedback_type": feedback_type,
                "adapter_name": adapter_name,
                "created_at": now,
                "updated_at": now
            }
            await self.database_service.insert_one(self.collection_name, document)
            logger.debug(f"Feedback created for message {message_id}: {feedback_type}")
            return {
                "message_id": message_id,
                "feedback_type": feedback_type,
                "action": "created"
            }

    async def get_feedback(
        self,
        message_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get feedback for a specific message.

        Args:
            message_id: Database message ID
            session_id: Session ID

        Returns:
            Feedback document or None
        """
        if not self._initialized:
            await self.initialize()

        return await self.database_service.find_one(
            self.collection_name,
            {"message_id": message_id, "session_id": session_id}
        )

    async def get_session_feedback(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all feedback for a session.

        Args:
            session_id: Session ID

        Returns:
            List of {message_id, feedback_type} dicts
        """
        if not self._initialized:
            await self.initialize()

        results = await self.database_service.find_many(
            self.collection_name,
            {"session_id": session_id},
            limit=1000
        )

        return [
            {"message_id": r.get("message_id"), "feedback_type": r.get("feedback_type")}
            for r in results
        ]
