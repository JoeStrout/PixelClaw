import queue
import threading
from pathlib import Path

import numpy as np
import raylib as rl
from PIL import Image

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
from .ml_deps import ensure_packages
from .tools import (ApplyTool, CloseDocsTool, CropTool, EditImageTool, GenerateImageTool,
                    InspectTool, MultiApplyTool, NewFromRegionTool, NewImageTool, PadTool,
                    PixelateTool, PosterizeTool, QueryTool, RemoveBackgroundTool, RevertTool,
                    RotateTool, ScaleTool, SeparateLayersTool, SetActiveTool, SoftThresholdTool,
                    TrimTool, UndoTool, VersionHistoryTool)
from .file_dialogs import save_image
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
    def __init__(self, *, openai_key: str | None = None, **kwargs) -> None:
        self._openai_key = openai_key
        super().__init__(**kwargs)

    def get_instructions_path(self) -> Path:
        return Path(__file__).parent / "agent_instructions.md"

    def create_workspace(self) -> Context:
        return ImageWorkspace()

    def create_tools(self) -> list[Tool]:
        return [
            ApplyTool(), CloseDocsTool(), CropTool(),
            EditImageTool(self._openai_key), GenerateImageTool(self._openai_key),
            InspectTool(), MultiApplyTool(), NewFromRegionTool(), NewImageTool(), PadTool(),
            PixelateTool(), PosterizeTool(), QueryTool(), RemoveBackgroundTool(), RevertTool(),
            RotateTool(), ScaleTool(), SeparateLayersTool(), SetActiveTool(), SoftThresholdTool(),
            TrimTool(), UndoTool(), VersionHistoryTool(),
        ]

    def on_start(self) -> None:
        self._reply_queue: queue.Queue[str] = queue.Queue()
        self._save_key = _find_key_for_char('s')
        self._window_focused = rl.IsWindowFocused()

        self.header = Panel("Header")
        self.dock   = DockPanel("Dock",  context=self.workspace)
        self.main   = MainPanel("Main",  context=self.workspace)
        self.chat   = ChatPanel("Chat",  on_message=self._handle_message)

        self.header.bg_color = _COLOR_HEADER
        self.dock.bg_color   = _COLOR_DOCK
        self.main.bg_color   = _COLOR_MAIN
        self.chat.bg_color   = _COLOR_CHAT

        self.main._input_field = self.chat._input
        self.main._focus_input_fn = lambda: (
            self.root.set_focus(self.chat),
            self.chat.set_focus(self.chat._input),
        )

        for panel in (self.header, self.dock, self.main, self.chat):
            self.root.add(panel)

        self.layout = LayoutManager(self.header, self.dock, self.main, self.chat)
        self.layout.update(rl.GetScreenWidth(), rl.GetScreenHeight())

    def _handle_message(self, text: str) -> None:
        self.chat.add_entry(text, "user")
        self.chat.thinking = True
        self.chat._thinking_start = rl.GetTime()
        self.chat._thinking_shown = False

        def _run() -> None:
            try:
                reply = self.agent.chat(text)
            except Exception as e:
                reply = f"(Error: {e})"
            self._reply_queue.put(reply)

        threading.Thread(target=_run, daemon=True).start()

    def _process_input(self) -> None:
        # Snapshot focus state from the previous frame so MainPanel can ignore
        # the activating click when the user switches to this window.
        self.main._window_was_focused = self._window_focused
        cmd  = rl.IsKeyDown(rl.KEY_LEFT_SUPER)   or rl.IsKeyDown(rl.KEY_RIGHT_SUPER)
        ctrl = rl.IsKeyDown(rl.KEY_LEFT_CONTROL) or rl.IsKeyDown(rl.KEY_RIGHT_CONTROL)
        if (cmd or ctrl) and rl.IsKeyPressed(self._save_key):
            self._save_active_document()
        if rl.IsKeyPressed(rl.KEY_TAB):
            self.root.set_focus(self.chat)
            self.chat.set_focus(self.chat._input)
        super()._process_input()
        self._window_focused = rl.IsWindowFocused()

    def _save_active_document(self) -> None:
        doc = self.workspace.active_document
        if not isinstance(doc, ImageDocument) or doc.image is None:
            return
        path = save_image(doc.name)
        if path is None:
            return
        try:
            _save_pil(doc.image, path)
            doc.path = path
            doc.dirty = False
            self.chat.add_entry(f"Saved '{path.name}'.", "agent")
        except Exception as e:
            self.chat.add_entry(f"Save failed: {e}", "agent")

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
        self.main.unload()
        textures.unload_all()

    def update(self) -> None:
        while not self.workspace.message_queue.empty():
            self.chat.add_entry(self.workspace.message_queue.get_nowait(), "agent")

        while not self._reply_queue.empty():
            reply = self._reply_queue.get_nowait()
            self.chat.thinking = False
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


def _find_key_for_char(char: str) -> int:
    """Return the Raylib key code that produces *char* in the current keyboard layout.

    Uses glfwGetKeyName (layout-aware) so Dvorak, Colemak, etc. work correctly.
    Falls back to the QWERTY key code if no match is found.
    """
    target = char.lower()
    fallback = getattr(rl, f"KEY_{char.upper()}", rl.KEY_S)
    for key in range(32, 350):
        raw = rl.glfwGetKeyName(key, 0)
        if raw != rl.ffi.NULL:
            name = rl.ffi.string(raw).decode(errors="ignore").lower()
            if name == target:
                return key
    return fallback


def _save_pil(image: np.ndarray, path: Path) -> None:
    pil = Image.fromarray(image, "RGBA")
    if path.suffix.lower() in (".jpg", ".jpeg"):
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[3])
        bg.save(path)
    else:
        pil.save(path)


def main() -> None:
    ensure_packages()
    root = Path(__file__).parent.parent
    api_key = (root / "api_key.secret").read_text().strip() if (root / "api_key.secret").exists() else None
    openai_key_file = root / "openai_key.secret"
    openai_key = openai_key_file.read_text().strip() if openai_key_file.exists() else api_key
    PixelClawApp(title="PixelClaw", api_key=api_key, openai_key=openai_key).run()


if __name__ == "__main__":
    main()
