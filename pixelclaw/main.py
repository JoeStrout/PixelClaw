import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # prevent libomp/libiomp5 dual-runtime crash
import queue
import threading
from pathlib import Path

import numpy as np
import raylib as rl
from PIL import Image

from agentcore.app import App
from agentcore.chatpanel import ChatPanel
from agentcore.context import Context
from agentcore.key_utils import find_key_for_char as _find_key_for_char
from agentcore.tool import Tool

from .document import ImageDocument
from .dockpanel import DockPanel
from .headerpanel import HeaderPanel
from .layout import LayoutManager
from .mainpanel import MainPanel
from . import textures
from .ml_deps import ensure_packages
from agentcore.speech import speak, preload as preload_speech
from agentcore.stt import preload as preload_stt
from .tools import (ApplyTool, CloseDocsTool, CropTool, DefringeTool, EditImageTool, FillTool,
                    GenerateImageTool, InspectTool, MultiApplyTool, NewFromRegionTool, NewImageTool,
                    OpenDocumentTool, PadTool, PixelateTool, PosterizeTool, QueryTool,
                    RemoveBackgroundTool, RenameDocumentTool, RevertTool, RotateTool,
                    SaveDocumentTool, ScaleTool, SeparateLayersTool, SetActiveTool, SetBgColorTool,
                    SoftThresholdTool, TrimTool, UndoTool, VersionHistoryTool)
from .file_dialogs import open_images, save_image
from .headerpanel import _alt_is_held
from .workspace import ImageWorkspace

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

_COLOR_HEADER = (45,  45,  70, 255)
_COLOR_DOCK   = (35,  60,  45, 255)
_COLOR_MAIN   = (25,  25,  25, 255)
_COLOR_CHAT   = (55,  35,  60, 255)


