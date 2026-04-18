# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PixelClaw is a desktop image manipulation app: a Raylib UI + Anthropic LLM agent harness. Most operations are driven by the LLM via tools. It is the prototype for a future suite of "Claw" apps (SoundClaw, PDFClaw, etc.); `agentcore` will eventually become a standalone package.

## Environment

micromamba, environment name `pixelclaw`. Run with:
```bash
micromamba run -n pixelclaw python -m pixelclaw.main
```
Recreate: `micromamba env create -f environment.yml`

## Package Structure

```
agentcore/          ← reusable framework; never imports from pixelclaw
  context.py        ← Context[D] base: documents, history, current_task, chat_history
  document.py       ← abstract Document (path, dirty, load, save)
  tool.py           ← abstract Tool (name, input_schema, execute)
  agent.py          ← Anthropic agentic loop + tool dispatch
  app.py            ← App base: Raylib window, on_start/update/draw/on_close/on_files_dropped hooks,
                       _process_input (mouse, keyboard, scroll wheel, file drop each frame)
  panel.py          ← Panel: named rect, bg_color, child hierarchy, mouse/keyboard/wheel routing,
                       focus follows click, handle_* dispatches, on_* override points
  font.py           ← Font: TTF wrapper, per-physical-px cache, HiDPI-aware draw/measure
  ninepatch.py      ← NinePatch: 9-slice PNG + JSON sidecar (border widths)
  chatpanel.py      ← ChatPanel(Panel): scrollable balloon transcript + InputField child
  inputfield.py     ← InputField(Panel): full single-line edit (selection, clipboard, auto-repeat)
  resources.py      ← default_font() singleton; unload_all() called by App.run()
  workspace.py      ← shim: Workspace = Context (backward compat)

pixelclaw/          ← image app; imports agentcore, never vice versa
  main.py           ← PixelClawApp entry point; layout, file-drop handler
  workspace.py      ← ImageWorkspace(Context[ImageDocument]): adds selection rect
  document.py       ← ImageDocument(Document): wraps PIL Image
  layout.py         ← LayoutManager: Header 64px / Dock 128px / Main / Chat 20%
  dockpanel.py      ← DockPanel: thumbnails, click to activate document
  mainpanel.py      ← MainPanel: active document scaled-to-fit
  textures.py       ← PIL→Raylib texture cache (thumbnails + display); unload_all()
  tools/            ← LLM-callable Tool subclasses (empty so far)

agentcore/resources/
  DejaVuSans.ttf
  speechBalloonLeft.png + .json   ← borders: left=64, top=32, right=32, bottom=32
  speechBalloonRight.png + .json  ← borders: left=32, top=32, right=64, bottom=32
```

## Key Raylib API notes

- Functions are PascalCase matching the C API (`InitWindow`, `DrawTextEx`, etc.)
- Colors and structs are tuples/CFFI objects; no `rl.Color` or `rl.Vector2` types exposed
- Create structs: `rl.ffi.new("Vector2 *", [x, y])[0]`, pass by value to draw calls
- NULL pointer: `rl.ffi.NULL` (not Python `None`)
- `LoadFontEx(path, size, rl.ffi.NULL, 0)` — font loaded at physical pixels
- `GetWindowScaleDPI().x` — HiDPI scale factor (2.0 on Retina)
- `BeginScissorMode` / `EndScissorMode` — clip drawing to a rectangle
- `DrawTextureNPatch` — 9-slice drawing
- `IsKeyPressedRepeat(key)` — use for auto-repeating keys (Backspace, Delete)
- `GetMouseWheelMove()` — use `sign(delta)` not raw value for consistent scroll speed
- GPU resources (textures, fonts) must be created after `InitWindow` — use `on_start()` hook

## Threading rules

Agent tools run on a background thread. **Tools must never call Raylib or touch `textures.py`** — all OpenGL calls (including `UnloadTexture`) must happen on the main thread. The pattern:
- Tools call `doc.push(array)` only.
- `PixelClawApp.update()` drains the reply queue on the main thread, then calls `textures.invalidate_thumbnail/display` for all documents.

## Debugging

Agent API requests and responses are logged to `debug_output/` as numbered JSON pairs (`0001_request.json` / `0001_response.json`, etc.). Each request contains the full message history and tool list; each response shows which tool was called and the token counts. This is the primary way to diagnose unexpected agent behavior.

## How to add a new tool

1. Create `pixelclaw/tools/<name>.py` with a class subclassing `Tool`. Implement `name`, `description`, `input_schema`, and `execute`.
2. Add an `if __name__ == "__main__":` block for manual testing (prompt for an input image and parameters, run the algorithm, save `<stem>_<toolname>.png`). Run with `micromamba run -n pixelclaw python -m pixelclaw.tools.<name>`.
3. Register in `pixelclaw/tools/__init__.py`: add the import and add the class name to `__all__`.
4. Import and instantiate in `pixelclaw/main.py`: add to the `from .tools import (...)` line **and** add `MyTool()` inside `create_tools()`.
5. Document the tool in `pixelclaw/agent_instructions.md` under `# Available Tools`.

Missing step 4 is the most common mistake — the tool exists but the agent can't see it.

## Architecture notes

- `Context.chat_history` is the raw Anthropic API list; `Context.history` is the human-readable event log
- `Panel.handle_*` dispatches events; `Panel.on_*` is the override point for subclasses
- Scroll wheel is routed by `App._process_input` every frame independently of mouse movement
- `textures.py` caches PIL→Raylib conversions; call `textures.unload_all()` in `on_close()`
- `NinePatch` and `ChatPanel` balloons load lazily on first draw (GPU context required)
- `InputField` is owned by `ChatPanel`; positioned/sized via `_layout_input()` called from width/height setters
