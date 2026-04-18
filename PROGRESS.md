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

## Apr 16 2026 (continued)

**LLM backend & agent loop**
- Switched from Anthropic SDK to **LiteLLM** for provider-agnostic function-calling; default model `gpt-5.4-nano` (key read from `api_key.secret`); `litellm.suppress_debug_info = True` silences startup noise.
- `Agent` rebuilt around OpenAI-style `chat/completions`: `_build_messages()` assembles `[system(instructions), system(context), *history]` fresh each call; `_trim_history()` drops oldest user-turn groups when history exceeds 40 messages; `_write_debug()` writes `debug_output/NNNN_request.json` + `NNNN_response.json` for inspection; debug folder is cleared on each launch.
- `Tool.to_api_dict()` now emits OpenAI function-calling schema (`{"type":"function","function":{...}}`).
- `Context.agent_reason` field — set by `Agent` to the model's text content before each tool dispatch, so tools can record the intent alongside the image version.
- `Context.render_context()` default implementation; overridden in `ImageWorkspace` to report image size, channel layout, dtype, version count, and selection rect.
- Agent messages and tool invocations printed to terminal as they arrive (`[agent] …` / `[tool] name(args)`).
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
- `apply` — execute arbitrary Python/numpy code against the active image **in place**; supports single expressions and multi-line code blocks (assigns to `result`); `np`, `ndi` (scipy.ndimage), and `skimage` available. Instructions note this modifies the active document — use `multi_apply` to produce a new document.
- `inspect` — report per-channel min/max/mean, transparency breakdown, content bounding box, and an 8×8 hex alpha map for spatial orientation; optional sub-region.
- `crop` — crop to rectangle; reports resulting version index.
- `pad` — add border; performs **alpha bleed** (fills transparent border pixels with nearest edge pixel's RGB) so edge effects like glow work correctly. Root-caused via diagnostic instrumentation: tool-padded images had `[0,0,0,0]` in transparent zone vs. GraphicConverter's `[112,112,112,0]`, causing invisible glow.
- `scale` — resize with nearest/bilinear/lanczos resampling; derives missing dimension from aspect ratio.
- `version_history` — list all versions with index and reason.
- `revert` — revert to a given version index, discarding later ones.
- `set_active` — change the active document by name.
- `close_documents` — close named documents; accepts `["all except active"]` as a shorthand.
- `new_from_region` — create a new document from a region of the active image without modifying the original; omit region args to duplicate.
- `multi_apply` — apply Python/numpy code reading from multiple named documents; write result to a named or new document. Accepts `"active"` as a special document name in both `images` and `result_name` to avoid needing to track the active document's filename across multi-step turns.

**Display fixes**
- `textures.py`: display textures use `TEXTURE_FILTER_POINT` (sharp pixels); thumbnails use `TEXTURE_FILTER_BILINEAR`.
- `font.py`: extended character set (curly quotes, em-dash, en-dash, ellipsis, etc.) loaded via `codepoints_arr`; fixed `global` declaration so module-level variables are updated correctly on first use.

**Agent instructions** (`pixelclaw/agent_instructions.md`)
- Documents all tools with examples including flip/rotate, glow (multi-line), grayscale, and alpha-composite patterns.
- Protocol rules: never announce an action without calling the tool; single-step tasks call the tool immediately with no preamble; `apply` is in-place, `multi_apply` creates/updates a named document.

---

## Apr 17 2026

**New image tools**
- `generate_image` — creates a new document via OpenAI `gpt-image-1`; posts "Generating image: …" progress message to chat before the API call.
- `edit_image` — edits the active document via `gpt-image-1`; uses the selection rect as a mask if present; posts progress message; `_nearest_size()` picks the closest supported size.
- `remove_background` — removes image background using `rembg` neural network (default model `isnet-general-use`; 6 models listed for LLM selection); posts "Removing background…" or "Downloading model…" depending on cache state.
- `new_image` — creates a blank canvas filled with a solid RGBA color (default transparent); instant, no API call. Agent instructions explicitly tell the LLM to prefer this over `generate_image` for solid fills.
- `rotate` — rotates the active image by a given number of degrees (CCW positive) around a configurable pivot (default: image center); canvas expands automatically so no content is lost by finding the rotated bounding box of the active (non-transparent) content and growing the canvas to contain it; reports original and new size.
- `soft_threshold` — cleans up grayscale masks by snapping interior pixels to 0/255 while preserving anti-aliased edges. Works by: thresholding to binary, flood-filling enclosed holes (with edge-pad trick so shapes touching the border are handled), computing per-pixel distance from the binary edge, then blending — original value within `min_dist` px of the edge, snapped value beyond `min_dist` px, interpolated in between. Parameters: `channel` (luminance/alpha/red/green/blue), `threshold` (128), `min_dist` (2), `max_dist` (7).
- `inspect` — extended to include an 8×8 color map (average RGB per cell as hex) alongside the existing alpha map, so the LLM can identify spatial color and transparency issues.
- `pad` — default fill color now samples all four corners and uses the most common (if any two agree) or the average; prevents black-bar artifacts when padding images with a uniform background.

**OpenAI integration**
- `api_key.secret` is the OpenAI key used via LiteLLM (not an Anthropic key). `openai_key.secret` may also be present; if so it takes priority; otherwise `api_key.secret` is used for both the agent and image tools.
- `ml_deps.py` — `ensure_packages()` installs optional ML dependencies at startup (before `InitWindow`); `rembg[cpu]` installed via pip, `numba` (required by pymatting → rembg) installed via micromamba to get pre-built binaries.

**Vision support**
- Agent injects a 128×128 base64 PNG thumbnail of the active document into the last user message as a `detail:low` image URL, enabling vision-capable models to see what they're working on.
- `Agent._use_vision` flag; `_call_llm()` auto-detects vision-related API errors, disables vision, and retries transparently.
- `Context.message_queue` (thread-safe `queue.Queue`) + `post_message()` — tools post progress strings from background threads; `PixelClawApp.update()` drains the queue into the chat panel each frame.
- Post-operation verification rule added to agent instructions: after any visual operation, call `inspect` before reporting success.

**UI — checkerboard background**
- `MainPanel` loads `pixelclaw/resources/backgroundPattern.png` as a tiled texture behind the active image so transparency is visually apparent. Uses `TEXTURE_WRAP_REPEAT` + `DrawTexturePro` with an oversized source rect (no `DrawTextureTiled` in this Raylib version).

**File save (Cmd+S / Ctrl+S)**
- `file_dialogs.py` — `save_image()` shows a native save dialog: `NSSavePanel` via PyObjC on macOS, tkinter fallback on other platforms. PyObjC kept strictly inside `file_dialogs.py`.
- Layout-aware key detection: `_find_key_for_char('s')` scans key codes 32–350 using `glfwGetKeyName(key, 0)` (layout-aware) to find the code that produces `'s'` in the current OS keyboard layout. Runs once in `on_start()` after `InitWindow`. Correctly handles Dvorak, Colemak, etc.
- JPEG save composites on a white RGB background before saving (no alpha channel in JPEG).

---

## Apr 18 2026

**`pixelate` tool** (`pixelclaw/tools/pixelate.py`)
- Wraps the pyxelate library (installed from GitHub; uses Bayesian Gaussian Mixture + sobel-weighted downsampling).
- Accepts `factor` **or** `target_width`/`target_height` (or both, validated for consistency). When a target size is given the image is pre-scaled (Lanczos) to the nearest exact multiple of the factor before pixelation, so the output matches the requested size precisely.
- `svd` defaults to `false` (faster; empirically looks better).
- Posts a progress message (with expected output size and palette count) before the slow BGM step.
- Includes a `__main__` test block: prompts for input path and parameters, writes `<stem>_pixelated.png`.
- Agent instructions updated: `pixelate` entry now includes `target_width`/`target_height` params and an explicit rule to never follow a `pixelate` call with a `scale` call.

**`undo` tool** (`pixelclaw/tools/undo.py`)
- No-argument shortcut for "revert to previous version". Returns the version label and current image dimensions.
- `revert` tool also updated to report image dimensions after reverting, so the agent is grounded before proceeding with further operations.
- Agent instructions updated: explicit rule that when asked to undo-then-redo, `undo` must be called first and its returned state verified before any subsequent tool call.

**Main panel UI tweak** (`pixelclaw/mainpanel.py`)
- 16 px top and bottom margin added; image scales to fit the margined area.
- Current image dimensions (e.g. `512×512`) drawn right-aligned in the top margin in small translucent gray text.

**`separate_layers` tool** (`pixelclaw/tools/separate_layers.py`)
- Splits a cartoon/line-art image into `_ink` (black outlines, varying alpha), `_color` (flat fill colors), `_bg` (background, fully opaque), and `_palette` (swatch strip) documents.
- **Palette discovery**: uses pyxelate's BGM (not K-means) on a near-black-purified copy of the image. Pixels with `max(R,G,B) < 64` are snapped to true black before fitting, preventing AI-image speckle in dark areas from registering as spurious fill colors.
- **Background detection**: samples border pixels, quantizes to 8-step bins, and votes for the most common color — handles any background color, not just white.
- **Unmixing**: extended palette is `[black, bg_color, ...fill_colors]`. For each pixel the two nearest palette entries are found (Euclidean RGB) and the linear mix solved. Cases: ink/fill, fill/bg, ink/bg, solid fill, solid ink, solid bg — each assigns correctly to the three output layers.
- Background layer is fully opaque (solid detected bg color, no alpha cutout).
- Includes a `__main__` test block.

**InputField improvements**
- `Alt+Backspace` — delete word to the left of cursor.
- `Alt+Delete` — delete word to the right of cursor.
- **Focus bug fix** — `Panel.is_focused` previously only checked one level up the parent chain; a click on the main panel would update `root._focused_child` but leave `ChatPanel._focused_child` still pointing at `InputField`, causing the cursor to appear focused while keyboard events were dead-ended elsewhere. Fixed by walking the full ancestor chain to verify every level agrees.

**`posterize` tool** (`pixelclaw/tools/posterize.py`)
- Reduces an image to a small flat-color palette to eliminate speckle/texture common in AI-generated images, without changing image size.
- Pipeline: Gaussian blur of configurable `blend_radius` → BGM palette discovery (via sklearn `BayesianGaussianMixture`) on blurred pixels → nearest-palette remap of original pixels → optional despeckle pass.
- **Palette discovery**: subsamples to 50k pixels for speed; active components filtered by weight threshold; pure black `(0,0,0)` and white `(255,255,255)` always guaranteed in palette (replacing near-black/near-white entries within L2 distance 60, or appending if none are close).
- **Despeckle** (`despeckle=True` by default): after palette remap, finds every pixel whose label differs from all 8 neighbors and replaces it with the modal neighbor label. Vectorized via `np.roll` + per-label vote counts.
- Includes a `__main__` test block (prompts for input, palette, blend_radius, despeckle; writes `<stem>_posterized.png`).
- Registered in `__init__.py`, imported and instantiated in `main.py`, documented in `agent_instructions.md`.

**`inspect` tool update**
- Now reports unique color count (RGB, ignoring alpha) for the inspected region.

**Tab-to-focus shortcut**
- Pressing Tab anywhere in the window routes keyboard focus to the chat input field (`root.set_focus(chat)` + `chat.set_focus(chat._input)`). Both links in the focus chain must be set — only setting the bottom link was the original bug.

**Thinking indicator**
- `ChatPanel` gains `thinking: bool` + `_thinking_start: float` attributes. When `thinking` is True and ≥5 seconds have elapsed, three pulsing dots are drawn below the last speech balloon (inside the scroll scissor region); content height is expanded to include them, and the panel auto-scrolls to show them on their first visible frame.
- `PixelClawApp._handle_message()` sets `thinking = True`; `update()` clears it when the reply arrives.

**Agent instruction fixes**
- `edit_image` description now explicitly calls out removing specific objects as a use case.
- `remove_background` description clarified: removes the *background* (making it transparent), not objects within the scene — cross-references `edit_image` for object removal.

**CLAUDE.md additions**
- `debug_output/` directory documented as the primary debugging tool (numbered request/response JSON pairs, cleared on each launch).
- "How to add a new tool" checklist added with all four required steps (create file, register in `__init__.py`, import + instantiate in `main.py`, document in `agent_instructions.md`), with a note that missing step 4 is the most common mistake.