class PixelClawApp(App):
    def __init__(self, *, openai_key: str | None = None, **kwargs) -> None:
        self._openai_key = openai_key
        self._dialog_queue: queue.Queue = queue.Queue()
        super().__init__(**kwargs)

    def get_instructions_path(self) -> Path:
        return Path(__file__).parent / "agent_instructions.md"

    def create_workspace(self) -> Context:
        return ImageWorkspace()

    def create_tools(self) -> list[Tool]:
        return [
            ApplyTool(), CloseDocsTool(), CropTool(), DefringeTool(), FillTool(),
            EditImageTool(self._openai_key), GenerateImageTool(self._openai_key),
            InspectTool(), MultiApplyTool(), NewFromRegionTool(), NewImageTool(),
            OpenDocumentTool(dialog_queue=self._dialog_queue), PadTool(),
            PixelateTool(), PosterizeTool(), QueryTool(), RemoveBackgroundTool(),
            RenameDocumentTool(), RevertTool(), RotateTool(), SaveDocumentTool(),
            ScaleTool(), SeparateLayersTool(), SetActiveTool(), SetBgColorTool(), SoftThresholdTool(),
            TrimTool(), UndoTool(), VersionHistoryTool(),
        ]

    def on_start(self) -> None:
        rl.InitAudioDevice()
        preload_speech()
        preload_stt()
        self._reply_queue: queue.Queue[str] = queue.Queue()
        self._save_key  = _find_key_for_char('s')
        self._open_key  = _find_key_for_char('o')
        self._close_key = _find_key_for_char('w')
        self._window_focused = rl.IsWindowFocused()

        self.header = HeaderPanel("Header")
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
        self.header.setup(
            self.workspace,
            on_open=self._open_documents,
            on_save=self._save_active_document,
            on_close_doc=self._close_active_document,
        )

    def _handle_message(self, text: str) -> None:
        self.chat.add_entry(text, "user")

        # Slash commands handled locally — no LLM call.
        stripped = text.strip()
        if stripped.startswith("/model"):
            parts = stripped.split(None, 1)
            if len(parts) == 1:
                self._reply_queue.put(f"Current model: {self.agent.model}", "agent")
            else:
                new_model = _expand_model(parts[1].strip())
                prev_model = self.agent.model
                self.agent.model = new_model
                self.chat.thinking = True
                self.chat._thinking_start = rl.GetTime()
                self.chat._thinking_shown = False

                def _validate() -> None:
                    import litellm
                    try:
                        litellm.completion(
                            model=new_model,
                            messages=[{"role": "user", "content": "hi"}],
                            max_tokens=1,
                            api_key=self.agent.api_key,
                        )
                        self._reply_queue.put(f"Model set to: {new_model}")
                    except Exception as e:
                        self.agent.model = prev_model
                        self._reply_queue.put(
                            f"Invalid model '{new_model}'\nReverted to: {prev_model}"
                        )

                threading.Thread(target=_validate, daemon=True).start()
            return

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
        if self._mod() and rl.IsKeyPressed(self._open_key):
            self._open_documents()
        if self._mod() and rl.IsKeyPressed(self._save_key):
            self._save_active_document()
        if self._mod() and rl.IsKeyPressed(self._close_key):
            self._close_active_document()
        if rl.IsKeyPressed(rl.KEY_TAB):
            self.root.set_focus(self.chat)
            self.chat.set_focus(self.chat._input)
        if rl.IsKeyPressed(rl.KEY_F5):
            self.chat.on_mic_press()
        if rl.IsKeyReleased(rl.KEY_F5):
            self.chat.on_mic_release()
        super()._process_input()
        self._window_focused = rl.IsWindowFocused()

    def _mod(self) -> bool:
        return (rl.IsKeyDown(rl.KEY_LEFT_SUPER)   or rl.IsKeyDown(rl.KEY_RIGHT_SUPER) or
                rl.IsKeyDown(rl.KEY_LEFT_CONTROL) or rl.IsKeyDown(rl.KEY_RIGHT_CONTROL))

    def _open_documents(self) -> None:
        paths = open_images()
        if paths:
            self.on_files_dropped([str(p) for p in paths])

    def _close_active_document(self) -> None:
        idx = self.workspace.active_index
        if idx < 0:
            return
        doc = self.workspace.documents[idx]
        name = doc.name
        textures.invalidate_thumbnail(doc)
        textures.invalidate_display(doc)
        self.workspace.close(idx)
        self.chat.add_entry(f"Closed '{name}'.", "agent")

    def _save_active_document(self) -> None:
        doc = self.workspace.active_document
        if not isinstance(doc, ImageDocument) or doc.image is None:
            return
        if doc.file_path is not None and not _alt_is_held():
            self._save_to_path(doc, doc.file_path)
        else:
            default = doc.file_path.name if doc.file_path else doc.name
            path = save_image(default)
            if path is not None:
                self._save_to_path(doc, path)

    def _save_to_path(self, doc: ImageDocument, path: Path) -> None:
        if path.exists():
            bak = path.with_name(path.stem + ".bak" + path.suffix)
            if not bak.exists():
                path.rename(bak)
        try:
            _save_pil(doc.image, path)
            doc.path = path
            doc.file_path = path
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
        self.header.unload()
        textures.unload_all()
        rl.CloseAudioDevice()

    def update(self) -> None:
        while not self._dialog_queue.empty():
            event, result_holder = self._dialog_queue.get()
            paths = open_images()
            result_holder.append(paths)
            event.set()

        while not self.workspace.message_queue.empty():
            self.chat.add_entry(self.workspace.message_queue.get_nowait(), "agent")

        while not self._reply_queue.empty():
            reply = self._reply_queue.get_nowait()
            self.chat.thinking = False
            self.chat.add_entry(reply, "agent")
            speak(reply)
            for doc in self.workspace.documents:
                textures.invalidate_thumbnail(doc)
                textures.invalidate_display(doc)

        if rl.IsWindowResized():
            self.layout.update(rl.GetScreenWidth(), rl.GetScreenHeight())
            self.root.width  = rl.GetScreenWidth()
            self.root.height = rl.GetScreenHeight()

    def draw(self) -> None:
        pass


def _expand_model(name: str) -> str:
    if name.startswith(("opus", "sonnet", "haiku")):
        return "anthropic/claude-" + name
    if name.startswith("claude-"):
        return "anthropic/" + name
    if name.startswith("gemini-"):
        return "gemini/" + name
    return name


def _save_pil(image: np.ndarray, path: Path) -> None:
    pil = Image.fromarray(image, "RGBA")
    if path.suffix.lower() in (".jpg", ".jpeg"):
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[3])
        bg.save(path)
    else:
        pil.save(path)


def main() -> None:
    import configargparse
    from agentcore.agent import DEFAULT_MODEL

    root = Path(__file__).parent.parent
    parser = configargparse.ArgumentParser(
        description="PixelClaw image editor",
        default_config_files=[str(root / "pixelclaw.cfg")],
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model to use")
    args = parser.parse_args()

    ensure_packages()

    api_key_file = root / "api_key.secret"
    api_key = (api_key_file.read_text().strip() if api_key_file.exists()
               else os.environ.get("OPENAI_API_KEY"))
    openai_key_file = root / "openai_key.secret"
    openai_key = (openai_key_file.read_text().strip() if openai_key_file.exists()
                  else os.environ.get("OPENAI_API_KEY") or api_key)

    PixelClawApp(title="PixelClaw", api_key=api_key, openai_key=openai_key, model=args.model).run()


if __name__ == "__main__":
    main()
