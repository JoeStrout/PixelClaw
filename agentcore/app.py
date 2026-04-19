from abc import ABC, abstractmethod
from pathlib import Path

import raylib as rl

from . import resources
from .agent import Agent, DEFAULT_MODEL
from .context import Context
from .panel import Panel
from .tool import Tool

class App(ABC):
    def __init__(
        self,
        title: str,
        width: int = 1422,
        height: int = 800,
        window_flags: int = rl.FLAG_WINDOW_RESIZABLE,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
    ):
        self.title = title
        self.width = width
        self.height = height
        self.window_flags = window_flags
        p = self.get_instructions_path()
        instructions = p.read_text() if p and p.exists() else None
        self.workspace: Context = self.create_workspace()
        tools: list[Tool] = self.create_tools()
        self.agent = Agent(self.workspace, tools, model=model, api_key=api_key,
                           instructions=instructions)
        self.root = Panel("root")

    def get_instructions_path(self) -> Path | None:
        """Return path to the agent instructions file. Override in subclasses."""
        return None

    @abstractmethod
    def create_workspace(self) -> Context: ...

    @abstractmethod
    def create_tools(self) -> list[Tool]: ...

    def on_start(self) -> None:
        """Called once after InitWindow. Override to load GPU resources (textures, etc.)."""
        pass

    def update(self) -> None:
        """Called each frame before draw. Override to handle non-panel app logic."""
        pass

    def draw(self) -> None:
        """Called each frame inside BeginDrawing/EndDrawing, after root.draw_all().
        Override to draw anything that should appear above the panel tree."""
        pass

    def on_close(self) -> None:
        """Called once before CloseWindow. Override to unload GPU resources."""
        pass

    def on_files_dropped(self, paths: list[str]) -> None:
        """Called when files are dragged onto the window. Override to handle them."""
        pass

    def run(self) -> None:
        if self.window_flags:
            rl.SetConfigFlags(self.window_flags)
        rl.InitWindow(self.width, self.height, self.title.encode())
        rl.SetTargetFPS(60)
        self.root.width = self.width
        self.root.height = self.height
        self.on_start()
        try:
            while not rl.WindowShouldClose():
                self._process_input()
                self.update()
                rl.BeginDrawing()
                rl.ClearBackground(rl.BLACK)
                self.root.draw_all()
                self.draw()
                rl.EndDrawing()
        finally:
            self.on_close()
            resources.unload_all()
            rl.CloseWindow()

    def _process_input(self) -> None:
        """Read Raylib input each frame and route to the panel tree."""
        mx = float(rl.GetMouseX())
        my = float(rl.GetMouseY())

        for button in (rl.MOUSE_BUTTON_LEFT, rl.MOUSE_BUTTON_RIGHT, rl.MOUSE_BUTTON_MIDDLE):
            if rl.IsMouseButtonPressed(button):
                self.root.handle_mouse_press(mx, my, button)
            if rl.IsMouseButtonReleased(button):
                self.root.handle_mouse_release(mx, my, button)

        if rl.GetMouseDelta().x != 0 or rl.GetMouseDelta().y != 0:
            self.root.handle_mouse_move(mx, my)

        wheel = rl.GetMouseWheelMove()
        if wheel != 0:
            self.root.handle_mouse_wheel(mx, my, wheel)

        key = rl.GetKeyPressed()
        while key != 0:
            self.root.handle_key_press(key)
            key = rl.GetKeyPressed()

        char = rl.GetCharPressed()
        while char != 0:
            self.root.handle_char(chr(char))
            char = rl.GetCharPressed()

        if rl.IsFileDropped():
            dropped = rl.LoadDroppedFiles()
            paths = [
                rl.ffi.string(dropped.paths[i]).decode()
                for i in range(dropped.count)
            ]
            rl.UnloadDroppedFiles(dropped)
            self.on_files_dropped(paths)
