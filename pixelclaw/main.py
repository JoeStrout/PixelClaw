import queue
import threading
from pathlib import Path

import raylib as rl

from agentcore.app import App
from agentcore.chatpanel import ChatPanel
from agentcore.context import Context
from agentcore.panel import Panel
from agentcore.resources import default_font
from agentcore.tool import Tool

from .document import ImageDocument
from .dockpanel import DockPanel
from .layout import LayoutManager
from .mainpanel import MainPanel
from . import textures
from .tools import (ApplyTool, CloseDocsTool, CropTool, InspectTool, MultiApplyTool,
                    NewFromRegionTool, PadTool, RevertTool, ScaleTool, SetActiveTool,
                    VersionHistoryTool)
from .workspace import ImageWorkspace

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

SILVER = (192, 192, 192, 255)
TITLE_SIZE = 48
TITLE_MARGIN = 12

_COLOR_HEADER = (45,  45,  70, 255)
_COLOR_DOCK   = (35,  60,  45, 255)
_COLOR_MAIN   = (25,  25,  25, 255)
_COLOR_CHAT   = (55,  35,  60, 255)


class PixelClawApp(App):
    def get_instructions_path(self) -> Path:
        return Path(__file__).parent / "agent_instructions.md"

    def create_workspace(self) -> Context:
        return ImageWorkspace()

    def create_tools(self) -> list[Tool]:
        return [
            ApplyTool(), CloseDocsTool(), CropTool(), InspectTool(),
            MultiApplyTool(), NewFromRegionTool(), PadTool(), RevertTool(),
            ScaleTool(), SetActiveTool(), VersionHistoryTool(),
        ]

    def on_start(self) -> None:
        self._reply_queue: queue.Queue[str] = queue.Queue()

        self.header = Panel("Header")
        self.dock   = DockPanel("Dock",  context=self.workspace)
        self.main   = MainPanel("Main",  context=self.workspace)
        self.chat   = ChatPanel("Chat",  on_message=self._handle_message)

        self.header.bg_color = _COLOR_HEADER
        self.dock.bg_color   = _COLOR_DOCK
        self.main.bg_color   = _COLOR_MAIN
        self.chat.bg_color   = _COLOR_CHAT

        for panel in (self.header, self.dock, self.main, self.chat):
            self.root.add(panel)

        self.layout = LayoutManager(self.header, self.dock, self.main, self.chat)
        self.layout.update(rl.GetScreenWidth(), rl.GetScreenHeight())

    def _handle_message(self, text: str) -> None:
        self.chat.add_entry(text, "user")

        def _run() -> None:
            try:
                reply = self.agent.chat(text)
            except Exception as e:
                reply = f"(Error: {e})"
            self._reply_queue.put(reply)

        threading.Thread(target=_run, daemon=True).start()

    def on_files_dropped(self, paths: list[str]) -> None:
        opened, skipped = [], []
        for p in paths:
            path = Path(p)
            if path.suffix.lower() in _SUPPORTED_EXTENSIONS:
                doc = ImageDocument(path)
                self.workspace.open(doc)
                self.workspace.add_history("document_opened", name=doc.name, path=str(path))
                opened.append(path.name)
            else:
                skipped.append(path.name)
        if opened:
            msg = f"Opened: {', '.join(opened)}"
            self.chat.add_entry(msg, "agent")
            self.workspace.add_history("agent_message", text=msg)
        if skipped:
            msg = f"Skipped (unsupported format): {', '.join(skipped)}"
            self.chat.add_entry(msg, "agent")
            self.workspace.add_history("agent_message", text=msg)

    def on_close(self) -> None:
        self.chat.unload()
        textures.unload_all()

    def update(self) -> None:
        while not self._reply_queue.empty():
            reply = self._reply_queue.get_nowait()
            self.chat.add_entry(reply, "agent")
            for doc in self.workspace.documents:
                textures.invalidate_thumbnail(doc)
                textures.invalidate_display(doc)

        if rl.IsWindowResized():
            self.layout.update(rl.GetScreenWidth(), rl.GetScreenHeight())
            self.root.width  = rl.GetScreenWidth()
            self.root.height = rl.GetScreenHeight()

    def draw(self) -> None:
        self._draw_title()

    def _draw_title(self) -> None:
        font = default_font()
        text = "PixelClaw"
        w, _ = font.measure(text, TITLE_SIZE)
        x = rl.GetScreenWidth() - w - TITLE_MARGIN
        font.draw(text, x, TITLE_MARGIN, TITLE_SIZE, SILVER)


def main() -> None:
    key_file = Path(__file__).parent.parent / "api_key.secret"
    api_key = key_file.read_text().strip() if key_file.exists() else None
    PixelClawApp(title="PixelClaw", api_key=api_key).run()


if __name__ == "__main__":
    main()
