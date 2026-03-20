from __future__ import annotations

from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import BaseMessage

from config.settings import settings


def get_chat_history(session_id: str) -> SQLChatMessageHistory:
    """Return a chat message history backed by SQLite for the given session."""
    return SQLChatMessageHistory(
        session_id=session_id,
        connection=settings.database_url,
        table_name="message_store",
    )


def load_history_messages(session_id: str, last_k: int = 20) -> list[BaseMessage]:
    """Load the most recent *last_k* messages for a session."""
    history = get_chat_history(session_id)
    messages = history.messages
    return messages[-last_k:] if len(messages) > last_k else messages


def save_message(session_id: str, message: BaseMessage) -> None:
    """Persist a single message to the session history."""
    history = get_chat_history(session_id)
    history.add_message(message)


def clear_history(session_id: str) -> None:
    """Delete all messages for the given session."""
    history = get_chat_history(session_id)
    history.clear()
