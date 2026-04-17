from __future__ import annotations

import queue
import time
from abc import ABC
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from .document import Document

D = TypeVar("D", bound=Document)


@dataclass
class HistoryEntry:
    """One event in the app's history log.

    kind values (not exhaustive):
        "user_message"   — text submitted by the user
        "agent_message"  — text reply from the agent
        "tool_call"      — agent invoked a tool  (data includes "tool" and "input")
        "tool_result"    — result returned to the agent (data includes "tool" and "result")
    """
    kind: str
    data: dict
    timestamp: float = field(default_factory=time.time)


class Context(ABC, Generic[D]):
    """
    Central state object for a Claw app.

    Holds:
      documents    — all open Document instances (may or may not be backed by a file)
      history      — human-readable log of events (messages, tool calls, results)
      current_task — the user input / task the agent is currently working on
      chat_history — raw Anthropic API message list, managed by Agent
    """

    def __init__(self) -> None:
        self.documents:    list[D]            = []
        self.active_index: int                = -1
        self.history:      list[HistoryEntry] = []
        self.current_task: str | None         = None
        self.chat_history: list[dict]         = []   # LiteLLM/OpenAI message format
        self.agent_reason: str                = ""   # set by Agent before each tool dispatch
        self.message_queue: queue.Queue[str]  = queue.Queue()  # tool → chat panel

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    @property
    def active_document(self) -> D | None:
        if 0 <= self.active_index < len(self.documents):
            return self.documents[self.active_index]
        return None

    def open(self, doc: D) -> None:
        """Add a document and make it active."""
        self.documents.append(doc)
        self.active_index = len(self.documents) - 1

    def close(self, index: int) -> None:
        self.documents.pop(index)
        self.active_index = min(self.active_index, len(self.documents) - 1)

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def render_thumbnail(self) -> str | None:
        """Return a base64 PNG thumbnail of the active document, or None."""
        doc = self.active_document
        return doc.thumbnail_b64() if doc is not None else None

    def post_message(self, text: str) -> None:
        """Post a status message to the chat panel from a background thread."""
        self.message_queue.put(text)

    def add_history(self, kind: str, **data) -> HistoryEntry:
        """Append a history entry and return it."""
        entry = HistoryEntry(kind=kind, data=data)
        self.history.append(entry)
        return entry

    # ------------------------------------------------------------------
    # Agent context rendering
    # ------------------------------------------------------------------

    def render_context(self) -> str:
        """Return a Markdown string describing current app state for the agent.

        Override in subclasses to include app-specific state (e.g. image dimensions).
        """
        lines = ["## Current Context\n"]

        if self.current_task:
            lines.append(f"**Current task:** {self.current_task}\n")

        if not self.documents:
            lines.append("**Open documents:** none\n")
        else:
            lines.append("**Open documents:**\n")
            for i, doc in enumerate(self.documents):
                marker = " (active)" if i == self.active_index else ""
                lines.append(f"- {doc.name}{marker}")

        return "\n".join(lines)
