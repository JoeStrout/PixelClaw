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

---

## Apr 16–17 2026 (continued)

**LLM backend & agent loop**
- Switched from Anthropic SDK to **LiteLLM** for provider-agnostic function-calling; default model `gpt-5.4-nano` (key read from `api_key.secret`).
- `Agent` rebuilt around OpenAI-style `chat/completions`: `_build_messages()` assembles `[system(instructions), system(context), *history]` fresh each call; `_trim_history()` drops oldest user-turn groups when history exceeds 40 messages; `_write_debug()` writes `debug_output/NNNN_request.json` + `NNNN_response.json` for inspection.
- `Tool.to_api_dict()` now emits OpenAI function-calling schema (`{"type":"function","function":{...}}`).
- `Context.agent_reason` field — set by `Agent` to the model's text content before each tool dispatch, so tools can record the intent alongside the image version.
- `Context.render_context()` default implementation; overridden in `ImageWorkspace` to report image size, channel layout, dtype, version count, and selection rect.
- Agent messages printed to terminal as they arrive (`[agent] …`).
- Background threading: `_handle_message` starts a daemon thread; `update()` drains `_reply_queue` on the main thread and invalidates textures there (all OpenGL calls on main thread only — documented as architectural rule in `CLAUDE.md`).
- `get_instructions_path()` hook on `App`; `PixelClawApp` points to `pixelclaw/agent_instructions.md`.

**Image representation & version history**
- `ImageDocument` stores images as numpy `uint8` RGBA arrays (`(H, W, 4)`).
- Version history: `_versions: list[tuple[np.ndarray, str]]` — each entry is `(array, reason)`; initial load gets reason `"loaded from file"`.
- `push(array, reason)` appends and returns the new version index.
- `revert_to(index)` discards later versions.
- `version_history()` returns `[(index, reason), …]`.
- Fixed `load()` to use `np.array()` (copy) instead of `np.asarray()` (view into PIL buffer) to avoid GC-related data corruption.

**LLM-callable tools**
- `crop` — crop to rectangle; reports resulting version index.
- `pad` — add transparent border; performs **alpha bleed** (fills transparent border pixels with the nearest edge pixel's RGB) so edge effects like glow work correctly.
- `scale` — resize with nearest/bilinear/lanczos resampling; derives missing dimension from aspect ratio.
- `apply` — execute arbitrary Python/numpy code against the image; supports single expressions and multi-line code blocks (assigns to `result`); `np`, `ndi` (scipy.ndimage), and `skimage` available.
- `version_history` — list all versions with index and reason.
- `revert` — revert to a given version index, discarding later ones.

**Display fixes**
- `textures.py`: display textures use `TEXTURE_FILTER_POINT` (sharp pixels); thumbnails use `TEXTURE_FILTER_BILINEAR`.
- `font.py`: extended character set (curly quotes, em-dash, en-dash, ellipsis, etc.) loaded via `codepoints_arr`; fixed `global` declaration so module-level variables are updated correctly on first use.

**Agent instructions**
- `pixelclaw/agent_instructions.md`: documents all six tools with examples; multi-line `apply` example shows correct yellow-glow pattern; protocol rule added: "never announce an action without also calling the tool in the same response."
