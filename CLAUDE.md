# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PixelClaw is a desktop image manipulation app: a Raylib UI + LLM agent harness. Most operations are driven by the LLM via tools. It is the prototype for a future suite of "Claw" apps (SoundClaw, PDFClaw, etc.); `agentcore` will eventually become a standalone package.

The agent loop goes through **LiteLLM**, so any provider it supports works (OpenAI, Anthropic, Gemini, Groq, …). Nothing in the codebase is Anthropic-specific.

## Platform policy

Code must be cross-platform (macOS, Windows, Linux) **except** in `pixelclaw/file_dialogs.py`, which is the designated home for any platform-specific file-dialog logic. Do not use `afplay`, `AppleScript`, `pyobjc`, or other macOS-only APIs outside that module.

## Environment

micromamba, environment name `pixelclaw`. Run with:
```bash
micromamba run -n pixelclaw python -m pixelclaw.main
```
Recreate: `micromamba env create -f environment.yml`

**Model selection:** `pixelclaw.cfg` (configargparse) sets the model and **overrides** `DEFAULT_MODEL` in `agentcore/agent.py` — the constant only applies if the cfg file is missing. `--model` on the command line beats both, and `/model <name>` in the chat panel switches at runtime (validated with a 1-token completion, reverting on failure). `_expand_model` in `main.py` adds the provider prefix for `opus`/`sonnet`/`haiku`/`claude-*`/`gemini-*` shorthands.

**API keys:** `api_key.secret` at the project root (or `OPENAI_API_KEY`) is passed to LiteLLM and may hold *any* provider's key. `openai_key.secret` is OpenAI-specific and used only by `generate_image`/`edit_image`, falling back to `api_key.secret`. Never assume `api_key.secret` is any particular provider's.

## Package Structure

```
agentcore/          ← reusable framework; never imports from pixelclaw
  context.py        ← Context[D] base: documents, history, current_task, chat_history,
                       message_queue, agent_reason, render_context/render_thumbnail
  document.py       ← abstract Document (path, dirty, load, save)
  tool.py           ← abstract Tool (name, input_schema, execute)
  agent.py          ← LiteLLM agentic loop + tool dispatch; context assembly, history
                       trimming, vision fallback, debug_output dumps
  app.py            ← App base: Raylib window, on_start/update/draw/on_close/on_files_dropped hooks,
                       _process_input (mouse, keyboard, scroll wheel, file drop each frame)
  panel.py          ← Panel: named rect, bg_color, child hierarchy, mouse/keyboard/wheel routing,
                       focus follows click, handle_* dispatches, on_* override points
  font.py           ← Font: TTF wrapper, per-physical-px cache, HiDPI-aware draw/measure
  ninepatch.py      ← NinePatch: 9-slice PNG + JSON sidecar (border widths)
  chatpanel.py      ← ChatPanel(Panel): scrollable balloon transcript + InputField child
  inputfield.py     ← InputField(Panel): full single-line edit (selection, clipboard, auto-repeat)
  toolbarbutton.py  ← ToolbarButton(Panel): icon/label button with hover + press states
  mdrender.py       ← Markdown → laid-out styled spans for chat balloons
  key_utils.py      ← find_key_for_char(): keyboard-layout-aware shortcut lookup
  log.py            ← Markdown transcript logger, one file per run in logs/
  speech.py         ← text-to-speech (Kokoro ONNX, downloaded on first use) + HALO voice effects
  stt.py            ← speech-to-text (faster-whisper base.en, local CPU); push-to-talk + VAD
  resources.py      ← default_font() singleton; unload_all() called by App.run()
  workspace.py      ← shim: Workspace = Context (backward compat)

pixelclaw/          ← image app; imports agentcore, never vice versa
  main.py           ← PixelClawApp entry point; layout, file-drop handler, /model command,
                       queue draining, key file loading
  workspace.py      ← ImageWorkspace(Context[ImageDocument]): selection rect, mouse image pos,
                       display background; rich render_context() override
  document.py       ← ImageDocument(Document): append-only version list, thumbnail_b64()
  layout.py         ← LayoutManager: Header 64px / Dock 128px / Main / Chat 20%
  headerpanel.py    ← HeaderPanel: open/save/close toolbar buttons
  dockpanel.py      ← DockPanel: thumbnails, click to activate document
  mainpanel.py      ← MainPanel: active document scaled-to-fit, selection drag
  display.py        ← display background parsing ("checkerboard" or HTML color)
  file_dialogs.py   ← native open/save dialogs — the ONLY place platform-specific code belongs
  ml_deps.py        ← installs optional ML packages (rembg) at startup if missing
  textures.py       ← PIL→Raylib texture cache (thumbnails + display); unload_all()
  tools/            ← 29 LLM-callable Tool subclasses; see tools/__init__.py for the list

agentcore/resources/
  DejaVuSans.ttf (+ -Bold, -Oblique, -BoldOblique)
  MicIcon.png
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

Agent tools run on a background thread (one daemon thread per user message). **Tools must never call Raylib or touch `textures.py`** — all OpenGL calls (including `UnloadTexture`) must happen on the main thread. The pattern:
- Tools call `doc.push(array)` only.
- `PixelClawApp.update()` drains the queues on the main thread, then calls `textures.invalidate_thumbnail/display` for all documents.

Three queues cross the thread boundary, all drained in `update()`:
- `_reply_queue` — the agent's final reply text → chat panel
- `workspace.message_queue` — mid-tool status updates; call `workspace.post_message(text)` from a tool for progress on slow operations
- `_dialog_queue` — a tool requesting a native file dialog, which must run on the main thread. The tool pushes `(threading.Event, result_holder)` and blocks on the event (120s timeout). See `OpenDocumentTool._open_via_dialog`.

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

- `Context.chat_history` is the raw LiteLLM/OpenAI-format message list (`role`/`content`, with `tool_calls` and `role: "tool"` entries); `Context.history` is the human-readable event log
- Context is rebuilt from scratch on every LLM call: system instructions + `render_context()` state snapshot + trimmed `chat_history` + a base64 thumbnail of the active document spliced into the most recent user message. Override `render_context()` to expose new app state to the agent — that's the cheapest way to give it new awareness without adding a tool
- `MAX_HISTORY_MESSAGES` (40) trims whole user-turn groups from the front, never splitting an assistant/tool-call/tool-result group
- Vision degrades gracefully: a vision-related API error sets `_use_vision = False` and retries once without the thumbnail
- `ImageDocument` keeps every version in memory (`_versions` is a list of `(ndarray, reason)`); `push(array, reason)` appends. Pass a meaningful `reason` — it's what `version_history` shows the agent
- `Panel.handle_*` dispatches events; `Panel.on_*` is the override point for subclasses
- Scroll wheel is routed by `App._process_input` every frame independently of mouse movement
- `textures.py` caches PIL→Raylib conversions; call `textures.unload_all()` in `on_close()`
- `NinePatch` and `ChatPanel` balloons load lazily on first draw (GPU context required)
- `InputField` is owned by `ChatPanel`; positioned/sized via `_layout_input()` called from width/height setters
