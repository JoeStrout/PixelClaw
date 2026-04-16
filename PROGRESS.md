# PixelClaw Progress Log

## Apr 16 2026

Bootstrapped the project from scratch.

**Environment & structure**
- Set up micromamba environment (`pixelclaw`) with Python 3.12, raylib, anthropic, and Pillow.
- Established two-package layout: `agentcore/` (reusable core, no app-specific imports) and `pixelclaw/` (image app built on top of it). Designed so `agentcore` can be extracted into its own repo later.

**agentcore — framework**
- `Document` / `Context` — abstract base classes for open documents and app state (documents list, history log, current task, Anthropic API chat history).
- `Tool` — abstract base for LLM-callable tools (name, JSON schema, execute).
- `Agent` — Anthropic conversation loop with tool dispatch and chat history management.
- `App` — Raylib window lifecycle (`on_start`, `update`, `draw`, `on_close`, `on_files_dropped` hooks; `_process_input` routes mouse, keyboard, scroll wheel, and file drops each frame).
- `Panel` — named rectangular UI region forming a hierarchy: background fill, recursive draw, mouse hit-testing and focus routing (focus follows click), keyboard routing down the focus chain, `handle_mouse_wheel` routed independently of mouse movement.
- `Font` — TrueType font wrapper with a per-physical-pixel cache for HiDPI-correct rendering; `measure()` and `draw()` in logical coordinates.
- `NinePatch` — 9-slice image loaded from PNG + JSON sidecar (border widths); wraps `DrawTextureNPatch`.
- `resources` — lazy singleton for the default font (DejaVuSans); auto-unloaded by `App`.
- `ChatPanel` — scrollable transcript of chat entries displayed as speech balloons (agent left, user right) with word-wrap, scissor clipping, and mouse-wheel scrolling.
- `InputField` — single-line text input with full editing: cursor, click-to-place, drag-to-select, shift+arrows, Alt/Ctrl word movement, Home/End/Up/Down, Backspace/Delete with OS auto-repeat, Ctrl+A/C/X/V clipboard, Enter to submit.

**pixelclaw — image app**
- `ImageDocument` — wraps a PIL `Image`; load/save.
- `ImageWorkspace` — extends `Context[ImageDocument]`; adds a selection rectangle.
- `LayoutManager` — hard-coded four-panel layout: Header (64 px tall), Dock (128 px wide), Main (fills remainder), Chat (20 % of width); recalculates on window resize.
- `DockPanel` — shows a thumbnail and filename for each open document; active document highlighted; click to activate.
- `MainPanel` — displays the active document scaled-to-fit with aspect ratio preserved; "drop an image" hint when empty.
- `textures` — PIL→Raylib texture conversion with separate thumbnail and display caches; `unload_all()` on close.
- `PixelClawApp` — wires everything together; handles file-drop (PNG/JPEG/etc.) by opening documents into the workspace and logging to context history.

**Assets**
- `agentcore/resources/DejaVuSans.ttf` — default UI font.
- `agentcore/resources/speechBalloonLeft.png` / `speechBalloonRight.png` + JSON sidecars — 9-slice speech balloon images for the chat panel.
