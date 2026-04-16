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
from .workspace import ImageWorkspace

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

SILVER = (192, 192, 192, 255)
TITLE_SIZE = 48
TITLE_MARGIN = 12

# Temporary placeholder colors — replace when panels get real content
_COLOR_HEADER = (45,  45,  70, 255)
_COLOR_DOCK   = (35,  60,  45, 255)
_COLOR_MAIN   = (25,  25,  25, 255)
_COLOR_CHAT   = (55,  35,  60, 255)


class PixelClawApp(App):
    def create_workspace(self) -> Context:
        return ImageWorkspace()

    def create_tools(self) -> list[Tool]:
        return []

    def on_start(self) -> None:
        self.header = Panel("Header")
        self.dock   = DockPanel("Dock",  context=self.workspace)
        self.main   = MainPanel("Main",  context=self.workspace)
        self.chat   = ChatPanel("Chat")

        self.header.bg_color = _COLOR_HEADER
        self.dock.bg_color   = _COLOR_DOCK
        self.main.bg_color   = _COLOR_MAIN
        self.chat.bg_color   = _COLOR_CHAT

        for panel in (self.header, self.dock, self.main, self.chat):
            self.root.add(panel)

        self.layout = LayoutManager(self.header, self.dock, self.main, self.chat)
        self.layout.update(rl.GetScreenWidth(), rl.GetScreenHeight())

        self._populate_test_chat()

    def _populate_test_chat(self) -> None:
        msgs = [
            ("agent", "Hello! I'm PixelClaw, your AI image editing assistant. How can I help you today?"),
            ("user",  "Can you remove the background from this photo?"),
            ("agent", "Sure! I'll isolate the subject and replace the background with transparency. One moment…"),
            ("agent", "Done. The background has been removed. The result is in your workspace as a PNG with an alpha channel. Would you like me to replace it with a solid color or a different image instead?"),
            ("user",  "Make the background a soft gradient from light blue at the top to white at the bottom."),
            ("agent", "Got it — applying a vertical gradient (light blue → white) behind the subject now."),
            ("user",  "That looks great! Can you also sharpen the subject a little?"),
            ("agent", "Applied a moderate unsharp-mask to the subject layer. You can see the result in the main view. Let me know if you'd like it stronger or softer."),
            ("user",  "Perfect. Now export it as a JPEG at 90% quality."),
            ("agent", "Exported as output.jpg at 90% quality (2.4 MB). The file has been saved to your downloads folder."),
        ]
        for source, text in msgs:
            self.chat.add_entry(text, source)

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
    PixelClawApp(title="PixelClaw").run()


if __name__ == "__main__":
    main()
